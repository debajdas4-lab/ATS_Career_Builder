from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.config import MAX_RESUME_BYTES
from core.docx_export import build_docx
from core.graph import optimize_resume
from core.career_graph import run_career_guide
from core.research import build_research_pack
from core.parsing import extract_resume_text, fetch_job_description

app = FastAPI(title="ATS Career Builder V3", version="3.1.0")


class OptimizeTextRequest(BaseModel):
    resume_text: str = Field(min_length=80)
    job_description: str = Field(min_length=80)


class ExportDocxRequest(BaseModel):
    resume_text: str = Field(min_length=1)


class CareerGuideTextRequest(BaseModel):
    resume_text: str = Field(min_length=80)
    job_description: str = Field(min_length=80)
    job_url: str = ""
    company_url: str = ""
    leadership_url: str = ""
    market_urls: list[str] = Field(default_factory=list)
    market_query: str = ""
    linkedin_profile: str = ""
    naukri_profile: str = ""


def _result(resume_text: str, job_description: str) -> dict:
    state = optimize_resume(resume_text, job_description)
    return {
        "status": "success",
        "ats_analysis": state.get("analysis", {}),
        "keywords": state.get("keywords", []),
        "optimized_resume": state.get("optimized_resume", ""),
        "cover_note": state.get("cover_note", ""),
        "warnings": state.get("warnings", []),
    }


def _fallback_cover_letter(state: dict) -> str:
    profile = state.get("candidate_profile") or {}
    job = state.get("job_spec") or {}
    headline = str(profile.get("headline") or "experienced professional").strip()
    role = str(job.get("title") or job.get("role") or "the advertised role").strip()
    skills = job.get("keywords") or []
    skills_text = ", ".join(str(x) for x in skills[:5] if str(x).strip()) if isinstance(skills, list) else ""
    fit_line = f" The role's emphasis on {skills_text} aligns with areas highlighted in my professional background." if skills_text else ""
    return (f"Dear Hiring Manager,\n\nI am writing to express my interest in {role}. My background as {headline} has given me experience working across complex initiatives, cross-functional stakeholders, delivery governance, and business outcomes.{fit_line}\n\nI would welcome the opportunity to discuss how the experience documented in my resume can support the priorities of this role. This letter is intentionally grounded in the evidence provided in my application materials.\n\nSincerely,\nCandidate")


def _ensure_v3_artifacts(state: dict, *, company_url: str = "", leadership_url: str = "", market_urls: list[str] | None = None, market_query: str = "") -> dict:
    state = dict(state or {})
    research = state.get("research")
    research_requested = bool(company_url or leadership_url or (market_urls or []) or market_query)
    if research_requested and (not isinstance(research, dict) or not research):
        try:
            state["research"] = build_research_pack(company_url=company_url, leadership_url=leadership_url, market_urls=market_urls or [], market_query=market_query)
        except Exception as exc:
            state["research"] = {"company_profile": ({"name": "Company Research", "overview": "The company URL was supplied, but public-page research was unavailable during this run.", "url": company_url} if company_url else {}), "leadership": [], "strategy": [], "recent_signals": [], "competitors": [], "sources": ([{"type": "company", "label": "Company Website", "url": company_url}] if company_url else []), "market_signals": [], "research_warning": f"Research fallback used: {type(exc).__name__}: {exc}"}
    if not str(state.get("cover_letter") or "").strip():
        state["cover_letter"] = _fallback_cover_letter(state)
    return state


