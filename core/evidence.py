from __future__ import annotations

import re
from typing import Any


def extract_candidate_profile(resume_text: str, linkedin: str = "", naukri: str = "") -> dict[str, Any]:
    combined = "\n".join(x for x in (resume_text, linkedin, naukri) if x)
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    name = lines[0] if lines else "Candidate"
    headline = next((line for line in lines[1:8] if "@" not in line and len(line) < 160), "")
    skills = extract_skills(combined)
    achievements = []
    for line in lines:
        if re.search(r"\b\d+(?:\.\d+)?(?:%|\+|\s*(?:users?|teams?|stakeholders?|defects?|applications?))\b", line, re.I):
            achievements.append({
                "text": line,
                "metrics": re.findall(r"\b\d+(?:\.\d+)?%?\b", line),
                "skills": [skill for skill in skills if skill.lower() in line.lower()][:6],
                "evidence_source": "resume/profile",
                "confidence": 0.9,
            })
    return {
        "name": name,
        "headline": headline,
        "summary": " ".join(lines[:12])[:1500],
        "skills": skills,
        "experience": extract_experience(lines),
        "achievements": achievements[:30],
        "education": [],
        "certifications": [],
        "linkedin": {"raw": linkedin} if linkedin else {},
        "naukri": {"raw": naukri} if naukri else {},
        "career_gaps": [],
        "source_documents": [source for source, value in (("resume", resume_text), ("linkedin", linkedin), ("naukri", naukri)) if value],
    }


def extract_skills(text: str) -> list[str]:
    known = [
        "Technical Program Management", "Program Management", "Project Management", "Enterprise Transformation",
        "Program Governance", "Agile", "Scrum", "JIRA", "TestRail", "Power BI", "RALLY", "SAP", "S/4HANA",
        "AWS", "Azure", "Oracle", "Java", "Python", "GenAI", "Agentic AI", "RAG", "Cloud Migration",
        "Stakeholder Management", "Vendor Management", "Change Management", "Risk Management", "Release Management",
        "Executive Reporting", "Financial Governance", "Service Delivery", "Operations Transformation", "Process Optimization",
        "Product Management", "P&L", "AI Transformation",
    ]
    lower = text.lower()
    return [skill for skill in known if skill.lower() in lower]


def extract_experience(lines: list[str]) -> list[dict[str, str]]:
    results = []
    pattern = re.compile(r"(?P<company>[A-Z][A-Za-z0-9 &.,'-]+)\s*[|\-]\s*(?P<role>[^|]+)", re.I)
    for line in lines:
        match = pattern.search(line)
        if match:
            results.append({"company": match.group("company").strip(), "role": match.group("role").strip()})
    return results[:20]


def evidence_guard(text: str, candidate_profile: dict[str, Any]) -> dict[str, Any]:
    """Check complete quantified claims without reducing them to malformed tokens like '000users'."""
    source = " ".join([
        candidate_profile.get("summary", ""),
        " ".join(candidate_profile.get("skills", [])),
        " ".join(item.get("text", "") for item in candidate_profile.get("achievements", [])),
    ]).lower()
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    unsupported = []
    for sentence in sentences:
        if not re.search(r"\b\d+(?:[.,]\d+)*(?:\+|%|\s*(?:users?|members?|engineers?|teams?|countries?|transactions?|years?|projects?|applications?))?\b", sentence, re.I):
            continue
        nums = re.findall(r"\b\d+(?:[.,]\d+)*(?:\+|%)?\b", sentence)
        if nums and not all(n.lower() in source for n in nums):
            unsupported.append(sentence.strip())
    return {"pass": not unsupported, "unsupported_claims": unsupported[:10]}
