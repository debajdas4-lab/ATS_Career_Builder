"""Dynamic career artefacts for every tab.

Each artefact has an LLM path (when configured) and a deterministic fallback so
the UI tabs are NEVER empty. All content is derived from the candidate profile,
the JD, and the live ATS analysis — no hardcoded, candidate-specific strings.
"""
from __future__ import annotations

import json

from .llm import invoke_json
from .utils import dedupe_keep_order


def _kw(analysis: dict, key: str) -> list[str]:
    return analysis.get(key, []) or []


# --------------------------------------------------------------------------- #
# Fit & Gaps                                                                  #
# --------------------------------------------------------------------------- #
def build_fit(analysis: dict) -> dict:
    return {
        "overall": analysis.get("score", 0),
        "recommendation": analysis.get("recommendation", "REVIEW"),
        "components": analysis.get("components", {}),
        "strengths": _kw(analysis, "matched_keywords"),
        "partial": _kw(analysis, "partial_keywords"),
        "gaps": _kw(analysis, "missing_keywords"),
        "missing_sections": analysis.get("missing_sections", []),
    }


# --------------------------------------------------------------------------- #
# LinkedIn / Naukri                                                           #
# --------------------------------------------------------------------------- #
def build_profile_optimization(kind: str, profile: dict, analysis: dict) -> dict:
    prompt = (
        f"Return compact JSON for a truthful {kind} profile optimisation with keys: "
        f"headline, about_or_summary, top_skills (list), recommended_keywords (list), "
        f"suggested_changes (list). Use only evidenced facts.\n"
        f"CANDIDATE: {json.dumps({k: profile.get(k) for k in ('name','headline','summary','skills')}, ensure_ascii=False)[:1500]}\n"
        f"KEYWORDS_TO_TARGET: {json.dumps(_kw(analysis,'matched_keywords')+_kw(analysis,'partial_keywords'), ensure_ascii=False)[:800]}"
    )
    llm = invoke_json(prompt, max_tokens=650)
    if isinstance(llm, dict) and llm:
        return llm

    target_kw = dedupe_keep_order(_kw(analysis, "matched_keywords") + _kw(analysis, "partial_keywords"), 15)
    return {
        "headline": profile.get("headline") or "Experienced Professional",
        "about_or_summary": profile.get("summary")
        or "Experienced professional focused on delivering measurable outcomes.",
        "top_skills": dedupe_keep_order(profile.get("skills", []), 15),
        "recommended_keywords": target_kw,
        "suggested_changes": [
            f"Add a {kind} headline that leads with your strongest evidenced specialisation.",
            "Front-load the summary with 2-3 quantified achievements from your resume.",
            "Ensure the skills section mirrors the target-role keywords you already meet.",
        ],
    }


# --------------------------------------------------------------------------- #
# Interview Kit                                                               #
# --------------------------------------------------------------------------- #
def build_interview_kit(profile: dict, analysis: dict, research: dict | None = None) -> dict:
    prompt = (
        "Return compact JSON with keys: resume_questions, company_questions, "
        "leadership_questions, technical_or_domain_questions, gap_questions, "
        "star_story_blueprints. Base every question only on the evidence provided.\n"
        f"CANDIDATE: {json.dumps({k: profile.get(k) for k in ('headline','summary','skills')}, ensure_ascii=False)[:1500]}\n"
        f"MATCHED: {json.dumps(_kw(analysis,'matched_keywords')[:15])}\n"
        f"GAPS: {json.dumps(_kw(analysis,'missing_keywords')[:15])}"
    )
    llm = invoke_json(prompt, max_tokens=900)
    if isinstance(llm, dict) and llm:
        return llm

    matched = _kw(analysis, "matched_keywords")
    gaps = _kw(analysis, "missing_keywords")
    return {
        "resume_questions": [
            f"Walk me through the achievement: “{a.get('text')[:110]}”."
            for a in profile.get("achievements", [])[:4]
        ] or ["Tell me about your most impactful project and the measurable result."],
        "company_questions": [
            "Why this company, and how does this role fit your trajectory?",
            "What do you know about our product and market position?",
        ],
        "leadership_questions": [
            "Describe a time you aligned conflicting stakeholders toward one outcome.",
            "How do you set governance and remove roadblocks on complex programs?",
        ],
        "technical_or_domain_questions": [
            f"How have you applied {kw} in a real delivery?" for kw in matched[:5]
        ] or ["Describe your delivery methodology end-to-end."],
        "gap_questions": [
            f"This role emphasises “{g}”. How would you close that gap quickly?"
            for g in gaps[:5]
        ],
        "star_story_blueprints": [
            {"situation": "…", "task": "…", "action": "…", "result": a.get("text")[:120]}
            for a in profile.get("achievements", [])[:3]
        ],
    }


# --------------------------------------------------------------------------- #
# Career Roadmap                                                              #
# --------------------------------------------------------------------------- #
def build_roadmap(profile: dict, analysis: dict) -> dict:
    prompt = (
        "Return compact JSON with keys: strengths, capability_gaps, wording_gaps, "
        "plan_30_days, plan_60_days, plan_90_days, longer_term. Distinguish real "
        "capability gaps from mere resume-wording gaps.\n"
        f"CANDIDATE_SKILLS: {json.dumps(profile.get('skills', [])[:25])}\n"
        f"MATCHED: {json.dumps(_kw(analysis,'matched_keywords')[:15])}\n"
        f"GAPS: {json.dumps(_kw(analysis,'missing_keywords')[:15])}"
    )
    llm = invoke_json(prompt, max_tokens=750)
    if isinstance(llm, dict) and llm:
        return llm

    gaps = _kw(analysis, "missing_keywords")
    return {
        "strengths": _kw(analysis, "matched_keywords")[:12],
        "capability_gaps": gaps[:8],
        "wording_gaps": _kw(analysis, "partial_keywords")[:8],
        "plan_30_days": [
            "Tailor the resume summary and skills to the target keywords you already meet.",
            f"Prepare STAR stories for your top {min(3, len(profile.get('achievements', [])))} quantified achievements.",
        ],
        "plan_60_days": [
            f"Build or document evidence for: {', '.join(gaps[:3]) or 'priority gap areas'}.",
            "Request a referral or informational interview in the target org.",
        ],
        "plan_90_days": [
            "Complete one credential or project that directly closes a top capability gap.",
            "Publish a short thought-leadership post demonstrating the target competency.",
        ],
        "longer_term": [
            "Position toward senior/lead scope by leading a visible cross-functional initiative.",
        ],
    }