def _career_result(state: dict) -> dict:
    research = state.get("research") or {}
    if not isinstance(research, dict):
        research = {}
    return {
        "status": "success",
        "candidate_profile": state.get("candidate_profile", {}),
        "job_spec": state.get("job_spec", {}),
        "research": research,
        "ats_analysis": state.get("ats_analysis", {}),
        "job_fit": state.get("job_fit", {}),
        "keyword_gap": state.get("keyword_gap", {}),
        "skill_gap": state.get("skill_gap", {}),
        "experience_gap": state.get("experience_gap", {}),
        "career_gap": state.get("career_gap", {}),
        "optimized_resume": state.get("optimized_resume", ""),
        "cover_letter": state.get("cover_letter", ""),
        "linkedin_optimization": state.get("linkedin_optimization", {}),
        "naukri_optimization": state.get("naukri_optimization", {}),
        "interview_kit": state.get("interview_kit", {}),
        "career_roadmap": state.get("career_roadmap", {}),
        "warnings": state.get("warnings", []),
        "sources": research.get("sources", []),
    }


@app.get("/")
def health() -> dict:
    return {"status": "Running", "application": "ATS Career Guide", "version": "3.1.0"}


@app.post("/v1/optimize")
async def optimize(
    resume: UploadFile = File(...),
    job_description: str = Form(""),
    job_url: str = Form(""),
) -> dict:
    content = await resume.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume file exceeds the configured size limit.")
    try:
        resume_text = extract_resume_text(resume.filename or "resume.txt", content)
        jd = job_description.strip() or await fetch_job_description(job_url.strip())
        if len(jd) < 80:
            raise ValueError("Provide a job description as text or a URL.")
        return _result(resume_text, jd)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Resume optimization failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v1/optimize-text")
def optimize_text(request: OptimizeTextRequest) -> dict:
    return _result(request.resume_text, request.job_description)


@app.post("/v2/career-guide/text")
def career_guide_text(request: CareerGuideTextRequest) -> dict:
    try:
        state = run_career_guide(
            resume_text=request.resume_text,
            job_description=request.job_description,
            job_url=request.job_url,
            company_url=request.company_url,
            leadership_url=request.leadership_url,
            market_urls=request.market_urls,
            market_query=request.market_query,
            linkedin_profile=request.linkedin_profile,
            naukri_profile=request.naukri_profile,
        )
        return _career_result(state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Career Guide text workflow failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/career-guide")
async def career_guide_v3(
    resume: UploadFile = File(...),
    analysis_mode: str = Form("Fast Resume"),
    job_description: str = Form(""),
    job_url: str = Form(""),
    company_url: str = Form(""),
    leadership_url: str = Form(""),
    market_urls: str = Form(""),
    market_query: str = Form(""),
    linkedin_profile: str = Form(""),
    naukri_profile: str = Form(""),
) -> dict:
    content = await resume.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume file exceeds the configured size limit.")
    try:
        resume_text = extract_resume_text(resume.filename or "resume.txt", content)
        jd = job_description.strip() or await fetch_job_description(job_url.strip())
        if len(jd) < 80:
            raise ValueError("Provide a job description as text or a URL.")
        parsed_market_urls = [u.strip() for u in market_urls.splitlines() if u.strip()]
        state = run_career_guide(
            resume_text=resume_text,
            job_description=jd,
            job_url=job_url.strip(),
            company_url=company_url.strip(),
            leadership_url=leadership_url.strip(),
            market_urls=parsed_market_urls,
            market_query=market_query.strip(),
            linkedin_profile=linkedin_profile,
            naukri_profile=naukri_profile,
            analysis_mode=analysis_mode,
        )
        state = _ensure_v3_artifacts(state, company_url=company_url.strip(), leadership_url=leadership_url.strip(), market_urls=parsed_market_urls, market_query=market_query.strip())
        return _career_result(state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Career Guide workflow failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/score-resume")
def score_resume_v3(request: OptimizeTextRequest) -> dict:
    try:
        return _result(request.resume_text, request.job_description)
    except Exception as exc:
        raise HTTPException(500, f"Resume re-score failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/export-docx")
def export_docx_v3(request: ExportDocxRequest) -> Response:
    return Response(
        content=build_docx(request.resume_text),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=ats-optimized-resume.docx"},
    )


@app.post("/v1/export-docx")
def export_docx_legacy(request: ExportDocxRequest) -> Response:
    return export_docx_v3(request)
