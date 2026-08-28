# ATS Career Builder — Enterprise Edition (v4.0)

A refactor of the ATS Career Builder into a clean, modular, **fully dynamic**
enterprise application. No hardcoded candidate data, no fixed skills dictionary,
and every tab produces real, evidence-based output.

---

## What changed vs. V3

| Area | V3 (before) | Enterprise (now) |
|------|-------------|------------------|
| **Keyword matching** | Fixed `ALIASES` dictionary — only understood a handful of pre-listed skills | **Dynamic RAKE + technical-token extraction** from the *requirements* section of any JD. Adapts to any role/industry with zero code changes |
| **Hardcoded values** | Candidate name (`Deba Jyoti Das`) baked into fallbacks; static score paths | **Zero hardcoding.** Name, contact, skills, achievements all extracted at runtime from the uploaded resume |
| **ATS score** | Opaque, didn't move after upgrade | **Transparent weighted blend**: 65% keyword coverage + 15% semantic (TF-IDF cosine) + 20% section completeness. Before/after dashboard shows a real delta |
| **Resume upgrade** | Crowded; could lose content; depended on a paid LLM (caused 413/429/timeout) | **Premium layout** that preserves all original content and *adds* evidenced keywords. Legitimately closes “wording gaps.” Works with **or without** an LLM |
| **Tabs** | Some returned empty | **All tabs guaranteed** (Fit & Gaps, Resume, LinkedIn, Naukri, Interview Kit, Career Roadmap, Research) with deterministic fallbacks |
| **Architecture** | Flat files, missing `core/` package | Clean layered package: `core/` (domain) · `api/` (FastAPI) · `app.py` (UI) |
| **Truthfulness** | — | **Evidence guard** flags any numeric claim not present in the source resume |

---

## Architecture

```
ATS_Career_Builder_Enterprise/
├── app.py                 # Streamlit UI (premium navy/violet theme + all tabs)
├── api/
│   └── main.py            # FastAPI service (/v3/career-guide, /score-resume, /export-docx, /research)
├── core/                  # Pure, testable domain logic (no web deps)
│   ├── config.py          # Env-driven settings (nothing hardcoded)
│   ├── keywords.py        # Dynamic RAKE keyword extraction + JD signal isolation
│   ├── scoring.py         # Explainable ATS score + wording-gap detection
│   ├── profile.py         # Candidate profile extraction (name/contact/skills/metrics)
│   ├── resume_builder.py  # Premium resume (LLM path + deterministic path) + evidence guard
│   ├── suggestions.py     # LinkedIn / Naukri / Interview Kit / Roadmap artefacts
│   ├── research.py        # Opt-in public-page company/market research
│   ├── parsing.py         # PDF / DOCX / TXT + JD URL ingestion
│   ├── docx_export.py     # Premium single-column DOCX
│   ├── llm.py             # Optional OpenAI-compatible LLM (Groq/OpenAI/Azure)
│   ├── pipeline.py        # Orchestrator
│   └── utils.py           # Shared text helpers
├── assets/ats_career_guide_banner.png
├── tests/test_engine.py   # Proves dynamism + no hardcoding
├── requirements.txt
└── .env.example
```

**Data flow:** `resume + JD → keywords (RAKE) → candidate profile → ATS analysis
→ premium resume → re-score (before/after) → all tab artefacts`.

---

## Quick start

```bash
# 1) Install
python -m pip install -r requirements.txt

# 2) (optional) configure
cp .env.example .env        # runs fine even if you skip this

# 3) Start the API
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# 4) Start the UI (new terminal)
python -m streamlit run app.py
```

Open http://localhost:8501, upload a resume (PDF/DOCX/TXT), paste a JD or a
public job URL, and click **Analyze job & build career guide**.

---

## Runs with or without an LLM

- **No key configured (default):** a high-quality **deterministic** builder
  produces the resume and all artefacts. Zero cost, no rate limits — this is
  what removes the previous 413/429/timeout failures.
- **`LLM_API_KEY` set:** the same pipeline uses an OpenAI-compatible endpoint
  (Groq / OpenAI / Azure OpenAI) for richer prose. Model, endpoint and token
  budget are all env-driven.

---

## How the ATS score works (transparent)

```
score = 0.65 * keyword_coverage       # dynamic JD keywords evidenced in resume
      + 0.15 * semantic_similarity     # TF-IDF cosine(resume, JD), normalised
      + 0.20 * section_completeness    # summary / experience / skills / education present
```

Each keyword decision carries the **evidence snippet** that justified it, so the
UI can explain *why* a score was given. A resume aligned to a JD scores high; the
same resume against an unrelated JD scores low (validated in tests: 79 vs 21).

---

## Azure AD / Microsoft Entra ID SSO

The app ships with optional **Entra ID single sign-on**. It stays **open for
local dev** (`AUTH_ENABLED=false`) and becomes a **protected resource** the
moment you enable it — no code changes required.

**How it works**
- **UI (`core/ui_auth.py`)** runs the OAuth2 **Authorization Code** flow via
  **MSAL**: users click *Sign in with Microsoft*, authenticate against your
  tenant, and the UI receives an access token for the API's scope.
- **API (`api/auth.py`)** treats itself as a resource server: every request must
  carry a valid **Bearer token**, which is validated cryptographically
  (**RS256 via tenant JWKS**) with issuer/audience/expiry checks.
- Optional **allow-lists** (`AUTH_ALLOWED_USERS`, `AUTH_ALLOWED_GROUPS`) restrict
  access to named users or AAD group object IDs.

**One-time Azure setup**
1. Create **two app registrations** (or one multi-purpose): an **API** app
   (expose a scope `access_as_user`) and a **UI** confidential client (add a web
   redirect URI, e.g. `https://<ui-host>` and create a client secret).
2. Grant the UI app delegated permission to the API scope; grant admin consent.
3. Set env vars (`.env` / container / Render dashboard):
   ```
   AUTH_ENABLED=true
   AZURE_TENANT_ID=<tenant-guid>
   AZURE_CLIENT_ID=<API app client id>
   AZURE_UI_CLIENT_ID=<UI app client id>
   AZURE_CLIENT_SECRET=<UI app secret>
   AZURE_REDIRECT_URI=https://<ui-host>
   AZURE_API_SCOPE=api://<API app client id>/access_as_user
   # optional
   AUTH_ALLOWED_GROUPS=<aad-group-object-id>
   ```

Endpoints: `GET /auth/config` (public, drives UI sign-in) · `GET /me`
(returns the caller's identity) · all `/v3/*` routes require a valid token.

---

## Deployment

### Docker (local / on-prem)

One image runs either service, selected by the `SERVICE` env var (`api`|`ui`).

```bash
cp .env.example .env          # set AUTH_* and LLM_API_KEY as needed
docker compose up --build
#   UI  -> http://localhost:8501
#   API -> http://localhost:8000
```

The image runs as a **non-root** user and includes a **healthcheck**.

### Render.com (managed, internal team tool)

`render.yaml` provisions two web services (`ats-career-api`, `ats-career-ui`)
from the same Dockerfile. The UI's `RESUME_API_URL` is auto-wired to the API
service; set the Azure secrets and `LLM_API_KEY` in the dashboard. You can still
deploy without Docker using plain start commands:

- **API:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- **UI:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
  with `RESUME_API_URL` pointing at the API service.

---

## Tests

```bash
python tests/test_engine.py     # or: python -m pytest -q
```

Asserts (1) profiles are extracted, not hardcoded; (2) keywords change per JD;
(3) an aligned resume outscores a misaligned one; (4) every tab is populated and
the upgrade never lowers the score.
