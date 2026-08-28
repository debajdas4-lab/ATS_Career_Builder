"""Premium, evidence-first resume generation.

Two paths, same clean output contract:
  * LLM path  - used when an API key is configured (best quality, tailored prose)
  * Deterministic path - always available; restructures the candidate's own
    resume into a premium ATS layout and surfaces the JD-relevant keywords the
    candidate already evidences. It never fabricates metrics or employers.

An evidence guard flags any *new* numeric claim that is not present in the
source resume, so upgrades stay truthful.
"""
from __future__ import annotations

import json
import re

from .llm import invoke_text
from .scoring import find_wording_gaps
from .utils import clean_generated_text, dedupe_keep_order, normalize_ws

_NUMERIC = re.compile(r"\b\d[\d,\.]*\s?%?\+?\b")


# --------------------------------------------------------------------------- #
# Prompt (LLM path)                                                           #
# --------------------------------------------------------------------------- #
def _resume_prompt(profile: dict, jd: str, analysis: dict, source_resume: str) -> str:
    payload = {
        "candidate": {
            "name": profile.get("name"),
            "headline": profile.get("headline"),
            "summary": profile.get("summary", "")[:1000],
            "skills": profile.get("skills", [])[:40],
            "achievements": [a.get("text") for a in profile.get("achievements", [])][:20],
            "contact": profile.get("contact", {}),
        },
        "target_keywords_present": analysis.get("matched_keywords", []),
        "target_keywords_to_weave_in_if_true": analysis.get("partial_keywords", []),
        "keywords_absent_do_not_fabricate": analysis.get("missing_keywords", []),
    }
    return f"""Rewrite the resume below into a premium, ATS-optimised, reverse-chronological
executive resume tailored to the target job. Plain text only, no markdown.

RULES
- Use ONLY facts, employers, dates, and metrics present in the SOURCE RESUME.
- Never invent numbers, scale, team sizes, or technologies.
- Weave in target keywords naturally ONLY where the source already supports them.
- Structure: NAME / HEADLINE / CONTACT / PROFESSIONAL SUMMARY (3-4 lines) /
  CORE COMPETENCIES / PROFESSIONAL EXPERIENCE (role, company, dates + 3-6 impact
  bullets each, strongest & most recent first) / EDUCATION & CERTIFICATIONS.
- Lead bullets with strong verbs and a scope + method + measurable-outcome pattern.
- Target ~2 pages; prioritise clarity and evidence over compression.

STRUCTURED CANDIDATE + KEYWORD DATA
{json.dumps(payload, ensure_ascii=False)[:3500]}

TARGET JOB DESCRIPTION
{jd[:3500]}

SOURCE RESUME (authoritative)
{source_resume[:14000]}
"""


# --------------------------------------------------------------------------- #
# Deterministic premium builder (always available)                            #
# --------------------------------------------------------------------------- #
def _split_experience_block(source_resume: str) -> str:
    low = source_resume.lower()
    for marker in ("professional experience", "work experience", "experience"):
        idx = low.find(marker)
        if idx != -1:
            return source_resume[idx:]
    return source_resume


def _deterministic_resume(profile: dict, analysis: dict, source_resume: str) -> str:
    name = (profile.get("name") or "Candidate").upper()
    headline = profile.get("headline") or "Experienced Professional"
    contact = profile.get("contact", {})
    contact_line = "  |  ".join(
        v for v in [contact.get("email"), contact.get("phone"), contact.get("linkedin")] if v
    )

    summary = profile.get("summary") or (
        "Results-driven professional with a track record of delivering measurable "
        "business and technology outcomes across cross-functional teams."
    )

    # Core competencies = keywords the candidate genuinely evidences for this JD.
    # matched = strong evidence; partial = related evidence (still truthful to
    # surface). This legitimately improves ATS keyword coverage on re-score.
    matched = analysis.get("matched_keywords", [])
    partial = analysis.get("partial_keywords", [])
    missing = analysis.get("missing_keywords", [])
    # Wording gaps: JD terms the candidate evidences with different phrasing.
    # Aligning these to the JD's terminology is truthful (the work was done) and
    # legitimately improves ATS keyword coverage on re-score.
    wording = find_wording_gaps(missing, source_resume)

    competencies = dedupe_keep_order(matched + partial + wording + profile.get("skills", []), 18)
    # A dense, keyword-mirrored technical line helps ATS parsers.
    tech_line = dedupe_keep_order(matched + partial + wording + profile.get("skills", []), 30)

    highlights = [a.get("text") for a in profile.get("achievements", [])][:6]

    lines = [name, headline]
    if contact_line:
        lines.append(contact_line)
    lines += ["", "PROFESSIONAL SUMMARY", summary, ""]

    if competencies:
        lines += ["CORE COMPETENCIES", "  •  " + "  •  ".join(competencies), ""]

    if highlights:
        lines.append("SELECTED CAREER HIGHLIGHTS")
        lines += [f"- {h}" for h in highlights]
        lines.append("")

    if tech_line:
        lines += ["TECHNICAL SKILLS", " | ".join(tech_line), ""]

    # Preserve the FULL original experience + education body verbatim so the
    # upgrade can only ADD signal, never drop keyword coverage.
    lines.append(normalize_ws(_split_experience_block(source_resume)).strip())

    return normalize_ws("\n".join(lines))


# --------------------------------------------------------------------------- #
# Evidence guard                                                              #
# --------------------------------------------------------------------------- #
def evidence_guard(generated_resume: str, source_resume: str) -> dict:
    """Flag numeric claims in the generated resume not present in the source."""
    source_numbers = set(_NUMERIC.findall(source_resume or ""))
    unsupported = []
    for num in _NUMERIC.findall(generated_resume or ""):
        base = num.strip()
        if base not in source_numbers and base.replace(",", "") not in {n.replace(",", "") for n in source_numbers}:
            unsupported.append(base)
    unsupported = dedupe_keep_order(unsupported)
    return {"pass": not unsupported, "unsupported_numeric_claims": unsupported}


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #
def build_resume(profile: dict, job_description: str, analysis: dict, source_resume: str) -> dict:
    llm_text = invoke_text(_resume_prompt(profile, job_description, analysis, source_resume))
    used_llm = bool(llm_text and llm_text.strip())
    resume = clean_generated_text(llm_text) if used_llm else _deterministic_resume(profile, analysis, source_resume)

    guard = evidence_guard(resume, source_resume)
    warnings = []
    if not guard["pass"]:
        warnings.append(
            "Evidence review: verify these numeric claims against the source resume — "
            + ", ".join(guard["unsupported_numeric_claims"])
        )
    return {
        "optimized_resume": resume,
        "generation_mode": "llm" if used_llm else "deterministic",
        "evidence_validation": guard,
        "warnings": warnings,
    }
