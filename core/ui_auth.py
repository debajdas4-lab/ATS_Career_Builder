"""Streamlit-side Microsoft Entra ID (Azure AD) sign-in via MSAL.

Implements the OAuth2 Authorization Code flow:
  1. Show a "Sign in with Microsoft" button -> redirect to Entra.
  2. Entra redirects back with ?code=... .
  3. Exchange the code for an access token (for the API's scope) + id token.
  4. Cache the token in st.session_state; attach it as a Bearer header on API calls.

If auth is disabled server-side, `ensure_signed_in` is a no-op and returns None,
so local development requires no Azure setup at all.
"""
from __future__ import annotations

import httpx
import streamlit as st


def _cfg(api_url: str) -> dict:
    try:
        resp = httpx.get(f"{api_url}/auth/config", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"auth_enabled": False}


def _msal_app(cfg: dict, client_secret: str):
    import msal

    return msal.ConfidentialClientApplication(
        client_id=cfg["ui_client_id"],
        authority=cfg["authority"],
        client_credential=client_secret,
    )


def ensure_signed_in(api_url: str, client_secret: str) -> dict | None:
    """Gate the app behind Entra ID sign-in. Returns the token record or None.

    Token record shape: {"access_token": str, "name": str, "username": str}.
    """
    cfg = _cfg(api_url)
    if not cfg.get("auth_enabled"):
        return None  # auth disabled -> open access (local/dev)

    if "auth_token" in st.session_state:
        return st.session_state["auth_token"]

    scopes = [cfg["api_scope"]] if cfg.get("api_scope") else []
    app = _msal_app(cfg, client_secret)

    # Step 2/3: handle the redirect back from Entra (authorization code present).
    params = st.query_params
    code = params.get("code")
    if code:
        result = app.acquire_token_by_authorization_code(
            code, scopes=scopes, redirect_uri=cfg["redirect_uri"],
        )
        if "access_token" in result:
            claims = result.get("id_token_claims", {})
            token = {
                "access_token": result["access_token"],
                "name": claims.get("name", "User"),
                "username": claims.get("preferred_username", ""),
            }
            st.session_state["auth_token"] = token
            st.query_params.clear()
            st.rerun()
        else:
            st.error(f"Sign-in failed: {result.get('error_description', result.get('error'))}")
            st.stop()

    # Step 1: not signed in -> render the sign-in gate.
    auth_url = app.get_authorization_request_url(
        scopes=scopes, redirect_uri=cfg["redirect_uri"],
    )
    st.markdown("## 🔐 Sign in required")
    st.write("This is an internal tool secured with your Microsoft work account.")
    st.link_button("Sign in with Microsoft", auth_url, type="primary", use_container_width=True)
    st.stop()


def auth_headers() -> dict:
    token = st.session_state.get("auth_token")
    return {"Authorization": f"Bearer {token['access_token']}"} if token else {}


def signed_in_user() -> dict | None:
    return st.session_state.get("auth_token")
