"""Microsoft Entra ID (Azure AD) bearer-token validation for the API.

Enterprise principle: the API is a protected resource server. Every request must
present a valid OAuth2 access token issued by your tenant for THIS API's
audience. Tokens are validated cryptographically against the tenant JWKS
(RS256), and issuer/audience/expiry are checked. Optional allow-lists restrict
access to specific users or AAD groups.

If AUTH_ENABLED is false (local dev default) the dependency is a no-op so the
app stays runnable out-of-the-box.
"""
from __future__ import annotations

import logging
import time

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import config

log = logging.getLogger("ats.auth")

# jose is only required when auth is enabled; import lazily so local dev needs
# no crypto dependencies.
try:
    from jose import jwt
    from jose.exceptions import JWTError
    _JOSE = True
except Exception:  # pragma: no cover
    _JOSE = False

_bearer = HTTPBearer(auto_error=False)

# Small in-process JWKS cache (Entra rotates keys infrequently).
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL = 3600.0


def _get_jwks() -> dict:
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"] < _JWKS_TTL):
        return _jwks_cache["keys"]
    resp = httpx.get(config.jwks_uri(), timeout=10)
    resp.raise_for_status()
    _jwks_cache["keys"] = resp.json()
    _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def _signing_key(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    for key in _get_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key
    # Force one refresh in case of key rotation.
    _jwks_cache["keys"] = None
    for key in _get_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key
    raise HTTPException(401, "Signing key not found for token.")


def _authorize_claims(claims: dict) -> None:
    users = config.allowed_users()
    groups = config.allowed_groups()
    if users:
        upn = (claims.get("preferred_username") or claims.get("upn") or claims.get("email") or "").lower()
        if upn not in users:
            raise HTTPException(403, "User is not permitted to access this application.")
    if groups:
        token_groups = set(claims.get("groups", []) or [])
        if token_groups.isdisjoint(groups):
            raise HTTPException(403, "User's group membership is not permitted.")


def _validate(token: str) -> dict:
    if not _JOSE:
        raise HTTPException(500, "Auth is enabled but 'python-jose' is not installed.")
    try:
        key = _signing_key(token)
        # Accept both v2 (api://<id>) and raw client-id audiences.
        audiences = [config.AZURE_CLIENT_ID, f"api://{config.AZURE_CLIENT_ID}"]
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audiences,
            issuer=config.issuer(),
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise HTTPException(401, f"Invalid token: {exc}") from exc
    _authorize_claims(claims)
    return claims


async def require_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency. Returns the validated user's claims, or a dev stub."""
    if not config.auth_enabled():
        return {"sub": "local-dev", "name": "Local Developer", "auth": "disabled"}
    if creds is None or not creds.credentials:
        raise HTTPException(401, "Missing bearer token.", headers={"WWW-Authenticate": "Bearer"})
    claims = _validate(creds.credentials)
    log.info("authenticated user: %s", claims.get("preferred_username") or claims.get("name"))
    return claims
