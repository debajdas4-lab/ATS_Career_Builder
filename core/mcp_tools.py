from __future__ import annotations

import re
from collections import Counter


STOPWORDS = {
    "about", "after", "also", "and", "are", "been", "being", "from", "have",
    "into", "more", "our", "that", "their", "this", "with", "will", "your",
    "years", "using", "work", "working", "role", "team", "the", "for", "you",
}


def extract_keywords(job_description: str, limit: int = 35) -> list[str]:
    phrases = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{2,}", job_description.lower())
    counts = Counter(word for word in phrases if word not in STOPWORDS)
    return [word for word, _ in counts.most_common(limit)]


def score_resume(resume_text: str, keywords: list[str]) -> dict:
    normalized = resume_text.lower()
    matched = [keyword for keyword in keywords if keyword.lower() in normalized]
    missing = [keyword for keyword in keywords if keyword.lower() not in normalized]
    score = round((len(matched) / len(keywords)) * 100) if keywords else 0
    sections = ["experience", "education", "skills"]
    section_hits = sum(section in normalized for section in sections)
    return {
        "score": min(100, round(score * 0.8 + (section_hits / len(sections)) * 20)),
        "matched_keywords": matched,
        "missing_keywords": missing,
        "section_count": section_hits,
    }

