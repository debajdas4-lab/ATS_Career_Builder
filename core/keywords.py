"""Fully dynamic keyword extraction.

There is NO fixed skills dictionary here. Keywords are discovered from the job
description itself using:
  1. TF-IDF over 1-3 word phrases (statistical importance within the JD),
  2. a shape-based technical-token detector (acronyms, CamelCase, tech tokens
     like CI/CD, S/4HANA, Node.js), and
  3. a generic HR/boilerplate stop-phrase filter.

This means the engine adapts to ANY role or industry without code changes.
"""
from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer

from .config import MAX_JD_KEYWORDS
from .utils import dedupe_keep_order, norm_token

# Generic recruiting boilerplate that is never a real "skill" keyword.
_BOILERPLATE = {
    "equal opportunity", "opportunity employer", "qualified applicants",
    "regardless of race", "gender identity", "sexual orientation",
    "veteran status", "reasonable accommodation", "years experience",
    "years of experience", "key responsibilities", "candidate requirements",
    "position summary", "roles and responsibilities", "nice to have",
    "we are looking", "you will", "join us", "our team", "the role",
    "strong communication", "communication skills", "fast paced",
    "cross functional", "bachelor degree", "computer science",
}

# Extra English stop words tuned for JDs (kept small & generic on purpose).
_EXTRA_STOP = {
    "work", "working", "ability", "including", "etc", "e.g", "i.e", "using",
    "role", "team", "teams", "company", "organization", "organisation",
    "candidate", "candidates", "responsibilities", "requirements", "job",
    "position", "experience", "years", "will", "must", "strong", "excellent",
    "good", "help", "ensure", "various", "across", "within", "well", "day",
    "world", "make", "new", "also", "may", "like", "one", "us", "our",
    "key", "status", "support", "future", "global", "opportunity", "business",
    "technology", "internal", "external", "groups", "functions", "context",
    "detailed", "broader", "respective", "engaged", "concept", "beyond",
    "understands", "enjoy", "seeking", "committed", "passionate", "join",
    "employer", "applicants", "consideration", "employment", "regard",
    "market", "markets", "platform", "customers", "buyers", "sellers",
    "communicate", "communication", "workshops", "accommodation",
    "accessibility", "close", "collaboration", "unit", "units",
    # marketing / mission fluff commonly seen in JD intros
    "authenticity", "thrives", "bold", "ideas", "welcome", "compass",
    "changing", "way", "shops", "sells", "boundaries", "leaving", "mark",
    "reinvent", "enthusiasts", "passionate", "thinkers", "innovators",
    "dreamers", "communities", "economic", "sustaining", "planet", "color",
    "religion", "race", "gender", "identity", "veteran", "disability",
    "sexual", "orientation", "national", "origin", "protected", "legally",
    "unique", "selves", "everyone", "empowers", "millions", "leader",
    "ecommerce", "commerce", "additional", "artifacts", "example",
    "assessed", "sized", "significant", "religion", "details",
}

# Common TLDs to drop domain/email fragments that leak in from JD footers.
_TLD = re.compile(r"\.(?:com|org|net|io|co|ai|gov|edu)\b", re.I)

# Degree/qualification acronyms are not "skills".
_DEGREES = {"bs", "ba", "ms", "ma", "mba", "phd", "be", "me", "bsc", "msc", "btech", "mtech"}

# Connective/verb-ish words that signal a TF-IDF phrase is a sentence fragment
# rather than a real skill phrase (e.g. "activities create program").
_PHRASE_JUNK = {
    "create", "creating", "created", "removing", "remove", "removed", "details",
    "preferably", "additional", "activities", "including", "ensure", "ensuring",
    "provide", "providing", "supporting", "helping", "leading", "used", "use",
    "understand", "understands", "throughout", "beyond", "various", "closely",
    "effectively", "quickly", "independently", "clearly", "succinctly", "well",
    "make", "made", "get", "got", "take", "taken", "put", "keep", "kept",
}

