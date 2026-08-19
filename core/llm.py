from __future__ import annotations

import json
import re

from .config import DEMO_MODE, GROQ_API_KEY, GROQ_MAX_OUTPUT_TOKENS, GROQ_MODEL


def parse_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {}
            except Exception:
                pass
    return {}


def _client(max_tokens: int):
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=GROQ_MODEL,
        temperature=0.08,
        api_key=GROQ_API_KEY,
        max_tokens=max_tokens,
        max_retries=2,
    )


def invoke_json(prompt: str, max_tokens: int = 700) -> dict:
    if DEMO_MODE or not GROQ_API_KEY:
        return {}
    content = _client(min(max_tokens, GROQ_MAX_OUTPUT_TOKENS)).invoke(prompt).content
    return parse_json(content if isinstance(content, str) else str(content))


def invoke_text(prompt: str, max_tokens: int | None = None) -> str:
    if DEMO_MODE or not GROQ_API_KEY:
        return ""
    budget = max_tokens or GROQ_MAX_OUTPUT_TOKENS
    content = _client(min(budget, GROQ_MAX_OUTPUT_TOKENS)).invoke(prompt).content
    return content.strip() if isinstance(content, str) else str(content).strip()
