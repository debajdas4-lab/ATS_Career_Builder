from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.config import MAX_RESUME_BYTES
from core.docx_export import build_docx
from core.graph import optimize_resume
from core.career_tools import build_job_spec, score_fit
from core.career_graph import run_career_guide
from core.parsing import extract_resume_text, fetch_job_description
from core.research import build_research_pack

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


def _ats_result(resume_text: str, job_description: str) -> dict:
    """Use the same scoring engine for both current and upgraded ATS scores."""
    spec = build_job_spec(job_description)
    analysis = score_fit(resume_text, spec)
    return {
        "status": "success",
        "ats_analysis": analysis,
        "job_spec": spec,
    }


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
    role = str(job.get("title") or job.get("role") or "the advertised role").strip()
    headline = str(profile.get("headline") or "an experienced technology and transformation leader").strip()
    keywords = job.get("keywords") or []
    focus = ", ".join(str(x) for x in keywords[:5] if str(x).strip())
    focus_sentence = (
        f"My background aligns particularly well with the role's focus on {focus}."
        if focus else
        "My background aligns with the role's focus on delivering measurable business and technology outcomes."
    )
    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my interest in {role}. As {headline}, I bring extensive experience leading complex, cross-functional technology and transformation initiatives from strategy through delivery. "
        f"{focus_sentence}\n\n"
        "I would welcome the opportunity to discuss how my experience can support the priorities of this role and organization. "
        "This letter is intentionally grounded in the experience and evidence provided in my application materials.\n\n"
        "Sincerely,\nDeba Jyoti Das"
    )



def _fallback_linkedin(state: dict) -> dict:
    profile = state.get("candidate_profile") or {}
    job = state.get("job_spec") or {}
    headline = str(profile.get("headline") or "Technical Program & Transformation Leader").strip()
    summary = str(
        profile.get("summary")
        or profile.get("professional_summary")
        or "Experienced technology and transformation leader with a track record of leading complex cross-functional programs and delivering measurable business outcomes."
    ).strip()
    keywords = [str(x) for x in (job.get("keywords") or [])[:15] if str(x).strip()]
    return {
        "headline": headline,
        "about_or_summary": summary,
        "skills": keywords,
        "keywords": keywords,
        "changes": [
            "Align the headline to the target role using only evidenced experience.",
            "Prioritize the strongest program, technical and leadership evidence from the resume.",
            "Use concise achievement language and verified outcomes only.",
        ],
    }


def _fallback_naukri(state: dict) -> dict:
    profile = state.get("candidate_profile") or {}
    job = state.get("job_spec") or {}
    headline = str(profile.get("headline") or "Technical Program & Transformation Leader").strip()
    summary = str(
        profile.get("summary")
        or profile.get("professional_summary")
        or "Experienced technology and transformation leader focused on complex program delivery, governance and measurable business outcomes."
    ).strip()
    keywords = [str(x) for x in (job.get("keywords") or [])[:15] if str(x).strip()]
    return {
        "title": headline,
        "key_summary": summary,
        "core_competencies": keywords,
        "keywords": keywords,
        "changes": [
            "Keep the profile concise and aligned to the target role.",
            "Retain employer-wise experience, dates and only verified achievements.",
        ],
    }


