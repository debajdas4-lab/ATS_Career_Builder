from __future__ import annotations

import re
from difflib import SequenceMatcher

from bs4 import BeautifulSoup

PHRASES = [
    "technical program management", "cross-functional leadership", "product and engineering",
    "roadmap alignment", "program governance", "operational excellence",
    "technical risk management", "stakeholder management", "software development lifecycle",
    "distributed systems", "cloud technologies", "system architecture",
    "engineering trade-offs", "program planning", "prioritization", "success metrics",
    "senior leadership", "influence without authority", "mentoring", "adtech", "e-commerce",
    "data", "monetisation",
]
ALIASES = {
    "technical program management": ["program management", "technical program manager", "program delivery"],
    "cross-functional leadership": ["cross functional teams", "global teams", "stakeholder alignment"],
    "roadmap alignment": ["roadmap", "portfolio planning", "strategic planning", "milestones"],
    "technical risk management": ["technical risk", "risk management", "risk mitigation", "raid"],
    "operational excellence": ["process improvement", "continuous improvement"],
    "cloud technologies": ["cloud", "paas", "azure", "aws", "gcp"],
    "software development lifecycle": ["sdlc", "agile delivery", "design development testing"],
    "program governance": ["governance", "governance framework", "pmo", "kpi reporting"],
    "mentoring": ["mentor", "mentoring", "coach", "coaching", "knowledge transfer"],
    "distributed systems": ["distributed systems", "microservices", "enterprise integration"],
    "stakeholder management": ["stakeholder engagement", "stakeholder leadership", "executive stakeholder", "business stakeholders", "senior stakeholders"],
    "senior leadership": ["executive leadership", "senior leaders", "executive stakeholders", "leadership team"],
    "system architecture": ["solution architecture", "technical architecture", "enterprise architecture", "architected"],
    "engineering trade-offs": ["technical trade-offs", "architecture decisions", "design decisions", "engineering decisions"],
    "prioritization": ["priority", "prioritisation", "demand prioritization", "demand prioritisation"],
    "success metrics": ["kpi", "kpis", "metrics", "measurable outcomes", "business outcomes"],
    "product and engineering": ["product engineering", "engineering delivery", "product teams", "engineering teams"],
    "influence without authority": ["stakeholder influence", "cross-functional influence", "executive influence"],
    "data": ["analytics", "reporting", "data platform", "data-driven"],
}


def clean_html(text: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(text, "html.parser").get_text(" ", strip=True)).strip()


def build_job_spec(jd: str, source_url: str = "") -> dict:
    text = clean_html(jd)
    low = text.lower()
    years = [int(x) for x in re.findall(r"(\d{1,2})\s*\+?\s*years", low)]
    keywords = [phrase for phrase in PHRASES if phrase in low]
    keywords += [x for x in ["program execution", "milestones", "technical architecture", "risk mitigation", "measurable metrics", "problem solving", "strategic initiatives", "predictable delivery"] if x in low]
    leadership = [x for x in keywords if x in {"cross-functional leadership", "roadmap alignment", "program governance", "stakeholder management", "senior leadership", "influence without authority", "mentoring"}]
    technical = [x for x in keywords if x in {"software development lifecycle", "distributed systems", "cloud technologies", "system architecture", "engineering trade-offs", "technical risk management"}]
    return {
        "title": "Director - Technical Program Manager" if "director" in low and "technical program" in low else "",
        "years_experience": max(years) if years else None,
        "keywords": list(dict.fromkeys(keywords)),
        "required_skills": list(dict.fromkeys(keywords)),
        "leadership_expectations": leadership,
        "technical_requirements": technical,
        "domains": [x for x in keywords if x in {"adtech", "e-commerce", "data", "monetisation"}],
        "source_url": source_url,
    }


def _match(requirement: str, resume: str) -> tuple[float, str]:
    req, text = requirement.lower(), resume.lower()
    candidates = [req] + ALIASES.get(req, [])
    for candidate in candidates:
        if candidate in text:
            return 1.0, candidate
    snippets = re.split(r"[.\n;•]", text)
    best = max(((SequenceMatcher(None, req, snippet.strip()).ratio(), snippet.strip()) for snippet in snippets if len(snippet.strip()) > 10), default=(0.0, ""))
    return best if best[0] >= 0.72 else (0.0, "")


def score_fit(resume: str, spec: dict) -> dict:
    groups = {
        "skills": spec.get("required_skills", []),
        "leadership": spec.get("leadership_expectations", []),
        "technical": spec.get("technical_requirements", []),
        "domain": spec.get("domains", []),
    }

    results = {}
    for group, requirements in groups.items():
        matched, partial, missing, weighted = [], [], [], 0.0
        unique_requirements = list(dict.fromkeys(requirements))

        for requirement in unique_requirements:
            score, evidence = _match(requirement, resume)
            if score >= 0.9:
                matched.append({"requirement": requirement, "evidence": evidence})
                weighted += 1.0
            elif score >= 0.72:
                partial.append({"requirement": requirement, "evidence": evidence})
                weighted += 0.65
            else:
                missing.append(requirement)

        total = len(unique_requirements)
        results[group] = {
            "score": round(100 * weighted / total) if total else None,
            "matched": matched,
            "partial": partial,
            "missing": missing,
            "requirements": total,
        }

    # Only score dimensions that the JD actually contains. Previously an empty
    # domain/technical/leadership group received 0 and still reduced the overall
    # score, which could make a good resume appear artificially weak.
    base_weights = {
        "skills": 0.40,
        "leadership": 0.25,
        "technical": 0.25,
        "domain": 0.10,
    }
    active = {
        group: weight
        for group, weight in base_weights.items()
        if results[group]["score"] is not None
    }
    active_weight = sum(active.values())
    overall = round(
        sum(results[group]["score"] * weight for group, weight in active.items()) / active_weight
    ) if active_weight else 0

    matched_keywords = list(dict.fromkeys(
        x["requirement"]
        for value in results.values()
        for x in value["matched"]
    ))
    partial_keywords = list(dict.fromkeys(
        x["requirement"]
        for value in results.values()
        for x in value["partial"]
    ))
    missing_keywords = list(dict.fromkeys(
        x
        for value in results.values()
        for x in value["missing"]
    ))

    def dimension_score(name: str) -> int:
        value = results[name]["score"]
        return int(value) if value is not None else 0

    return {
        "score": overall,
        "leadership_score": dimension_score("leadership"),
        "technical_score": dimension_score("technical"),
        "domain_score": dimension_score("domain"),
        "recruiter_score": dimension_score("skills"),
        "executive_score": dimension_score("leadership"),
        "ai_readiness_score": 0,
        "matched_keywords": matched_keywords,
        "partial_keywords": partial_keywords,
        "missing_keywords": missing_keywords,
        "evidence_map": results,
        "recommendation": (
            "STRONG MATCH" if overall >= 80
            else "APPLY" if overall >= 65
            else "APPLY WITH POSITIONING CHANGES" if overall >= 50
            else "REVIEW FIT"
        ),
    }


def gap_analysis(resume: str, spec: dict) -> dict:
    fit = score_fit(resume, spec)
    partial = list(dict.fromkeys(x["requirement"] for value in fit["evidence_map"].values() for x in value["partial"]))
    return {"strong": fit["matched_keywords"], "partial": partial, "missing": fit["missing_keywords"]}
