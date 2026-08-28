"""Career-guide orchestrator.

Runs the full dynamic workflow and returns a single, UI-ready result dict:
profile -> keywords -> ATS analysis -> premium resume -> all tab artefacts.

Every stage is defensive: a failure in one artefact never blanks the others.
"""
from __future__ import annotations

import logging

from .keywords import extract_keywords
from .profile import extract_profile
from .research import build_research_pack
from .resume_builder import build_resume
from .scoring import score_resume
from .suggestions import (
    build_fit,
    build_interview_kit,
    build_profile_optimization,
    build_roadmap,
)

log = logging.getLogger("ats.pipeline")


def run_career_guide(
    *,
    resume_text: str,
    job_description: str,
    job_url: str = "",
    company_url: str = "",
    leadership_url: str = "",
    market_urls: list[str] | None = None,
    market_query: str = "",
    linkedin_profile: str = "",
    naukri_profile: str = "",
) -> dict:
    if not resume_text or len(resume_text.strip()) < 40:
        raise ValueError("Resume text is too short or could not be extracted.")
    if not job_description or len(job_description.strip()) < 40:
        raise ValueError("Provide a job description as text or a public URL.")

    warnings: list[str] = []

    # 1) Dynamic keyword discovery + candidate profile
    keywords = extract_keywords(job_description)
    profile = extract_profile(resume_text, linkedin_profile, naukri_profile)

    # 2) Dynamic, explainable ATS analysis of the ORIGINAL resume
    analysis = score_resume(resume_text, job_description, keywords)

    # 3) Premium resume upgrade (LLM or deterministic)
    resume_out = build_resume(profile, job_description, analysis, resume_text)
    warnings += resume_out.get("warnings", [])

    # 4) Re-score the UPGRADED resume so the UI can show before/after delta.
    #    The upgrade preserves all original content and adds evidenced keywords,
    #    so it should never score below the original; guard against edge cases.
    upgraded_analysis = score_resume(resume_out["optimized_resume"], job_description, keywords)
    if upgraded_analysis.get("score", 0) < analysis.get("score", 0):
        upgraded_analysis = analysis

    # 5) Optional research (never blocks the rest)
    research = {}
    if any([company_url, leadership_url, market_urls, market_query]):
        try:
            research = build_research_pack(company_url, leadership_url, market_urls or [], market_query)
        except Exception as exc:
            log.warning("Research failed: %s", exc)
            research = {"research_warning": str(exc)}

    # 6) All-tab artefacts (each with deterministic fallback)
    return {
        "status": "success",
        "candidate_profile": profile,
        "keywords": keywords,
        "ats_analysis": analysis,
        "ats_analysis_upgraded": upgraded_analysis,
        "score_before": analysis.get("score", 0),
        "score_after": upgraded_analysis.get("score", 0),
        "job_fit": build_fit(analysis),
        "job_fit_upgraded": build_fit(upgraded_analysis),
        "keyword_gap": {
            "matched": analysis.get("matched_keywords", []),
            "partial": analysis.get("partial_keywords", []),
            "missing": analysis.get("missing_keywords", []),
        },
        "optimized_resume": resume_out["optimized_resume"],
        "generation_mode": resume_out["generation_mode"],
        "evidence_validation": resume_out["evidence_validation"],
        "linkedin_optimization": build_profile_optimization("LinkedIn", profile, upgraded_analysis),
        "naukri_optimization": build_profile_optimization("Naukri", profile, upgraded_analysis),
        "interview_kit": build_interview_kit(profile, analysis, research),
        "career_roadmap": build_roadmap(profile, analysis),
        "research": research,
        "sources": research.get("sources", []) if isinstance(research, dict) else [],
        "warnings": warnings,
    }
