"""Dynamic, explainable ATS scoring.

The score is a transparent weighted blend of three signals, all computed at
runtime from the actual resume + JD (no fixed alias table, no hardcoded numbers):

  * keyword_coverage   - how many dynamically-extracted JD keywords are evidenced
  * semantic_similarity- TF-IDF cosine similarity between resume and JD
  * section_completeness- does the resume contain the sections ATS parsers expect

Every keyword decision carries the evidence snippet that justified it, so the UI
can show *why* a score was given.
"""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import (
    FULL_MATCH_THRESHOLD,
    PARTIAL_MATCH_THRESHOLD,
    SEMANTIC_REFERENCE,
    WEIGHT_KEYWORD_COVERAGE,
    WEIGHT_SECTION_COMPLETENESS,
    WEIGHT_SEMANTIC_SIMILARITY,
)
from .keywords import extract_keywords, keyword_weight, _tech_tokens
from .utils import norm_token, sentences, similarity

_EXPECTED_SECTIONS = {
    "summary": ["summary", "profile", "objective", "about"],
    "experience": ["experience", "employment", "work history", "professional experience"],
    "skills": ["skills", "competencies", "technologies", "expertise"],
    "education": ["education", "qualification", "academic"],
}


def _match_keyword(keyword: str, resume_norm: str, resume_sentences: list[str]) -> tuple[float, str]:
    """Return (confidence, evidence) for one keyword against the resume."""
    kw = norm_token(keyword)
    if not kw:
        return 0.0, ""
    # 1) Exact / substring presence -> full match.
    if kw in resume_norm:
        return 1.0, keyword
    # 2) Fuzzy phrase match against resume sentences -> partial/full.
    best_score, best_ev = 0.0, ""
    for sent in resume_sentences:
        s = similarity(kw, sent)
        if s > best_score:
            best_score, best_ev = s, sent[:140]
    return best_score, best_ev


def find_wording_gaps(missing_keywords: list[str], resume_text: str, floor: float = 0.55) -> list[str]:
    """JD keywords that are 'missing' by exact match but for which the resume has
    RELATED evidence (fuzzy match >= floor). These are wording gaps — safe and
    ethical to align to the JD's terminology because the candidate did the work.
    """
    resume_sents = sentences(resume_text)
    out = []
    for kw in missing_keywords:
        best = max((similarity(kw, s) for s in resume_sents), default=0.0)
        if floor <= best < FULL_MATCH_THRESHOLD:
            out.append(kw)
    return out


def _section_completeness(resume_text: str) -> tuple[float, list[str]]:
    low = (resume_text or "").lower()
    present, missing = [], []
    for section, aliases in _EXPECTED_SECTIONS.items():
        if any(a in low for a in aliases):
            present.append(section)
        else:
            missing.append(section)
    return len(present) / len(_EXPECTED_SECTIONS), missing


def _semantic_similarity(resume_text: str, job_description: str) -> float:
    docs = [resume_text or "", job_description or ""]
    try:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        matrix = vec.fit_transform(docs)
        return float(cosine_similarity(matrix[0], matrix[1])[0][0])
    except ValueError:
        return 0.0


def score_resume(resume_text: str, job_description: str, keywords: list[str] | None = None) -> dict:
    """Compute a full, explainable ATS analysis (dynamic)."""
    resume_text = resume_text or ""
    resume_norm = norm_token(resume_text)
    resume_sents = sentences(resume_text)
    keywords = keywords or extract_keywords(job_description)
    tech = set(_tech_tokens(job_description))

    matched, partial, missing, evidence_map = [], [], [], {}
    weighted_hits, total_weight = 0.0, 0.0

    for kw in keywords:
        w = keyword_weight(kw, tech)
        total_weight += w
        conf, ev = _match_keyword(kw, resume_norm, resume_sents)
        if conf >= FULL_MATCH_THRESHOLD:
            matched.append(kw)
            weighted_hits += w
            evidence_map[kw] = ev
        elif conf >= PARTIAL_MATCH_THRESHOLD:
            partial.append(kw)
            weighted_hits += w * 0.5
            evidence_map[kw] = ev
        else:
            missing.append(kw)

    keyword_coverage = (weighted_hits / total_weight) if total_weight else 0.0
    semantic_raw = _semantic_similarity(resume_text, job_description)
    # Normalise cosine into a fair 0-1 signal (see SEMANTIC_REFERENCE).
    semantic = min(1.0, semantic_raw / SEMANTIC_REFERENCE) if SEMANTIC_REFERENCE else semantic_raw
    completeness, missing_sections = _section_completeness(resume_text)

    raw = (
        WEIGHT_KEYWORD_COVERAGE * keyword_coverage
        + WEIGHT_SEMANTIC_SIMILARITY * semantic
        + WEIGHT_SECTION_COMPLETENESS * completeness
    )
    score = int(round(100 * raw))
    score = max(0, min(100, score))

    if score >= 75:
        recommendation = "STRONG FIT"
    elif score >= 55:
        recommendation = "MODERATE FIT"
    else:
        recommendation = "NEEDS TAILORING"

    return {
        "score": score,
        "recommendation": recommendation,
        "components": {
            "keyword_coverage": round(keyword_coverage, 3),
            "semantic_similarity": round(semantic, 3),
            "semantic_raw": round(semantic_raw, 3),
            "section_completeness": round(completeness, 3),
        },
        "matched_keywords": matched,
        "partial_keywords": partial,
        "missing_keywords": missing,
        "missing_sections": missing_sections,
        "evidence_map": evidence_map,
        "keywords_evaluated": keywords,
    }
