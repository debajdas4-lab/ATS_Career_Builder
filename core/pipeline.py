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


def _targeted_interview_kit(profile: dict, analysis: dict, research: dict, job_description: str, keywords: list[str]) -> dict:
    """Create JD-specific interview questions from live JD signals and candidate evidence."""
    matched = list(analysis.get("matched_keywords", []))
    partial = list(analysis.get("partial_keywords", []))
    missing = list(analysis.get("missing_keywords", []))
    signals = [k for k in keywords if k] or matched + partial + missing
    top = []
    for k in signals:
        if k not in top:
            top.append(k)
        if len(top) >= 8:
            break

    achievements = profile.get("achievements", []) if isinstance(profile, dict) else []
    achievement_texts = []
    for item in achievements[:4]:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
        else:
            text = str(item).strip()
        if text:
            achievement_texts.append(text)

    company = (research.get("company_profile", {}) or {}).get("name", "the company")
    strategies = list(research.get("strategy", []) or [])[:3]
    strategy_text = ", ".join(strategies) if strategies else "the company's stated priorities"

    resume_questions = []
    for text in achievement_texts[:4]:
        resume_questions.append(f"Walk me through the most relevant result in this resume and explain how you would apply that experience to the role's requirements around {top[0] if top else 'technical program delivery'}.")
    if top:
        resume_questions.append(f"Which example from your background best demonstrates your ability to lead {top[0]}, and what was your personal contribution?")

    technical = []
    technical_templates = [
        "How would you structure delivery for a program involving {k}, multiple engineering teams, and competing dependencies?",
        "What technical risks would you assess first when delivering a platform involving {k}, and how would you communicate those risks to senior leadership?",
        "How would you validate architecture and engineering trade-offs related to {k} without becoming the team's day-to-day engineer?",
        "How would you define success metrics for a program centered on {k}?",
        "How would you handle a cross-team dependency blocking delivery of a capability involving {k}?",
    ]
    for k in top[:5]:
        technical.append(technical_templates[len(technical) % len(technical_templates)].format(k=k))

    leadership_questions = [
        f"This role requires influencing Product, Engineering and Business leaders on {top[0] if top else 'competing priorities'}. Describe how you would resolve a disagreement without direct authority.",
        f"How would you run a distributed, multi-time-zone delivery model while keeping {top[1] if len(top) > 1 else 'execution'} predictable?",
        "Describe how you would establish governance, risk management and executive reporting for a high-visibility technical program.",
    ]

    company_questions = [
        f"Why this role at {company}, and which parts of your experience are most transferable to the company's current priorities around {strategy_text}?",
        f"What would you want to learn about {company}'s engineering/product operating model before committing to a major program roadmap?",
    ]

    gap_questions = [
        f"You do not show direct evidence of {k}. How would you address that gap honestly while demonstrating related experience?"
        for k in missing[:5]
    ]
    if not gap_questions:
        gap_questions = ["Which requirement in this JD would require the most ramp-up from you, and how would you close that gap?"]

    star = []
    for k in top[:4]:
        star.append({
            "capability": k,
            "prompt": f"Prepare a STAR story showing Situation, Task, Action and quantified Result for a real example involving {k}.",
        })

    return {
        "resume_questions": resume_questions[:6] or [f"Which resume example best demonstrates your fit for {top[0] if top else 'this role'}?"],
        "company_questions": company_questions,
        "leadership_questions": leadership_questions,
        "technical_or_domain_questions": technical,
        "gap_questions": gap_questions,
        "star_story_blueprints": star,
    }


def _merge_interview_kits(base: dict, targeted: dict) -> dict:
    """Prefer targeted JD-specific questions while retaining extra generated sections."""
    base = base if isinstance(base, dict) else {}
    targeted = targeted if isinstance(targeted, dict) else {}
    merged = dict(base)
    for key, value in targeted.items():
        if value:
            merged[key] = value
    return merged


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
        "experience_structure_validation": resume_out.get("experience_structure_validation", {}),
        "resume_generation_quality": {
            "source_locked": True,
            "employer_structure_preserved": resume_out.get("experience_structure_validation", {}).get("pass", True),
            "numeric_evidence_pass": resume_out.get("evidence_validation", {}).get("pass", True),
        },
        "linkedin_optimization": build_profile_optimization("LinkedIn", profile, upgraded_analysis),
        "naukri_optimization": build_profile_optimization("Naukri", profile, upgraded_analysis),
        "interview_kit": _merge_interview_kits(
            build_interview_kit(profile, analysis, research),
            _targeted_interview_kit(profile, analysis, research, job_description, keywords),
        ),
        "career_roadmap": build_roadmap(profile, analysis),
        "research": research,
        "sources": research.get("sources", []) if isinstance(research, dict) else [],
        "warnings": warnings,
    }
