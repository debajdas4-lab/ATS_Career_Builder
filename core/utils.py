"""Small, dependency-light text utilities shared across the engine."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_WS = re.compile(r"[ \t]+")
_MULTINL = re.compile(r"\n{3,}")


def normalize_ws(text: str) -> str:
    """Collapse runs of spaces/tabs and excessive blank lines."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS.sub(" ", text)
    text = _MULTINL.sub("\n\n", text)
    return text.strip()


def norm_token(text: str) -> str:
    """Lowercase and strip punctuation, keeping tech chars like + # . /"""
    return re.sub(r"[^a-z0-9+#./ ]+", " ", (text or "").lower()).strip()


def similarity(a: str, b: str) -> float:
    """Order-insensitive token similarity ratio in [0, 1]."""
    a_set = " ".join(sorted(set(norm_token(a).split())))
    b_set = " ".join(sorted(set(norm_token(b).split())))
    if not a_set or not b_set:
        return 0.0
    return SequenceMatcher(None, a_set, b_set).ratio()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+|[•;]", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 8]


def bullet_lines(text: str) -> list[str]:
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line[:2] in ("- ", "* ", "• ", "▪ ", "◦ "):
            out.append(line[2:].strip())
    return out


def dedupe_keep_order(values, limit: int | None = None) -> list:
    seen, out = set(), []
    for v in values:
        key = str(v).strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(v)
            if limit and len(out) >= limit:
                break
    return out


def clean_generated_text(value) -> str:
    """Strip markdown fences/emphasis so exported resume text stays clean."""
    if not value:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for raw in text.split("\n"):
        line = raw.strip()
        if line in {"---", "***", "___", "```", "```markdown", "```text"}:
            out.append("")
            continue
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"__(.*?)__", r"\1", line)
        out.append(line)
    return "\n".join(out).strip()
