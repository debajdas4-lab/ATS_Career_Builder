"""Dynamic candidate-profile extraction.

Everything here is derived from the uploaded resume at runtime. There are NO
hardcoded names, employers, or metrics. If a field cannot be found we return a
neutral placeholder rather than inventing candidate-specific data.
"""
from __future__ import annotations

import re

from .keywords import _tech_tokens
from .utils import bullet_lines, dedupe_keep_order, sentences

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4})")
_LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s,)]+", re.I)
_URL = re.compile(r"https?://[^\s,)]+")
_NUMERIC = re.compile(r"\b\d[\d,\.]*\s?%?\+?\b")

_HEADING_WORDS = {
    "summary", "profile", "objective", "experience", "education", "skills",
    "competencies", "certifications", "projects", "achievements", "contact",
}


def _guess_name(text: str) -> str:
    """First plausible person-name line at the top of the resume."""
    for raw in (text or "").splitlines()[:8]:
        line = raw.strip()
        if not line or "@" in line or _URL.search(line) or any(ch.isdigit() for ch in line):
            continue
        words = line.split()
        if 1 < len(words) <= 5 and line.lower() not in _HEADING_WORDS:
            # Mostly alphabetic, looks like a name / all-caps header.
            alpha = sum(w.replace(".", "").isalpha() for w in words)
            if alpha >= max(2, len(words) - 1):
                return line.title() if line.isupper() else line
    return ""


def _headline(text: str, name: str) -> str:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if name:
        for i, l in enumerate(lines):
            if l.strip().lower() == name.strip().lower() and i + 1 < len(lines):
                nxt = lines[i + 1]
                if "@" not in nxt and not _URL.search(nxt) and len(nxt) < 120:
                    return nxt
    return ""


def _summary(text: str) -> str:
    low = (text or "").lower()
    for marker in ("professional summary", "profile summary", "summary", "profile", "about"):
        idx = low.find(marker)
        if idx != -1:
            chunk = text[idx + len(marker): idx + len(marker) + 800]
            chunk = re.split(r"\n\s*\n", chunk.strip(), maxsplit=1)[0]
            chunk = re.sub(r"\s+", " ", chunk).strip(" :-\n")
            if len(chunk) > 60:
                return chunk[:600]
    # Fallback: first substantial paragraph.
    for para in re.split(r"\n\s*\n", text or ""):
        p = re.sub(r"\s+", " ", para).strip()
        if len(p) > 80:
            return p[:600]
    return ""


def _achievements(text: str) -> list[dict]:
    out = []
    candidates = bullet_lines(text) or sentences(text)
    for line in candidates:
        metrics = _NUMERIC.findall(line)
        if metrics and len(line) > 25:
            out.append({
                "text": line.strip(),
                "metrics": dedupe_keep_order(metrics),
                "evidence_source": "resume",
            })
    return out[:24]


def _extract_skills(text: str, name: str) -> list[str]:
    """Skills = explicit skills section (if any) + tech tokens from the body,
    minus the candidate's own name tokens and contact fragments."""
    # Strip the header region (first ~5 lines) and any contact/URL/email lines.
    body_lines = []
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if i < 5:
            continue
        if _EMAIL.search(line) or _URL.search(line):
            continue
        body_lines.append(line)
    body = "\n".join(body_lines)

    # Prefer an explicit skills / competencies section when present.
    low = body.lower()
    section_text = ""
    for marker in ("core competency", "core competencies", "technical skills",
                   "skills", "technologies", "expertise"):
        idx = low.find(marker)
        if idx != -1:
            section_text = body[idx: idx + 900]
            break

    name_tokens = {w.lower() for w in (name or "").split()}
    # Section-heading / structural words that are not real skills.
    heading_noise = {
        "core", "work", "profile", "summary", "experience", "education",
        "skills", "competency", "competencies", "technologies", "expertise",
        "professional", "technical", "certifications", "projects", "email",
        "phone", "linkedin", "contact", "objective", "achievements",
    }
    candidates = _tech_tokens(section_text) + _tech_tokens(body)
    skills = [
        s for s in candidates
        if s.lower() not in name_tokens
        and s.lower() not in heading_noise
        and "gmail" not in s.lower()
    ]
    return dedupe_keep_order(skills, 40)


def extract_profile(resume_text: str, linkedin_profile: str = "", naukri_profile: str = "") -> dict:
    text = resume_text or ""
    combined = "\n".join(filter(None, [text, linkedin_profile, naukri_profile]))
    name = _guess_name(text)
    email = _EMAIL.search(combined).group(0) if _EMAIL.search(combined) else ""
    phone_match = _PHONE.search(combined)
    phone = phone_match.group(0).strip() if phone_match and len(phone_match.group(0).strip()) >= 8 else ""
    linkedin = _LINKEDIN.search(combined).group(0) if _LINKEDIN.search(combined) else ""

    skills = _extract_skills(text, name)
    achievements = _achievements(text)

    return {
        "name": name or "Candidate",
        "headline": _headline(text, name) or "Experienced Professional",
        "summary": _summary(text),
        "contact": {"email": email, "phone": phone, "linkedin": linkedin},
        "skills": dedupe_keep_order(skills, 40),
        "achievements": achievements,
        "raw_length": len(text),
    }
