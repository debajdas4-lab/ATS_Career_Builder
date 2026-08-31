"""
ATS Resume Builder
==================

Source-authoritative resume generation.

IMPORTANT DESIGN PRINCIPLE
--------------------------
The source resume is authoritative for career history.

The LLM may improve:
    - Professional Summary
    - Core Competencies
    - Selected Career Highlights
    - Technical Skills
    - wording of experience bullets

The LLM is NOT allowed to control:
    - employer count
    - employer order
    - role
    - company
    - dates
    - Domain / Industry
    - Earlier Experience
    - Education / Professional Development

Python constructs the final resume structure.

Required final structure:

NAME
HEADLINE
CONTACT
PROFESSIONAL SUMMARY
CORE COMPETENCIES
SELECTED CAREER HIGHLIGHTS
TECHNICAL SKILLS
PROFESSIONAL EXPERIENCE
    Employer 1
    Employer 2
    Employer 3
    ...
EARLIER EXPERIENCE
EDUCATION & PROFESSIONAL DEVELOPMENT
"""

from __future__ import annotations

import json
import re
from typing import Any

from .llm import invoke_text
from .scoring import find_wording_gaps
from .utils import (
    clean_generated_text,
    dedupe_keep_order,
    normalize_ws,
)


# =============================================================================
# REGEX / CONSTANTS
# =============================================================================

_NUMERIC = re.compile(
    r"\b\d[\d,\.]*\s?%?\+?\b"
)

