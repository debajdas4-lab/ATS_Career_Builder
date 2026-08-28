"""FastAPI backend for ATS Career Builder — Enterprise Edition.

Clean, versioned REST surface with structured logging, input validation and
consistent error envelopes. No candidate-specific data is hardcoded anywhere;
every response is derived at runtime from the uploaded resume + JD.
"""

from __future__ import annotations

import logging
import time
import truststore
truststore.inject_into_ssl()

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core import __version__, config
from core.config import MAX_JD_CHARS, MAX_RESUME_BYTES
from core.docx_export import build_docx
from core.parsing import extract_resume_text, fetch_job_description
from core.pipeline import run_career_guide
from core.research import build_research_pack
from core.scoring import score_resume

from .auth import require_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("ats.api")

app = FastAPI(title="ATS Career Builder — Enterprise", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # internal tool; tighten per environment via a proxy
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.time() - start):.3f}"
    return response


# --------------------------------------------------------------------------- #
# Schemas                                                                      #
# --------------------------------------------------------------------------- #
class ScoreRequest(BaseModel):
    resume_text: str = Field(min_length=40)
    job_description: str = Field(min_length=40)


class ExportDocxRequest(BaseModel):
    resume_text: str = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@app.get("/")
def health() -> dict:
    return {
        "status": "Running",
        "application": "ATS Career Builder — Enterprise",
        "version": __version__,
        "auth_enabled": config.auth_enabled(),
    }


@app.get("/auth/config")
def auth_config() -> dict:
    """Public metadata the UI uses to drive the MSAL sign-in flow."""
    return {
        "auth_enabled": config.auth_enabled(),
        "tenant_id": config.AZURE_TENANT_ID,
        "ui_client_id": config.AZURE_UI_CLIENT_ID,
        "authority": config.authority(),
        "redirect_uri": config.AZURE_REDIRECT_URI,
        "api_scope": config.AZURE_API_SCOPE,
    }


@app.get("/me")
def me(user: dict = Depends(require_user)) -> dict:
    """Return the authenticated caller's identity claims (or a dev stub)."""
    return {
        "name": user.get("name"),
        "username": user.get("preferred_username") or user.get("upn") or user.get("email"),
        "auth": user.get("auth", "entra-id"),
    }


@app.post("/v3/career-guide")
async def career_guide(
    resume: UploadFile = File(...),
    job_description: str = Form(""),
    job_url: str = Form(""),
    company_url: str = Form(""),
    leadership_url: str = Form(""),
    market_urls: str = Form(""),
    market_query: str = Form(""),
    linkedin_profile: str = Form(""),
    naukri_profile: str = Form(""),
    user: dict = Depends(require_user),
) -> dict:
    content = await resume.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume file exceeds the configured size limit.")
    try:
        resume_text = extract_resume_text(resume.filename or "resume.txt", content)
        jd = (job_description or "").strip() or fetch_job_description(job_url.strip())
        jd = jd[:MAX_JD_CHARS]
        if len(jd) < 40:
            raise ValueError("Provide a job description as text or a public job URL.")
        parsed_market_urls = [u.strip() for u in market_urls.splitlines() if u.strip()]
        result = run_career_guide(
            resume_text=resume_text,
            job_description=jd,
            job_url=job_url.strip(),
            company_url=company_url.strip(),
            leadership_url=leadership_url.strip(),
            market_urls=parsed_market_urls,
            market_query=market_query.strip(),
            linkedin_profile=linkedin_profile,
            naukri_profile=naukri_profile,
        )
        log.info("career-guide ok: mode=%s before=%s after=%s",
                 result["generation_mode"], result["score_before"], result["score_after"])
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        log.exception("career-guide failed")
        raise HTTPException(500, f"Career Guide failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/score-resume")
def score(request: ScoreRequest, user: dict = Depends(require_user)) -> dict:
    try:
        return {"status": "success", "ats_analysis": score_resume(request.resume_text, request.job_description)}
    except Exception as exc:
        raise HTTPException(500, f"Score failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/research")
def research(company_url: str = Form(""), leadership_url: str = Form(""),
             market_urls: str = Form(""), market_query: str = Form(""),
             user: dict = Depends(require_user)) -> dict:
    parsed = [u.strip() for u in market_urls.splitlines() if u.strip()]
    if not any([company_url.strip(), leadership_url.strip(), parsed, market_query.strip()]):
        return {"status": "success", "research": {}}
    try:
        pack = build_research_pack(company_url.strip(), leadership_url.strip(), parsed, market_query.strip())
        return {"status": "success", "research": pack}
    except Exception as exc:
        return {"status": "partial", "research": {"research_warning": f"{type(exc).__name__}: {exc}"}}


@app.post("/v3/export-docx")
def export_docx(request: ExportDocxRequest, user: dict = Depends(require_user)) -> Response:
    return Response(
        content=build_docx(request.resume_text),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=ats-optimized-resume.docx"},
    )
