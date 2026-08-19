from __future__ import annotations

from datetime import datetime

from ..career_tools import build_job_spec, gap_analysis, score_fit
from ..config import ENABLE_COMPANY_RESEARCH
from ..evidence import evidence_guard, extract_candidate_profile
from ..llm import invoke_json, invoke_text
from ..prompts.templates import interview_prompt, profile_prompt, resume_prompt, roadmap_prompt


def log_agent(name: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting agent: {name}", flush=True)


def candidate_agent(state):
    log_agent("Candidate Intelligence")
    return {"candidate_profile": extract_candidate_profile(state.get("resume_text", ""), state.get("linkedin_profile", ""), state.get("naukri_profile", ""))}


def job_agent(state):
    log_agent("Job Intelligence")
    return {"job_spec": build_job_spec(state.get("job_description", ""), state.get("job_url", ""))}


def ats_agent(state):
    log_agent("Deterministic ATS Scoring")
    analysis = score_fit(state.get("resume_text", ""), state.get("job_spec", {}))
    gaps = gap_analysis(state.get("resume_text", ""), state.get("job_spec", {}))
    return {
        "ats_analysis": analysis,
        "job_fit": {"overall": analysis.get("score", 0), "recommendation": analysis.get("recommendation", "REVIEW FIT"), "strengths": gaps.get("strong", []), "partial": gaps.get("partial", []), "risks": gaps.get("missing", [])},
        "keyword_gap": {"matched": analysis.get("matched_keywords", []), "missing": analysis.get("missing_keywords", [])},
        "skill_gap": gaps,
    }


def local_strategy_agent(state):
    log_agent("TPM-Safe Local Strategy")
    job, ats, profile = state.get("job_spec", {}), state.get("ats_analysis", {}), state.get("candidate_profile", {})
    matched, missing = ats.get("matched_keywords", []), ats.get("missing_keywords", [])
    recruiter = {
        "recruiter_keywords": list(dict.fromkeys(job.get("keywords", []) + matched))[:30],
        "ats_keywords": job.get("keywords", [])[:30],
        "leadership_keywords": job.get("leadership_expectations", [])[:15],
        "technical_keywords": job.get("technical_requirements", [])[:15],
        "priority_terms_to_add": missing[:15],
        "unsupported_terms_to_avoid": missing[:15],
    }
    brand = {
        "executive_headline": profile.get("headline", ""),
        "leadership_themes": [x for x in job.get("leadership_expectations", []) if x in matched][:10],
        "value_proposition": profile.get("summary", "")[:550],
        "evidence_to_emphasize": profile.get("achievements", [])[:12],
        "positioning_risks": missing[:12],
    }
    achievement = {
        "priority_achievements": profile.get("achievements", [])[:18],
        "content_that_must_be_preserved": profile.get("experience_evidence", [])[:24],
        "unsupported_claims_to_avoid": missing[:15],
    }
    return {"recruiter_intelligence": recruiter, "executive_branding": brand, "achievement_strategy": achievement}


def resume_agent(state):
    log_agent("Executive Resume Writer")
    optimized = invoke_text(resume_prompt(state.get("candidate_profile", {}), state.get("job_spec", {}), state.get("recruiter_intelligence", {}), state.get("executive_branding", {}), state.get("achievement_strategy", {}), state.get("resume_text", "")), max_tokens=1800)
    if not optimized:
        optimized = state.get("resume_text", "")
    guard = evidence_guard(optimized, state.get("candidate_profile", {}))
    warnings = []
    if not guard.get("pass", True):
        warnings.append("Evidence review required only for these generated quantified claims: " + ", ".join(guard.get("unsupported_numeric_claims", [])) + ".")
    return {"optimized_resume": optimized, "evidence_validation": guard, "warnings": warnings}


def research_agent(state):
    empty = {"company_profile": {}, "leadership": [], "strategy": [], "market_signals": [], "sources": []}
    if not ENABLE_COMPANY_RESEARCH:
        return {"research": empty}
    from ..research import build_research_pack
    try:
        return {"research": build_research_pack(state.get("company_url", ""), state.get("leadership_url", ""), state.get("market_urls", []), state.get("market_query", ""))}
    except Exception as exc:
        return {"research": {**empty, "warning": str(exc)}}


def linkedin_agent(state):
    return {"linkedin_optimization": invoke_json(profile_prompt("LinkedIn", state.get("candidate_profile", {}), state.get("job_spec", {}), state.get("recruiter_intelligence", {})), max_tokens=650)}


def naukri_agent(state):
    return {"naukri_optimization": invoke_json(profile_prompt("Naukri", state.get("candidate_profile", {}), state.get("job_spec", {}), state.get("recruiter_intelligence", {})), max_tokens=650)}


def interview_agent(state):
    return {"interview_kit": invoke_json(interview_prompt(state.get("candidate_profile", {}), state.get("job_spec", {}), state.get("research", {}), state.get("ats_analysis", {}).get("missing_keywords", [])), max_tokens=900)}


def roadmap_agent(state):
    return {"career_roadmap": invoke_json(roadmap_prompt(state.get("candidate_profile", {}), state.get("job_spec", {}), state.get("ats_analysis", {}).get("missing_keywords", [])), max_tokens=750)}
