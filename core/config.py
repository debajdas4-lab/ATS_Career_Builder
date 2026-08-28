"""Centralised, environment-driven configuration.

Enterprise principle: nothing that changes between environments (keys, limits,
model names, feature flags) is hardcoded in business logic. Everything is read
from the environment with safe defaults so the app runs locally out-of-the-box.
"""
from __future__ import annotations

import os


def _get(name: str, default: str) -> str:
    return str(os.getenv(name, default))


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    return str(os.getenv(name, str(default))).strip().lower() in {"1", "true", "yes", "on"}


from dotenv import load_dotenv
load_dotenv()


# ---- Service limits -------------------------------------------------------
MAX_RESUME_BYTES: int = _get_int("MAX_RESUME_BYTES", 8 * 1024 * 1024)  # 8 MB
MAX_JD_CHARS: int = _get_int("MAX_JD_CHARS", 40_000)
REQUEST_TIMEOUT: int = _get_int("REQUEST_TIMEOUT", 180)

# ---- Feature flags --------------------------------------------------------
ENABLE_COMPANY_RESEARCH: bool = _get_bool("ENABLE_COMPANY_RESEARCH", True)

# ---- Keyword / scoring tuning (data-driven, not per-candidate) ------------
MAX_JD_KEYWORDS: int = _get_int("MAX_JD_KEYWORDS", 30)
PARTIAL_MATCH_THRESHOLD: float = float(_get("PARTIAL_MATCH_THRESHOLD", "0.72"))
FULL_MATCH_THRESHOLD: float = float(_get("FULL_MATCH_THRESHOLD", "0.90"))

# ATS score is a transparent weighted blend of three dynamic signals.
WEIGHT_KEYWORD_COVERAGE: float = float(_get("WEIGHT_KEYWORD_COVERAGE", "0.65"))
WEIGHT_SEMANTIC_SIMILARITY: float = float(_get("WEIGHT_SEMANTIC_SIMILARITY", "0.15"))
WEIGHT_SECTION_COMPLETENESS: float = float(_get("WEIGHT_SECTION_COMPLETENESS", "0.20"))

# Raw TF-IDF cosine between a full resume and a JD rarely exceeds ~0.35, so we
# normalise against this reference to turn it into a fair 0-1 signal.
SEMANTIC_REFERENCE: float = float(_get("SEMANTIC_REFERENCE", "0.35"))

# ---- Optional LLM (OpenAI-compatible, incl. Groq / Azure OpenAI) ----------
# If no key is present the app degrades gracefully to a deterministic builder,
# so it is always runnable without a paid provider.
LLM_API_KEY: str = _get("LLM_API_KEY", os.getenv("GROQ_API_KEY", os.getenv("OPENAI_API_KEY", "")))
LLM_BASE_URL: str = _get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL: str = _get("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_MAX_TOKENS: int = _get_int("LLM_MAX_TOKENS", 1800)
LLM_TEMPERATURE: float = float(_get("LLM_TEMPERATURE", "0.2"))

API_URL: str = _get("RESUME_API_URL", "http://localhost:8000").rstrip("/")

# ---- Azure AD / Microsoft Entra ID SSO ------------------------------------
# When AUTH_ENABLED is false (default) the app runs open for local dev. Set it
# to true in shared/production environments and provide the tenant + app IDs.
AUTH_ENABLED: bool = _get_bool("AUTH_ENABLED", False)
AZURE_TENANT_ID: str = _get("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID: str = _get("AZURE_CLIENT_ID", "")               # API app registration (audience)
AZURE_CLIENT_SECRET: str = _get("AZURE_CLIENT_SECRET", "")       # UI confidential client secret
AZURE_UI_CLIENT_ID: str = _get("AZURE_UI_CLIENT_ID", AZURE_CLIENT_ID)
AZURE_REDIRECT_URI: str = _get("AZURE_REDIRECT_URI", "http://localhost:8501")
# Scope the UI requests when calling the API (e.g. api://<client-id>/access_as_user).
AZURE_API_SCOPE: str = _get("AZURE_API_SCOPE", f"api://{AZURE_CLIENT_ID}/access_as_user" if AZURE_CLIENT_ID else "")
# Optional comma-separated allow-list of UPNs/emails or AAD group object IDs.
AUTH_ALLOWED_USERS: str = _get("AUTH_ALLOWED_USERS", "")
AUTH_ALLOWED_GROUPS: str = _get("AUTH_ALLOWED_GROUPS", "")

_AUTHORITY_BASE = _get("AZURE_AUTHORITY", "https://login.microsoftonline.com")


def authority() -> str:
    return f"{_AUTHORITY_BASE}/{AZURE_TENANT_ID}" if AZURE_TENANT_ID else _AUTHORITY_BASE


def openid_config_url() -> str:
    return f"{authority()}/v2.0/.well-known/openid-configuration"


def jwks_uri() -> str:
    return f"{authority()}/discovery/v2.0/keys"


def issuer() -> str:
    return f"{_AUTHORITY_BASE}/{AZURE_TENANT_ID}/v2.0" if AZURE_TENANT_ID else _AUTHORITY_BASE


def allowed_users() -> set[str]:
    return {u.strip().lower() for u in AUTH_ALLOWED_USERS.split(",") if u.strip()}


def allowed_groups() -> set[str]:
    return {g.strip() for g in AUTH_ALLOWED_GROUPS.split(",") if g.strip()}


def llm_enabled() -> bool:
    return bool(LLM_API_KEY.strip())


def auth_enabled() -> bool:
    return bool(AUTH_ENABLED and AZURE_TENANT_ID and AZURE_CLIENT_ID)
