from __future__ import annotations

import re
from typing import Any

SKILLS = [
    "Technical Program Management", "Program Governance", "Cross-Functional Leadership",
    "Roadmap Planning", "Stakeholder Management", "Vendor Management", "Risk Management",
    "Release Management", "Operational Excellence", "Software Development Lifecycle",
    "System Architecture", "Cloud Technologies", "SAP", "S/4HANA", "Agile", "JIRA",
    "Power BI", "Azure DevOps", "CI/CD", "Java", "Python", "Generative AI",
    "Agentic AI", "RAG", "Microsoft Copilot", "Power Automate", "Financial Governance",
    "Resource Planning", "M&A Integration",
]


def extract_candidate_profile(resume_text: str, linkedin: str = "", naukri: str = "") -> dict[str, Any]:
    sources = {"resume": resume_text, "linkedin": linkedin, "naukri": naukri}
    combined = "\n".join(value for value in sources.values() if value)
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    skills = [skill for skill in SKILLS if skill.lower() in combined.lower()]
    metric_pattern = (
        r"(?:₹|\$|€|£)\s?\d|\b\d+(?:\.\d+)?%|"
        r"\b\d+\+?\s+(?:years?|teams?|users?|applications?|countries?|projects?|"
        r"programs?|people|employees|members|markets?|releases?|defects?)\b"
    )
    metric_evidence = [line for line in lines if re.search(metric_pattern, line, re.I)]
    experience_evidence = [
        line.strip() for line in resume_text.splitlines()
        if re.search(r"\b(?:present|20\d{2}|19\d{2})\b", line, re.I) and len(line) < 220
    ]
    return {
        "name": lines[0] if lines else "Candidate",
        "headline": next((line for line in lines[1:10] if "@" not in line and len(line) < 180), ""),
        "summary": " ".join(lines[:16])[:2600],
        "skills": skills,
        "achievements": [{"text": line, "evidence_source": "resume/profile"} for line in metric_evidence[:60]],
        "experience_evidence": experience_evidence[:35],
        "raw_resume": resume_text,
        "linkedin": {"raw": linkedin} if linkedin else {},
        "naukri": {"raw": naukri} if naukri else {},
    }


def _normalize(value: str) -> str:
    return re.sub(r"[\s,]", "", value.lower())


def _protected_claims(text: str) -> list[str]:
    patterns = [
        r"(?:₹|\$|€|£)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|b|million|billion|crore|lakh))?",
        r"\b\d+(?:\.\d+)?%",
        r"\b\d+\+?\s+(?:years?|teams?|users?|applications?|countries?|projects?|programs?|people|employees|members|markets?|releases?|defects?)\b",
    ]
    claims: list[str] = []
    for pattern in patterns:
        claims.extend(re.findall(pattern, text, flags=re.I))
    return list(dict.fromkeys(_normalize(claim) for claim in claims))


def evidence_guard(generated_text: str, profile: dict) -> dict:
    source_text = "\n".join([
        profile.get("raw_resume", ""),
        profile.get("linkedin", {}).get("raw", ""),
        profile.get("naukri", {}).get("raw", ""),
    ])
    source = set(_protected_claims(source_text))
    unsupported = [claim for claim in _protected_claims(generated_text) if claim not in source]
    return {
        "pass": not unsupported,
        "unsupported_numeric_claims": unsupported,
        "message": "All quantified claims are supported." if not unsupported else "Quantified claims require review.",
    }