# Technical-token shapes: ACRONYMS, CamelCase, tokens with tech punctuation.
_TECH_SHAPE = re.compile(
    r"\b(?:[A-Z]{2,5}(?:/[A-Z0-9]{1,6})?"           # SDLC, CI/CD, GST
    r"|[A-Za-z]+\d+[A-Za-z]*"                        # S4HANA, S/4HANA-ish, AI102
    r"|[A-Za-z]+(?:\.[A-Za-z]+)+"                    # Node.js, .NET
    r"|[A-Z][a-z]+(?:[A-Z][a-z]+)+)\b"              # CamelCase e.g. TestRail
)


# Headers that mark the start of the "signal" part of a JD (real requirements).
_SIGNAL_HEADERS = re.compile(
    r"(responsibilities|requirements|qualifications|what you.?ll do|"
    r"what you.?ll need|skills|experience required|key responsibilities|"
    r"candidate requirements|role|about you|you will|must have|nice to have)",
    re.I,
)
# Headers that mark boilerplate we want to drop (EEO, perks, company mission).
_STOP_HEADERS = re.compile(
    r"(equal opportunity|additional details|benefits|perks|about (the )?company|"
    r"who we are|our mission|why join|diversity|accessibility statement)",
    re.I,
)


def isolate_signal(job_description: str) -> str:
    """Return the requirement-bearing portion of a JD, dropping marketing intro
    and EEO/boilerplate outro. Falls back to the whole JD if no headers found."""
    jd = job_description or ""
    lines = jd.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if _SIGNAL_HEADERS.search(line) and len(line.strip()) < 80:
            start = i
            break
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _STOP_HEADERS.search(lines[i]) and len(lines[i].strip()) < 80:
            end = i
            break
    signal = "\n".join(lines[start:end]).strip()
    # If isolation was too aggressive, fall back to the full text.
    return signal if len(signal) > 150 else jd


def _clean_phrase(phrase: str) -> str:
    return re.sub(r"\s+", " ", phrase).strip(" -|•,.")


def _is_boilerplate(phrase: str) -> bool:
    p = phrase.lower().strip()
    return any(b in p for b in _BOILERPLATE)


def _looks_like_noise(token: str) -> bool:
    """Reject requisition IDs, domains/emails, degrees, and mostly-numeric junk."""
    t = token.strip()
    if not t:
        return True
    if _TLD.search(t) or "@" in t:            # ebay.com, x@y.com
        return True
    if t.lower() in _DEGREES:                 # BS, BA, MBA ...
        return True
    letters = sum(c.isalpha() for c in t)
    digits = sum(c.isdigit() for c in t)
    if digits and digits >= letters:          # R0074903, 2024q3, 3d
        return True
    if len(t) <= 2 and t.upper() != t:        # stray 1-2 char lowercase
        return True
    return False


def _phrase_is_junk(phrase: str) -> bool:
    """A multi-word phrase is junk if any token is a connective/verb fragment."""
    toks = phrase.lower().split()
    if len(toks) > 2:                         # trigrams are almost always noisy
        return True
    if "/" in phrase and not _TECH_SHAPE.search(phrase):  # "and/or significant"
        return True
    return any(tok in _PHRASE_JUNK or tok in _EXTRA_STOP for tok in toks)


def _single_token_ok(token: str) -> bool:
    """Keep a single-word keyword only if it is a strong, meaningful term."""
    t = token.lower().strip()
    if len(t) < 4:                            # too short to be a distinctive skill
        return t.upper() == token and len(t) >= 2  # allow real acronyms (SAP, AWS)
    if t in _EXTRA_STOP or t in _PHRASE_JUNK or t in _DEGREES:
        return False
    if _looks_like_noise(token):
        return False
    return True


# Full stopword set used by RAKE to split candidate phrases at boundaries.
_ENGLISH_STOP = set(TfidfVectorizer(stop_words="english").get_stop_words())
_RAKE_STOP = _ENGLISH_STOP | _EXTRA_STOP | _PHRASE_JUNK | _DEGREES