_DATE_RANGE = re.compile(
    r"""
    (?:
        (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)
        [a-z]*\.?\s+\d{4}
        |
        \d{4}
    )
    \s*
    (?:-|–|—|to)
    \s*
    (?:
        Present
        |
        Current
        |
        (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)
        [a-z]*\.?\s+\d{4}
        |
        \d{4}
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# -----------------------------------------------------------------------------#
# Section markers
# -----------------------------------------------------------------------------#

_EXPERIENCE_MARKERS = (
    "professional experience",
    "work experience",
    "employment history",
    "professional employment",
)

_EARLIER_MARKERS = (
    "earlier experience",
    "earlier professional experience",
    "additional experience",
)

_EDUCATION_MARKERS = (
    "education & professional development",
    "education and professional development",
    "education & certifications",
    "education and certifications",
    "education & certification",
    "education and certification",
    "education",
    "certifications",
    "professional development",
)


# -----------------------------------------------------------------------------#
# Common company patterns
#
# These are deliberately broad enough for the current resume while still
# requiring a date range before a line can become an employer header.
# -----------------------------------------------------------------------------#

_COMPANY_PATTERNS = [
    re.compile(
        r"\bHP\s+INC\.?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bHewlett\s+Packard\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bCisco\s+Systems\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bWipro\s+Limited\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bMindtree\s+Limited\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bNetkraft\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bMetafusion\b",
        re.IGNORECASE,
    ),
]


_LOW_VALUE = {
    "service",
    "services",
    "drive",
    "driving",
    "execution",
    "execute",
    "support",
    "working",
    "work",
    "business",
    "team",
    "teams",
    "management",
    "experience",
    "strong",
    "skills",
    "responsible",
    "responsibility",
    "lead",
    "led",
    "delivery",
    "deliver",
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "across",
}


_SKILL_STOPLIST = {
    "it",
    "ip",
    "hr",
    "bi",
    "li",
    "and",
    "nit",
    "cgpa",
    "gate",
    "saf",
    "hp",
    "eem",
    "dxc",
    "grs",
    "sgs",
    "usa",
    "et",
    "cio",
    "gcc",
    "vat",
    "qa",
    "pmo",
    "kt",
    "rca",
    "sla",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
}


_SKILL_KEEP = {
    "sap",
    "aws",
    "gcp",
    "ci/cd",
    "sdlc",
    "api",
    "rag",
    "ai",
    "j2ee",
    "pmp",
}


# =============================================================================
# BASIC HELPERS
# =============================================================================

def _clean_line(
    value: Any,
) -> str:
    """
    Normalize a single source/generated line without destroying meaningful
    punctuation.
    """

    return normalize_ws(
        str(
            value or ""
        )
    ).strip()


def _strip_bullet(
    value: Any,
) -> str:

    text = _clean_line(
        value
    )

    text = re.sub(
        r"^[•\-\*▪◦●]+\s*",
        "",
        text,
    )

    return text.strip()


def _is_bullet(
    line: str,
) -> bool:

    return bool(
        re.match(
            r"^\s*[•\-\*▪◦●]\s+",
            line,
        )
    )


def _clean_lines(
    text: str,
) -> list[str]:

    output = []

    for raw in (
        text or ""
    ).replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).split(
        "\n"
    ):

        value = _clean_line(
            raw
        )

        if value:
            output.append(
                value
            )

    return output


def _find_marker(
    text: str,
    markers: tuple[str, ...],
    start: int = 0,
) -> tuple[int, str | None]:

    source = (
        text or ""
    )

    lower = source.lower()

    matches = []

    for marker in markers:

        pos = lower.find(
            marker,
            start,
        )

        if pos >= 0:

            matches.append(
                (
                    pos,
                    marker,
                )
            )

    if not matches:
        return -1, None

    return min(
        matches,
        key=lambda x: x[0],
    )


# =============================================================================
# SOURCE SECTION EXTRACTION
# =============================================================================

def _extract_sections(
    source_resume: str,
) -> dict[str, str]:
    """
    Extract:
        Professional Experience
        Earlier Experience
        Education

    without allowing one section to consume another.
    """

    text = (
        source_resume
        or ""
    )

    if not text.strip():

        return {
            "experience": "",
            "earlier": "",
            "education": "",
        }

    experience_start, _ = _find_marker(
        text,
        _EXPERIENCE_MARKERS,
    )

    earlier_start, _ = _find_marker(
        text,
        _EARLIER_MARKERS,
    )

    education_start, _ = _find_marker(
        text,
        _EDUCATION_MARKERS,
    )

    # -------------------------------------------------------------------------#
    # Experience
    # -------------------------------------------------------------------------#

    experience = ""

    if experience_start >= 0:

        possible_endings = [
            position
            for position in (
                earlier_start,
                education_start,
            )
            if position > experience_start
        ]

        experience_end = (
            min(possible_endings)
            if possible_endings
            else len(text)
        )

        experience = text[
            experience_start:
            experience_end
        ].strip()

    # -------------------------------------------------------------------------#
    # Earlier Experience
    # -------------------------------------------------------------------------#

    earlier = ""

    if earlier_start >= 0:

        possible_endings = [
            position
            for position in (
                education_start,
            )
            if position > earlier_start
        ]

        earlier_end = (
            min(possible_endings)
            if possible_endings
            else len(text)
        )

        earlier = text[
            earlier_start:
            earlier_end
        ].strip()

    # -------------------------------------------------------------------------#
    # Education
    # -------------------------------------------------------------------------#

    education = ""

    if education_start >= 0:

        education = text[
            education_start:
        ].strip()

    return {
        "experience": experience,
        "earlier": earlier,
        "education": education,
    }


# =============================================================================
# SOURCE EXPERIENCE PARSER
# =============================================================================

def _is_company_line(line: str) -> bool:
    """Detect company/date headers without candidate-specific employer names."""
    value = _clean_line(line)
    if not value or not _DATE_RANGE.search(value):
        return False
    if _is_bullet(value) or value.lower().startswith("domain:") or len(value) > 220:
        return False
    low = value.lower()
    if any(x in low for x in ("professional experience", "work experience",
                              "employment history", "education", "earlier experience")):
        return False
    return bool(
        "|" in value
        or re.search(
            r"\b(?:inc\.?|limited|ltd\.?|llc|plc|corp\.?|corporation|systems|"
            r"technologies|technology|solutions|services|group|company|pvt\.?\s*ltd\.?)\b",
            value, re.IGNORECASE
        )
    )



def _coalesce_body_lines(lines: list[str]) -> list[str]:
    """Join PDF/DOCX line wraps so achievements remain complete."""
    out: list[str] = []
    for raw in lines or []:
        line = _clean_line(raw)
        if not line:
            continue
        if line.lower().startswith("domain:") or _is_bullet(line):
            out.append(line)
        elif out and _is_bullet(out[-1]):
            out[-1] = _clean_line(out[-1] + " " + line)
        else:
            out.append(line)
    return out

def _parse_employer_experience(
    experience_text: str,
) -> list[dict[str, Any]]:
    """
    Parse source career history into atomic employer blocks.

    IMPORTANT:
    The role immediately preceding a company/date line belongs to that
    employer.

    Output:

    [
        {
            "role": "...",
            "company_dates": "...",
            "domain": "...",
            "body_lines": [...]
        }
    ]
    """

    text = re.sub(
        r"""
        (?im)
        ^\s*
        (?:
            professional\s+experience
            |
            work\s+experience
            |
            experience
            |
            employment\s+history
            |
            professional\s+employment
        )
        \s*:?\s*$
        """,
        "",
        experience_text or "",
        flags=re.VERBOSE,
    )

    lines = _clean_lines(
        text
    )

    if not lines:
        return []

    company_indices = [
        index
        for index, line in enumerate(
            lines
        )
        if _is_company_line(
            line
        )
    ]

    if not company_indices:
        return []

    employers = []

    for sequence, company_index in enumerate(
        company_indices
    ):

        next_company_index = (
            company_indices[sequence + 1]
            if sequence + 1 < len(
                company_indices
            )
            else len(lines)
        )

        # ---------------------------------------------------------------------#
        # ROLE
        # ---------------------------------------------------------------------#

        role = ""

        if company_index > 0:

            candidate = lines[
                company_index - 1
            ]

            if (
                not _is_bullet(
                    candidate
                )
                and not candidate.lower().startswith(
                    "domain:"
                )
                and candidate not in {
                    "PROFESSIONAL EXPERIENCE",
                    "WORK EXPERIENCE",
                    "EXPERIENCE",
                }
            ):

                role = candidate

        # ---------------------------------------------------------------------#
        # COMPANY + DATES
        # ---------------------------------------------------------------------#

        company_dates = lines[
            company_index
        ]

        # ---------------------------------------------------------------------#
        # BODY
        # ---------------------------------------------------------------------#

        body_start = (
            company_index + 1
        )

        body_end = (
            next_company_index
        )

        body_lines = _coalesce_body_lines(
            lines[body_start:body_end]
        )

        domain = ""

        remaining_body = []

        for body_line in body_lines:

            match = re.match(
                r"(?i)^domain\s*:\s*(.*)$",
                body_line,
            )

            if match:

                domain = _clean_line(
                    match.group(1)
                )

            else:

                remaining_body.append(
                    body_line
                )

        # ---------------------------------------------------------------------#
        # Remove accidental role duplication from body.
        # ---------------------------------------------------------------------#

        if (
            role
            and remaining_body
            and remaining_body[0].lower()
            == role.lower()
        ):

            remaining_body = remaining_body[
                1:
            ]

        employers.append(
            {
                "role":
                    role,

                "company_dates":
                    company_dates,

                "domain":
                    domain,

                "body_lines":
                    remaining_body,
            }
        )

    return employers


# =============================================================================
# EARLIER EXPERIENCE / EDUCATION
# =============================================================================

def _parse_earlier_experience(
    earlier_text: str,
) -> list[str]:

    if not earlier_text:
        return []

    text = re.sub(
        r"""
        (?im)
        ^\s*
        earlier\s+
        (?:professional\s+)?
        experience
        \s*:?\s*$
        """,
        "",
        earlier_text,
        flags=re.VERBOSE,
    )

    return _clean_lines(
        text
    )


def _parse_education(
    education_text: str,
) -> list[str]:

    if not education_text:
        return []

    text = re.sub(
        r"""
        (?im)
        ^\s*
        (?:
            education
            |
            education\s*&\s*professional\s+development
            |
            education\s+and\s+professional\s+development
            |
            education\s*&\s*certifications?
            |
            education\s+and\s+certifications?
            |
            certifications
            |
            professional\s+development
        )
        \s*:?\s*$
        """,
        "",
        education_text,
        flags=re.VERBOSE,
    )

    return _clean_lines(
        text
    )


# =============================================================================
# SKILL HELPERS
# =============================================================================

def _is_junk_skill(
    value: str,
) -> bool:

    token = (
        value
        .strip()
        .lower()
    )

    if not token:
        return True

    if token in _SKILL_STOPLIST:
        return True

    if (
        len(token) <= 2
        and token not in {
            "ai",
        }
    ):
        return True

    return False


def _meaningful_keywords(
    values,
    limit: int = 30,
) -> list[str]:

    output = []

    seen = set()

    for value in (
        values or []
    ):

        token = _clean_line(
            value
        )

        if not token:
            continue

        # Handle strings accidentally passed as one pipe-separated value.
        pieces = re.split(
            r"\s*[|,;]\s*",
            token,
        )

        for piece in pieces:

            piece = _clean_line(
                piece
            )

            if not piece:
                continue

            if _is_junk_skill(
                piece
            ):
                continue

            key = piece.lower()

            if key in seen:
                continue

            seen.add(
                key
            )

            output.append(
                piece
            )

            if len(output) >= limit:
                return output

    return output



def _norm_skill(value: str) -> str:
    return re.sub(r"[^a-z0-9+#./]+", " ", _clean_line(value).lower()).strip()


def _safe_skill_pool(profile: dict, analysis: dict, source_resume: str) -> list[str]:
    wording_gaps = find_wording_gaps(analysis.get("missing_keywords", []), source_resume)
    return _meaningful_keywords(
        profile.get("skills", [])
        + analysis.get("matched_keywords", [])
        + analysis.get("partial_keywords", [])
        + wording_gaps,
        limit=50,
    )


def _filter_generated_skills(generated, profile: dict, analysis: dict,
                             source_resume: str, limit: int) -> list[str]:
    allowed = _safe_skill_pool(profile, analysis, source_resume)
    allowed_map = {_norm_skill(x): x for x in allowed if _norm_skill(x)}
    result = []
    for item in _meaningful_keywords(generated, limit=60):
        key = _norm_skill(item)
        if key in allowed_map:
            result.append(allowed_map[key])
    return dedupe_keep_order(result or allowed, limit)


def _numeric_claims_supported(text: str, source_resume: str) -> bool:
    source_nums = {x.replace(",", "").strip() for x in _NUMERIC.findall(source_resume or "")}
    generated_nums = {x.replace(",", "").strip() for x in _NUMERIC.findall(text or "")}
    return generated_nums.issubset(source_nums)


def _select_employer_bullets(llm_bullets: list[str], source_bullets: list[str],
                             source_resume: str) -> list[str]:
    llm_clean = [_strip_bullet(x) for x in llm_bullets if _strip_bullet(x)]
    src_clean = [_strip_bullet(x) for x in source_bullets if _strip_bullet(x)]
    if not llm_clean:
        return src_clean
    minimum = max(1, int(len(src_clean) * 0.80))
    if len(llm_clean) < minimum:
        return src_clean
    if not all(_numeric_claims_supported(x, source_resume) for x in llm_clean):
        return src_clean
    return llm_clean

# =============================================================================
# LLM PROMPT
# =============================================================================

def _resume_prompt(
    profile: dict,
    jd: str,
    analysis: dict,
    source_resume: str,
    source_employers: list[dict],
    source_earlier: list[str],
    source_education: list[str],
) -> str:
    """
    Ask the LLM to improve content while explicitly preserving the source
    experience manifest.
    """

    manifest = []

    for sequence, employer in enumerate(
        source_employers,
        start=1,
    ):

        manifest.append(
            {
                "sequence":
                    sequence,

                "role":
                    employer.get(
                        "role",
                        "",
                    ),

                "company_dates":
                    employer.get(
                        "company_dates",
                        "",
                    ),

                "domain":
                    employer.get(
                        "domain",
                        "",
                    ),

                "source_bullets":
                    employer.get(
                        "body_lines",
                        [],
                    ),
            }
        )

    payload = {
        "candidate":
            profile,

        "experience_manifest":
            manifest,

        "earlier_experience":
            source_earlier,

        "education":
            source_education,

        "matched_keywords":
            analysis.get(
                "matched_keywords",
                [],
            ),

        "partial_keywords":
            analysis.get(
                "partial_keywords",
                [],
            ),

        "missing_keywords":
            analysis.get(
                "missing_keywords",
                [],
            ),
    }

    return f"""
You are an expert ATS resume writer.

SOURCE-OF-TRUTH RULE
====================

The source resume controls career history.

The Python application has already identified every employer.

You MUST preserve:

1. employer count
2. employer order
3. role
4. company
5. dates
6. Domain / Industry
7. relationship between employer and bullets
8. Earlier Experience
9. Education & Professional Development

NEVER:
- merge employers
- reorder employers
- remove employers
- invent employers
- invent clients
- invent industries
- invent domains
- invent dates
- invent roles
- invent metrics
- move a bullet to another employer
- move a Domain to another employer
- place employer headings after Education
- put employer headings into another section

You MAY:
- improve bullet wording
- improve summary
- improve competencies
- improve technical skills
- improve career highlights
- use ATS terminology from the job description ONLY when directly or equivalently supported by the source
- improve clarity and executive tone
- preserve the candidate's strongest quantified achievements
- keep every rewritten bullet complete; never return sentence fragments
- keep Core Competencies as capabilities, not responsibility phrases or product slogans
- keep Technical Skills limited to technologies/capabilities evidenced in the source resume

STRICT TAILORING RULES:
- The JD is a targeting guide, NOT candidate evidence.
- Never copy a target-company product/platform name into skills or experience unless it appears in the source resume.
- Never turn responsibility wording such as "build team", "deliver <product>", "context-aware experiences",
  "own delivery", or "career growth" into candidate skills.
- When evidence is transferable, describe the transferable capability without claiming target-company-specific experience.

DO NOT manufacture facts.

===============================================================================
MANDATORY JSON FORMAT
===============================================================================

Return ONLY valid JSON.

Use this exact structure:

{{
  "name": "...",
  "headline": "...",
  "contact": "...",

  "professional_summary": "...",

  "core_competencies": [
    "..."
  ],

  "selected_career_highlights": [
    "..."
  ],

  "technical_skills": [
    "..."
  ],

  "professional_experience": [
    {{
      "sequence": 1,
      "role": "EXACT SOURCE ROLE",
      "company_dates": "EXACT SOURCE COMPANY AND DATES",
      "domain": "EXACT SOURCE DOMAIN",
      "bullets": [
        "improved bullet"
      ]
    }}
  ],

  "earlier_experience": [
    "..."
  ],

  "education_professional_development": [
    "..."
  ]
}}

CRITICAL:
The number of professional_experience objects MUST equal the number of
source employers.

The sequence MUST remain identical.

The role, company_dates and domain fields MUST remain exactly as provided
in the source manifest.

If there are four employers in the source manifest, return exactly four
professional_experience objects.

===============================================================================
SOURCE EXPERIENCE MANIFEST
===============================================================================

{json.dumps(manifest, ensure_ascii=False, indent=2)}

===============================================================================
EARLIER EXPERIENCE
===============================================================================

{json.dumps(source_earlier, ensure_ascii=False, indent=2)}

===============================================================================
EDUCATION
===============================================================================

{json.dumps(source_education, ensure_ascii=False, indent=2)}

===============================================================================
CANDIDATE / ANALYSIS
===============================================================================

{json.dumps(payload, ensure_ascii=False, indent=2)[:18000]}

===============================================================================
JOB DESCRIPTION
===============================================================================

{jd[:7000]}

===============================================================================
SOURCE RESUME
===============================================================================

{source_resume[:24000]}
"""


# =============================================================================
# LLM JSON EXTRACTION
# =============================================================================

def _extract_json_object(
    raw_text: str,
) -> dict:

    raw = (
        raw_text or ""
    ).strip()

    if not raw:
        raise ValueError(
            "LLM returned empty output."
        )

    # Remove Markdown JSON fences.
    raw = re.sub(
        r"^\s*```(?:json)?\s*",
        "",
        raw,
        flags=re.IGNORECASE,
    )

    raw = re.sub(
        r"\s*```\s*$",
        "",
        raw,
    ).strip()

    first = raw.find(
        "{"
    )

    last = raw.rfind(
        "}"
    )

    if (
        first < 0
        or last < 0
        or last <= first
    ):

        raise ValueError(
            "LLM output does not contain a JSON object."
        )

    candidate = raw[
        first:
        last + 1
    ]

    result = json.loads(
        candidate
    )

    if not isinstance(
        result,
        dict,
    ):

        raise ValueError(
            "LLM JSON root is not an object."
        )

    return result


# =============================================================================
# STRUCTURE VALIDATION
# =============================================================================

def _validate_structured_output(
    data: dict,
    source_employers: list[dict],
    source_earlier: list[str],
    source_education: list[str],
) -> tuple[bool, list[str]]:

    errors = []

    if not isinstance(
        data,
        dict,
    ):

        return False, [
            "Output is not a dictionary."
        ]

    generated_experience = data.get(
        "professional_experience"
    )

    if not isinstance(
        generated_experience,
        list,
    ):

        return False, [
            "professional_experience is not a list."
        ]

    # -------------------------------------------------------------------------#
    # Employer count
    # -------------------------------------------------------------------------#

    if len(
        generated_experience
    ) != len(
        source_employers
    ):

        errors.append(
            "Employer count mismatch: "
            f"source={len(source_employers)}, "
            f"generated={len(generated_experience)}"
        )

    # -------------------------------------------------------------------------#
    # Employer identity
    # -------------------------------------------------------------------------#

    for index, source in enumerate(
        source_employers
    ):

        if index >= len(
            generated_experience
        ):
            break

        generated = generated_experience[
            index
        ]

        if not isinstance(
            generated,
            dict,
        ):

            errors.append(
                f"Employer {index + 1} is not an object."
            )

            continue

        source_role = _clean_line(
            source.get(
                "role",
                "",
            )
        )

        source_company_dates = _clean_line(
            source.get(
                "company_dates",
                "",
            )
        )

        source_domain = _clean_line(
            source.get(
                "domain",
                "",
            )
        )

        generated_role = _clean_line(
            generated.get(
                "role",
                "",
            )
        )

        generated_company_dates = _clean_line(
            generated.get(
                "company_dates",
                "",
            )
        )

        generated_domain = _clean_line(
            generated.get(
                "domain",
                "",
            )
        )

        if (
            source_role
            and generated_role.lower()
            != source_role.lower()
        ):

            errors.append(
                f"Employer {index + 1}: role changed."
            )

        if (
            source_company_dates
            and generated_company_dates.lower()
            != source_company_dates.lower()
        ):

            errors.append(
                f"Employer {index + 1}: company/dates changed."
            )

        if source_domain:

            if (
                not generated_domain
                or generated_domain.lower()
                != source_domain.lower()
            ):

                errors.append(
                    f"Employer {index + 1}: Domain changed."
                )

        bullets = generated.get(
            "bullets"
        )

        if not isinstance(
            bullets,
            list,
        ):

            errors.append(
                f"Employer {index + 1}: bullets are not a list."
            )

        elif not bullets:

            errors.append(
                f"Employer {index + 1}: bullets are empty."
            )

    # -------------------------------------------------------------------------#
    # Earlier Experience
    # -------------------------------------------------------------------------#

    if source_earlier:

        generated_earlier = data.get(
            "earlier_experience"
        )

        if not isinstance(
            generated_earlier,
            list,
        ):

            errors.append(
                "Earlier Experience missing."
            )

        elif not generated_earlier:

            errors.append(
                "Earlier Experience empty."
            )

    # -------------------------------------------------------------------------#
    # Education
    # -------------------------------------------------------------------------#

    if source_education:

        generated_education = data.get(
            "education_professional_development"
        )

        if not isinstance(
            generated_education,
            list,
        ):

            errors.append(
                "Education & Professional Development missing."
            )

        elif not generated_education:

            errors.append(
                "Education & Professional Development empty."
            )

    return (
        len(errors) == 0,
        errors,
    )


# =============================================================================
# SOURCE-LOCKED RENDERER
# =============================================================================

def _render_source_locked_resume(
    data: dict,
    source_employers: list[dict],
    source_earlier: list[str],
    source_education: list[str],
    profile: dict,
    analysis: dict,
    source_resume: str,
) -> str:
    """
    Build the final resume.

    IMPORTANT:
    Employer structure comes exclusively from source_employers.

    The LLM CANNOT:
        - move employers
        - rename employers
        - change dates
        - change Domain
        - attach bullets to another employer
    """

    lines = []

    # =========================================================================
    # HEADER
    # =========================================================================

    name = _clean_line(
        data.get(
            "name",
            "",
        )
    )

    headline = _clean_line(
        data.get(
            "headline",
            "",
        )
    )

    contact = _clean_line(
        data.get(
            "contact",
            "",
        )
    )

    if name:
        lines.append(
            name
        )

    if headline:
        lines.append(
            headline
        )

    if contact:
        lines.append(
            contact
        )

    # =========================================================================
    # PROFESSIONAL SUMMARY
    # =========================================================================

    summary = _clean_line(
        data.get(
            "professional_summary",
            "",
        )
    )

    if summary:

        lines += [
            "",
            "PROFESSIONAL SUMMARY",
            summary,
        ]

    # =========================================================================
    # CORE COMPETENCIES
    # =========================================================================

    competencies = _filter_generated_skills(
        data.get("core_competencies", []),
        profile, analysis, source_resume, limit=18,
    )

    if competencies:

        lines += [
            "",
            "CORE COMPETENCIES",
            " | ".join(
                competencies
            ),
        ]

    # =========================================================================
    # SELECTED CAREER HIGHLIGHTS
    # =========================================================================

    highlights = data.get(
        "selected_career_highlights",
        [],
    )

    if isinstance(
        highlights,
        list,
    ):

        clean_highlights = []

        for item in highlights:

            value = _strip_bullet(
                item
            )

            if value:

                clean_highlights.append(
                    value
                )

        if clean_highlights:

            lines += [
                "",
                "SELECTED CAREER HIGHLIGHTS",
            ]

            for item in clean_highlights:

                lines.append(
                    f"• {item}"
                )

    # =========================================================================
    # TECHNICAL SKILLS
    # =========================================================================

    technical = _filter_generated_skills(
        data.get("technical_skills", []),
        profile, analysis, source_resume, limit=30,
    )

    if technical:

        lines += [
            "",
            "TECHNICAL SKILLS",
            " | ".join(
                technical
            ),
        ]

    # =========================================================================
    # PROFESSIONAL EXPERIENCE
    # =========================================================================

    lines += [
        "",
        "PROFESSIONAL EXPERIENCE",
    ]

    generated_experience = data.get(
        "professional_experience",
        [],
    )

    if not isinstance(
        generated_experience,
        list,
    ):

        generated_experience = []

    # -------------------------------------------------------------------------#
    # CRITICAL:
    #
    # Iterate through source_employers, NOT generated_experience.
    #
    # This guarantees source chronology and employer association.
    # -------------------------------------------------------------------------#

    for index, source_employer in enumerate(
        source_employers
    ):

        role = _clean_line(
            source_employer.get(
                "role",
                "",
            )
        )

        company_dates = _clean_line(
            source_employer.get(
                "company_dates",
                "",
            )
        )

        domain = _clean_line(
            source_employer.get(
                "domain",
                "",
            )
        )

        # ---------------------------------------------------------------------#
        # ROLE
        # ---------------------------------------------------------------------#

        if role:

            lines += [
                "",
                role,
            ]

        # ---------------------------------------------------------------------#
        # COMPANY + DATES
        # ---------------------------------------------------------------------#

        if company_dates:

            lines.append(
                company_dates
            )

        # ---------------------------------------------------------------------#
        # DOMAIN
        # ---------------------------------------------------------------------#

        if domain:

            lines += [
                "",
                f"Domain: {domain}",
            ]

        # ---------------------------------------------------------------------#
        # BULLETS
        # ---------------------------------------------------------------------#

        llm_bullets = []

        if index < len(
            generated_experience
        ):

            generated_employer = (
                generated_experience[
                    index
                ]
            )

            if isinstance(
                generated_employer,
                dict,
            ):

                candidate_bullets = (
                    generated_employer.get(
                        "bullets",
                        [],
                    )
                )

                if isinstance(
                    candidate_bullets,
                    list,
                ):

                    llm_bullets = [
                        _strip_bullet(
                            bullet
                        )
                        for bullet in candidate_bullets
                        if _strip_bullet(
                            bullet
                        )
                    ]

        source_bullets = []

        for bullet in source_employer.get(
            "body_lines",
            [],
        ):

            value = _strip_bullet(
                bullet
            )

            if value:
                source_bullets.append(
                    value
                )

        # Use rewritten bullets only when complete and evidence-safe.
        bullets = _select_employer_bullets(
            llm_bullets, source_bullets, source_resume
        )

        for bullet in bullets:

            lines.append(
                f"• {bullet}"
            )

    # =========================================================================
    # EARLIER EXPERIENCE
    # =========================================================================

    if source_earlier:

        lines += [
            "",
            "EARLIER EXPERIENCE",
        ]

        for item in source_earlier:

            value = _strip_bullet(
                item
            )

            if value:

                lines.append(
                    f"• {value}"
                )

    # =========================================================================
    # EDUCATION & PROFESSIONAL DEVELOPMENT
    # =========================================================================

    if source_education:

        lines += [
            "",
            "EDUCATION & PROFESSIONAL DEVELOPMENT",
        ]

        for item in source_education:

            value = _strip_bullet(
                item
            )

            if value:

                lines.append(
                    f"• {value}"
                )

    return "\n".join(
        lines
    ).strip()


# =============================================================================
# DETERMINISTIC FALLBACK
# =============================================================================

def _deterministic_resume(
    profile: dict,
    analysis: dict,
    source_resume: str,
) -> str:
    """
    Fully deterministic resume generation.

    This is the safety net if the LLM produces invalid structure.
    """

    sections = _extract_sections(
        source_resume
    )

    employers = _parse_employer_experience(
        sections.get(
            "experience",
            "",
        )
    )

    earlier = _parse_earlier_experience(
        sections.get(
            "earlier",
            "",
        )
    )

    education = _parse_education(
        sections.get(
            "education",
            "",
        )
    )

    # -------------------------------------------------------------------------#
    # Header
    # -------------------------------------------------------------------------#

    name = _clean_line(
        profile.get(
            "name",
            "",
        )
    )

    headline = _clean_line(
        profile.get(
            "headline",
            "",
        )
    )

    contact_obj = profile.get(
        "contact",
        {},
    )

    contact_parts = []

    if isinstance(
        contact_obj,
        dict,
    ):

        for key in (
            "email",
            "phone",
            "linkedin",
        ):

            value = _clean_line(
                contact_obj.get(
                    key,
                    "",
                )
            )

            if value:
                contact_parts.append(
                    value
                )

    contact = " | ".join(
        contact_parts
    )

    summary = _clean_line(
        profile.get(
            "summary",
            "",
        )
    )

    if not summary:

        summary = (
            "Results-driven technology leader with "
            "extensive experience delivering complex "
            "programs, enterprise transformation, and "
            "cross-functional initiatives."
        )

    lines = []

    if name:
        lines.append(
            name
        )

    if headline:
        lines.append(
            headline
        )

    if contact:
        lines.append(
            contact
        )

    lines += [
        "",
        "PROFESSIONAL SUMMARY",
        summary,
    ]

    # -------------------------------------------------------------------------#
    # Competencies
    # -------------------------------------------------------------------------#

    competencies = _meaningful_keywords(
        analysis.get(
            "matched_keywords",
            [],
        )
        + analysis.get(
            "partial_keywords",
            [],
        )
        + profile.get(
            "skills",
            [],
        ),
        limit=18,
    )

    if competencies:

        lines += [
            "",
            "CORE COMPETENCIES",
            " | ".join(
                competencies
            ),
        ]

    # -------------------------------------------------------------------------#
    # Highlights
    # -------------------------------------------------------------------------#

    achievements = []

    for achievement in profile.get(
        "achievements",
        [],
    ):

        if isinstance(
            achievement,
            dict,
        ):

            value = _strip_bullet(
                achievement.get(
                    "text",
                    "",
                )
            )

        else:

            value = _strip_bullet(
                achievement
            )

        if value:
            achievements.append(
                value
            )

    if achievements:

        lines += [
            "",
            "SELECTED CAREER HIGHLIGHTS",
        ]

        for item in achievements:

            lines.append(
                f"• {item}"
            )

    # -------------------------------------------------------------------------#
    # Technical Skills
    # -------------------------------------------------------------------------#

    wording_gaps = find_wording_gaps(
        analysis.get(
            "missing_keywords",
            [],
        ),
        source_resume,
    )

    technical = _meaningful_keywords(
        profile.get(
            "skills",
            [],
        )
        + analysis.get(
            "matched_keywords",
            [],
        )
        + analysis.get(
            "partial_keywords",
            [],
        )
        + wording_gaps,
        limit=30,
    )

    if technical:

        lines += [
            "",
            "TECHNICAL SKILLS",
            " | ".join(
                technical
            ),
        ]

    # -------------------------------------------------------------------------#
    # Professional Experience
    # -------------------------------------------------------------------------#

    lines += [
        "",
        "PROFESSIONAL EXPERIENCE",
    ]

    for employer in employers:

        role = _clean_line(
            employer.get(
                "role",
                "",
            )
        )

        company_dates = _clean_line(
            employer.get(
                "company_dates",
                "",
            )
        )

        domain = _clean_line(
            employer.get(
                "domain",
                "",
            )
        )

        if role:

            lines += [
                "",
                role,
            ]

        if company_dates:

            lines.append(
                company_dates
            )

        if domain:

            lines += [
                "",
                f"Domain: {domain}",
            ]

        for bullet in employer.get(
            "body_lines",
            [],
        ):

            value = _strip_bullet(
                bullet
            )

            if value:

                lines.append(
                    f"• {value}"
                )

    # -------------------------------------------------------------------------#
    # Earlier Experience
    # -------------------------------------------------------------------------#

    if earlier:

        lines += [
            "",
            "EARLIER EXPERIENCE",
        ]

        for item in earlier:

            value = _strip_bullet(
                item
            )

            if value:

                lines.append(
                    f"• {value}"
                )

    # -------------------------------------------------------------------------#
    # Education
    # -------------------------------------------------------------------------#

    if education:

        lines += [
            "",
            "EDUCATION & PROFESSIONAL DEVELOPMENT",
        ]

        for item in education:

            value = _strip_bullet(
                item
            )

            if value:

                lines.append(
                    f"• {value}"
                )

    return "\n".join(
        lines
    ).strip()


# =============================================================================
# EVIDENCE GUARD
# =============================================================================

def evidence_guard(
    generated_resume: str,
    source_resume: str,
) -> dict:
    """
    Identify numeric claims in generated output that do not occur in source.

    This is a warning/validation mechanism, not a reason to destroy otherwise
    valid source content.
    """

    source_numbers = set(
        _NUMERIC.findall(
            source_resume or ""
        )
    )

    normalized_source = {
        value.replace(
            ",",
            "",
        )
        for value in source_numbers
    }

    unsupported = []

    for number in _NUMERIC.findall(
        generated_resume or ""
    ):

        value = number.strip()

        if (
            value not in source_numbers
            and value.replace(
                ",",
                "",
            )
            not in normalized_source
        ):

            unsupported.append(
                value
            )

    unsupported = dedupe_keep_order(
        unsupported
    )

    return {
        "pass":
            not unsupported,

        "unsupported_numeric_claims":
            unsupported,
    }


# =============================================================================
# FINAL STRUCTURE VALIDATION
# =============================================================================

def experience_structure_guard(
    generated_resume: str,
    source_resume: str,
) -> dict:
    """
    Validate the FINAL text.

    This catches the exact failure seen in the uploaded DOCX:
    employer headings appearing after Education.
    """

    text = (
        generated_resume
        or ""
    )

    lower = text.lower()

    sections = {
        "professional_experience":
            lower.find(
                "professional experience"
            ),

        "earlier_experience":
            lower.find(
                "earlier experience"
            ),

        "education":
            lower.find(
                "education & professional development"
            ),
    }

    warnings = []

    # -------------------------------------------------------------------------#
    # Professional Experience must precede Education
    # -------------------------------------------------------------------------#

    if (
        sections["professional_experience"] >= 0
        and sections["education"] >= 0
        and sections["professional_experience"]
        > sections["education"]
    ):

        warnings.append(
            "PROFESSIONAL EXPERIENCE appears after EDUCATION."
        )

    # -------------------------------------------------------------------------#
    # Earlier Experience must precede Education
    # -------------------------------------------------------------------------#

    if (
        sections["earlier_experience"] >= 0
        and sections["education"] >= 0
        and sections["earlier_experience"]
        > sections["education"]
    ):

        warnings.append(
            "EARLIER EXPERIENCE appears after EDUCATION."
        )

    return {
        "pass":
            not warnings,

        "warnings":
            warnings,

        "section_positions":
            sections,
    }


# =============================================================================
# PUBLIC API
# =============================================================================

def build_resume(
    profile: dict,
    job_description: str,
    analysis: dict,
    source_resume: str,
) -> dict:
    """
    Main resume generation entry point.

    The source resume is parsed BEFORE the LLM is called.

    The LLM improves content.

    Python constructs the final career-history structure.
    """

    # =========================================================================
    # 1. Parse source career structure
    # =========================================================================

    source_sections = _extract_sections(
        source_resume
    )

    source_employers = (
        _parse_employer_experience(
            source_sections.get(
                "experience",
                "",
            )
        )
    )

    source_earlier = (
        _parse_earlier_experience(
            source_sections.get(
                "earlier",
                "",
            )
        )
    )

    source_education = (
        _parse_education(
            source_sections.get(
                "education",
                "",
            )
        )
    )

    # =========================================================================
    # 2. If no employer blocks can be identified, use deterministic output
    # =========================================================================

    if not source_employers:

        resume = _deterministic_resume(
            profile,
            analysis,
            source_resume,
        )

        resume = clean_generated_text(
            resume
        )

        evidence = evidence_guard(
            resume,
            source_resume,
        )

        structure = experience_structure_guard(
            resume,
            source_resume,
        )

        return {
            "optimized_resume":
                resume,

            "generation_mode":
                "deterministic",

            "evidence_validation":
                evidence,

            "experience_structure_validation":
                structure,

            "warnings":
                structure.get(
                    "warnings",
                    [],
                ),

            "structured_llm_output":
                None,
        }

    # =========================================================================
    # 3. Ask the LLM to improve content
    # =========================================================================

    llm_text = invoke_text(
        _resume_prompt(
            profile,
            job_description,
            analysis,
            source_resume,
            source_employers,
            source_earlier,
            source_education,
        )
    )

    structured_output = None

    used_llm = False

    resume = ""

    # =========================================================================
    # 4. Parse and validate LLM result
    # =========================================================================

    if llm_text:

        try:

            structured_output = _extract_json_object(
                llm_text
            )

            valid, validation_errors = (
                _validate_structured_output(
                    structured_output,
                    source_employers,
                    source_earlier,
                    source_education,
                )
            )

            if not valid:

                raise ValueError(
                    "Invalid LLM structure: "
                    + "; ".join(
                        validation_errors
                    )
                )

            # =================================================================
            # 5. SOURCE-LOCKED RENDERING
            #
            # This is the critical part.
            #
            # The source employer objects are used to create:
            #
            # Role
            # Company | Dates
            # Domain
            # Bullets
            #
            # The LLM cannot reorder them.
            # =================================================================

            resume = _render_source_locked_resume(
                structured_output,
                source_employers,
                source_earlier,
                source_education,
                profile,
                analysis,
                source_resume,
            )

            used_llm = True

        except Exception:

            # =================================================================
            # 6. HARD FALLBACK
            #
            # If the LLM does anything structurally wrong, discard its
            # structure completely and build from source.
            # =================================================================

            structured_output = None

            used_llm = False

            resume = _deterministic_resume(
                profile,
                analysis,
                source_resume,
            )

    else:

        resume = _deterministic_resume(
            profile,
            analysis,
            source_resume,
        )

    # =========================================================================
    # 7. Final cleanup
    # =========================================================================

    resume = clean_generated_text(
        resume
    )

    # =========================================================================
    # 8. Final validation
    # =========================================================================

    evidence = evidence_guard(
        resume,
        source_resume,
    )

    structure = experience_structure_guard(
        resume,
        source_resume,
    )

    warnings = []

    if not evidence["pass"]:

        warnings.append(
            "Verify numeric claims: "
            + ", ".join(
                evidence[
                    "unsupported_numeric_claims"
                ]
            )
        )

    warnings.extend(
        structure.get(
            "warnings",
            [],
        )
    )

    # =========================================================================
    # 9. FINAL SAFETY CHECK
    #
    # If something somehow still caused Professional Experience to appear
    # after Education, THROW AWAY the generated result and use the source-only
    # deterministic result.
    # =========================================================================

    if not structure["pass"]:

        resume = _deterministic_resume(
            profile,
            analysis,
            source_resume,
        )

        resume = clean_generated_text(
            resume
        )

        used_llm = False

        structured_output = None

        evidence = evidence_guard(
            resume,
            source_resume,
        )

        structure = experience_structure_guard(
            resume,
            source_resume,
        )

        warnings = list(
            structure.get(
                "warnings",
                [],
            )
        )

    # =========================================================================
    # 10. Return
    # =========================================================================

    return {
        "optimized_resume":
            resume,

        "generation_mode":
            (
                "llm"
                if used_llm
                else "deterministic"
            ),

        "evidence_validation":
            evidence,

        "experience_structure_validation":
            structure,

        "warnings":
            warnings,

        "structured_llm_output":
            structured_output,
    }