def _ensure_v3_artifacts(
    state: dict,
    *,
    company_url: str = "",
    leadership_url: str = "",
    market_urls: list[str] | None = None,
    market_query: str = "",
) -> dict:
    state = dict(state or {})
    market_urls = market_urls or []

    research_requested = bool(
        company_url.strip()
        or leadership_url.strip()
        or market_urls
        or market_query.strip()
    )
    research = state.get("research")

    if research_requested and (not isinstance(research, dict) or not research.get("sources") and not research.get("company_profile") and not research.get("leadership") and not research.get("market_signals")):
        try:
            research = build_research_pack(
                company_url=company_url.strip(),
                leadership_url=leadership_url.strip(),
                market_urls=market_urls,
                market_query=market_query.strip(),
            )
        except Exception as exc:
            research = None
            research_error = f"Research fallback used: {type(exc).__name__}: {exc}"
        else:
            research_error = ""

        if not isinstance(research, dict):
            research = {}

        if not research.get("sources") and not research.get("company_profile") and not research.get("leadership") and not research.get("market_signals"):
            research = {
                "company_profile": (
                    {
                        "name": "Company Research",
                        "overview": "The supplied research input was received, but detailed public-page content was unavailable during this run.",
                        "url": company_url.strip(),
                    }
                    if company_url.strip() else {}
                ),
                "leadership": [],
                "strategy": [],
                "recent_signals": [],
                "competitors": [],
                "sources": (
                    [{"type": "company", "label": "Company Website", "url": company_url.strip()}]
                    if company_url.strip() else []
                ),
                "market_signals": [],
            }
            if research_error:
                research["research_warning"] = research_error

        state["research"] = research

    # Guarantee profile artifacts even if the main LLM response omitted them.
    if not isinstance(state.get("linkedin_optimization"), dict) or not state.get("linkedin_optimization"):
        state["linkedin_optimization"] = _fallback_linkedin(state)

    if not isinstance(state.get("naukri_optimization"), dict) or not state.get("naukri_optimization"):
        state["naukri_optimization"] = _fallback_naukri(state)

    # Guarantee a cover letter without fabricating quantified achievements.
    if not str(state.get("cover_letter") or "").strip():
        state["cover_letter"] = _fallback_cover_letter(state)
        warnings = list(state.get("warnings") or [])
        warnings.append("A grounded fallback cover letter was supplied because the primary cover-letter generation did not return content.")
        state["warnings"] = warnings

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
        "evidence_validation": state.get("evidence_validation", {}),
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
        state = _ensure_v3_artifacts(
            state,
            company_url=company_url.strip(),
            leadership_url=leadership_url.strip(),
            market_urls=parsed_market_urls,
            market_query=market_query.strip(),
        )

        # Canonicalize ATS/fit scoring at the API boundary so the V3 initial score
        # and the post-upgrade score use exactly the same scoring engine.
        canonical_ats = score_fit(resume_text, build_job_spec(jd))
        state["ats_analysis"] = canonical_ats
        state["job_fit"] = {
            "overall": canonical_ats.get("score", 0),
            "recommendation": canonical_ats.get("recommendation", "REVIEW FIT"),
            "strengths": canonical_ats.get("matched_keywords", []),
            "partial": canonical_ats.get("partial_keywords", []),
            "risks": canonical_ats.get("missing_keywords", []),
        }
        state["keyword_gap"] = {
            "matched": canonical_ats.get("matched_keywords", []),
            "partial": canonical_ats.get("partial_keywords", []),
            "missing": canonical_ats.get("missing_keywords", []),
        }
        return _career_result(state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Career Guide workflow failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/research")
def research_v3(company_url: str = Form(""), leadership_url: str = Form(""), market_urls: str = Form(""), market_query: str = Form("")) -> dict:
    parsed = [u.strip() for u in market_urls.splitlines() if u.strip()]
    requested = bool(company_url.strip() or leadership_url.strip() or parsed or market_query.strip())
    if not requested:
        return {"status":"success","research":{}}
    try:
        research = build_research_pack(company_url=company_url.strip(), leadership_url=leadership_url.strip(), market_urls=parsed, market_query=market_query.strip())
        if not isinstance(research, dict):
            research = _fallback_research(company_url.strip(), leadership_url.strip(), parsed, market_query.strip())
        return {"status":"success","research":research}
    except Exception as exc:
        return {"status":"partial","research":_fallback_research(company_url.strip(), leadership_url.strip(), parsed, market_query.strip()) | {"research_warning": f"Research fallback used: {type(exc).__name__}: {exc}"}}


@app.post("/v3/score-resume")
def score_resume_v3(request: OptimizeTextRequest) -> dict:
    try:
        return _ats_result(request.resume_text, request.job_description)
    except Exception as exc:
        raise HTTPException(500, f"Resume re-score failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/score-diagnostics")
def score_diagnostics(request: OptimizeTextRequest) -> dict:
    try:
        result = _ats_result(request.resume_text, request.job_description)
        analysis = result["ats_analysis"]
        return {
            "status": "success",
            "score": analysis.get("score", 0),
            "leadership_score": analysis.get("leadership_score", 0),
            "technical_score": analysis.get("technical_score", 0),
            "domain_score": analysis.get("domain_score", 0),
            "matched_keywords": analysis.get("matched_keywords", []),
            "partial_keywords": analysis.get("partial_keywords", []),
            "missing_keywords": analysis.get("missing_keywords", []),
            "recommendation": analysis.get("recommendation", "REVIEW FIT"),
            "evidence_map": analysis.get("evidence_map", {}),
        }
    except Exception as exc:
        raise HTTPException(500, f"Score diagnostics failed: {type(exc).__name__}: {exc}") from exc


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