# Split candidate keyphrases on punctuation and coordinating conjunctions.
_CLAUSE_SPLIT = re.compile(r"[,.;:!?()/\n\t]|\band\b|\bor\b|\bwith\b|\bfor\b|\bto\b|\bof\b|\bin\b", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")


def _rake_phrases(text: str, top_n: int) -> list[str]:
    """RAKE-style keyphrase extraction.

    Splits the text into candidate phrases at stopwords and punctuation, so the
    surviving phrases are contiguous runs of content words (e.g. "program
    management", "milestone tracking"). Phrases are scored by RAKE's word-degree
    heuristic, which favours words that co-occur in longer phrases.
    """
    # 1) Build candidate phrases: contiguous non-stopword word runs.
    phrases: list[list[str]] = []
    for clause in _CLAUSE_SPLIT.split(text.lower()):
        current: list[str] = []
        for word in _WORD.findall(clause):
            if word in _RAKE_STOP or len(word) < 2:
                if current:
                    phrases.append(current)
                    current = []
            else:
                current.append(word)
        if current:
            phrases.append(current)

    # 2) RAKE word scores: degree(word) / frequency(word).
    freq: dict[str, int] = {}
    degree: dict[str, int] = {}
    for words in phrases:
        deg = len(words) - 1
        for w in words:
            freq[w] = freq.get(w, 0) + 1
            degree[w] = degree.get(w, 0) + deg + 1

    word_score = {w: degree[w] / freq[w] for w in freq}

    # 3) Score each unique phrase; keep 1-2 word phrases (drop long noisy runs).
    scored: dict[str, float] = {}
    for words in phrases:
        if not (1 <= len(words) <= 2):
            continue
        phrase = " ".join(words)
        if _is_boilerplate(phrase):
            continue
        if len(words) == 1 and not _single_token_ok(words[0]):
            continue
        scored[phrase] = sum(word_score.get(w, 0) for w in words)

    ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    return [_clean_phrase(p) for p, _ in ranked[: top_n * 2]]


# Backwards-compatible alias.
_tfidf_phrases = _rake_phrases


def _tech_tokens(text: str) -> list[str]:
    found = _TECH_SHAPE.findall(text or "")
    cleaned = [_clean_phrase(t) for t in found if not _looks_like_noise(t)]
    return dedupe_keep_order(cleaned)


def extract_keywords(job_description: str, limit: int = MAX_JD_KEYWORDS) -> list[str]:
    """Return the most important, de-duplicated keywords for a JD (dynamic).

    Keywords are extracted from the requirement-bearing portion of the JD so
    marketing prose and EEO boilerplate do not pollute the result.
    """
    jd = isolate_signal(job_description)
    tech = _tech_tokens(jd)
    phrases = _tfidf_phrases(jd, limit)

    # Merge: technical tokens + phrases. Prefer multi-word phrases and tech
    # tokens (high recruiter value); single generic words go last.
    multi_phrases = [p for p in phrases if " " in p]
    single_phrases = [p for p in phrases if " " not in p]
    merged = dedupe_keep_order(tech + multi_phrases + single_phrases)

    # Drop single tokens fully contained in a retained multi-word phrase
    # to avoid "product" AND "product management" both appearing.
    multi = [k for k in merged if " " in k]
    result = []
    for k in merged:
        if " " not in k and any(k.lower() in m.lower().split() and len(m.split()) > 1 for m in multi):
            if k not in tech:  # keep only strong standalone tech tokens
                continue
        result.append(k)

    # Cap weak single-word tail so the set stays recruiter-relevant: keep all
    # multi-word / tech keywords, but limit bare single words.
    final, singles = [], 0
    for k in result:
        if " " not in k and k not in tech:
            singles += 1
            if singles > max(6, limit // 4):
                continue
        final.append(k)
    return dedupe_keep_order(final, limit)


def keyword_weight(keyword: str, technical_tokens: set[str]) -> float:
    """Weight recruiter-critical tokens (tech / multi-word) slightly higher."""
    if keyword in technical_tokens:
        return 1.3
    if " " in keyword:
        return 1.15
    return 1.0
