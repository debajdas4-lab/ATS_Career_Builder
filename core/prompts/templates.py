from __future__ import annotations

import json
import re


def _candidate(candidate: dict) -> dict:
    return {
        "name": candidate.get("name", ""),
        "headline": candidate.get("headline", ""),
        "summary": candidate.get("summary", "")[:1200],
        "skills": candidate.get("skills", [])[:45],
        "achievements": candidate.get("achievements", [])[:24],
        "experience_evidence": candidate.get("experience_evidence", [])[:24],
    }


def _job(job: dict) -> dict:
    return {
        "title": job.get("title", ""),
        "years_experience": job.get("years_experience"),
        "required_skills": job.get("required_skills", [])[:35],
        "leadership_expectations": job.get("leadership_expectations", [])[:20],
        "technical_requirements": job.get("technical_requirements", [])[:20],
        "domains": job.get("domains", [])[:12],
        "keywords": job.get("keywords", [])[:40],
    }


def _source(resume: str, max_chars: int = 13000) -> str:
    cleaned = re.sub(r"[ \t]+", " ", resume)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:9500] + "\n\n[...middle compacted...]\n\n" + cleaned[-3500:]


def resume_prompt(candidate: dict, job: dict, recruiter: dict, brand: dict, achievements: dict, resume: str) -> str:
    return f"""
Write a complete, premium executive resume tailored to the target job. Plain text only.

CONTENT STRATEGY
- Use a reverse-chronological, evidence-first strategy aligned to the target role.
- Open with an uppercase name, leadership headline, one positioning line and one-line contact details.
- Follow with a concise 3-4 line professional summary, then 6-8 selected career highlights.
- Surface recent, high-value and quantified outcomes early; do not duplicate full metric sets later.
- Use 4-6 impact bullets for the current/recent role and 1-3 for older roles.
- Preserve every employer, role, date, degree and verified certification.
- Keep only target-relevant earlier technical details in one concise Earlier Technical Foundation line.

TRUTHFULNESS
- Never invent metrics, technologies, scale, ownership, mentoring, team size or domain experience.
- Do not add a missing JD requirement merely to increase ATS score.
- Preserve supported numbers exactly and avoid unsupported quantified claims.

ATS AND EXECUTIVE WRITING
- Use supported recruiter keywords naturally, without keyword stuffing.
- Vary strong opening verbs and favor scope + method + measurable outcome.
- Avoid first person, objectives, references, icons, tables and decorative text.
- Target approximately two US Letter pages when readability permits; completeness and evidence take priority over forced compression.

OUTPUT STRUCTURE AND LABELS
NAME
HEADLINE
POSITIONING LINE
CONTACT
PROFESSIONAL SUMMARY
SELECTED CAREER HIGHLIGHTS
CORE LEADERSHIP & TECHNICAL EXPERTISE
PROFESSIONAL EXPERIENCE
ROLE | COMPANY | LOCATION | DATES
- Achievement bullet
EARLIER PROFESSIONAL EXPERIENCE
EDUCATION & PROFESSIONAL DEVELOPMENT
TECHNICAL SKILLS

CANDIDATE
{json.dumps(_candidate(candidate), ensure_ascii=False)}

TARGET JOB
{json.dumps(_job(job), ensure_ascii=False)}

RECRUITER SIGNALS
{json.dumps(recruiter, ensure_ascii=False)[:3000]}

EXECUTIVE BRAND
{json.dumps(brand, ensure_ascii=False)[:2500]}

ACHIEVEMENT PLAN
{json.dumps(achievements, ensure_ascii=False)[:3500]}

SOURCE RESUME
{_source(resume)}
"""


def profile_prompt(kind: str, candidate: dict, job: dict, recruiter: dict) -> str:
    return f"Return compact JSON for a truthful {kind} profile with headline, about_or_summary, skills, keywords, changes and terms_to_avoid. Candidate: {json.dumps(_candidate(candidate), ensure_ascii=False)} Job: {json.dumps(_job(job), ensure_ascii=False)} Keywords: {json.dumps(recruiter.get('recruiter_keywords', [])[:25], ensure_ascii=False)}"


def interview_prompt(candidate: dict, job: dict, research: dict, gaps: list[str]) -> str:
    return f"Return compact JSON with resume_questions, company_questions, leadership_questions, technical_or_domain_questions, gap_questions and star_story_blueprints using only evidence. Candidate: {json.dumps(_candidate(candidate), ensure_ascii=False)} Job: {json.dumps(_job(job), ensure_ascii=False)} Gaps: {json.dumps(gaps[:15])}"


def roadmap_prompt(candidate: dict, job: dict, gaps: list[str]) -> str:
    return f"Return compact JSON with strengths, confirmed_gaps, positioning_gaps, 30_days, 60_days, 90_days and longer_term. Distinguish capability gaps from wording gaps. Candidate: {json.dumps(_candidate(candidate), ensure_ascii=False)} Job: {json.dumps(_job(job), ensure_ascii=False)} Gaps: {json.dumps(gaps[:15])}"
