from __future__ import annotations

from typing import Any, TypedDict


class CareerGuideState(TypedDict, total=False):
    analysis_mode: str
    resume_text: str
    job_description: str
    job_url: str
    company_url: str
    leadership_url: str
    market_urls: list[str]
    market_query: str
    linkedin_profile: str
    naukri_profile: str
    candidate_profile: dict[str, Any]
    job_spec: dict[str, Any]
    research: dict[str, Any]
    ats_analysis: dict[str, Any]
    recruiter_intelligence: dict[str, Any]
    executive_branding: dict[str, Any]
    achievement_strategy: dict[str, Any]
    optimized_resume: str
    cover_letter: str
    linkedin_optimization: dict[str, Any]
    naukri_optimization: dict[str, Any]
    interview_kit: dict[str, Any]
    career_roadmap: dict[str, Any]
    keyword_gap: dict[str, Any]
    skill_gap: dict[str, Any]
    experience_gap: dict[str, Any]
    career_gap: dict[str, Any]
    job_fit: dict[str, Any]
    evidence_validation: dict[str, Any]
    warnings: list[str]
