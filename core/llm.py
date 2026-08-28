"""Optional LLM abstraction (OpenAI-compatible: Groq / OpenAI / Azure OpenAI).

Design goals:
  * The app is ALWAYS runnable. If no API key is configured, callers fall back
    to the deterministic builders, so there is never a hard dependency on a
    paid provider (this is what previously caused 413/429/timeout failures).
  * Model, endpoint and token budget come from config (env), never hardcoded.
  * One thin, retriable call surface used by every agent.
"""
from __future__ import annotations

import json
import logging

import httpx

from .config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    llm_enabled,
)

log = logging.getLogger("ats.llm")


def _chat(prompt: str, *, max_tokens: int, temperature: float, json_mode: bool) -> str:
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise, truthful executive resume and career strategist. "
                                          "Never invent metrics, employers, or experience not present in the source."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=httpx.Timeout(120.0, read=None)) as client:
        resp = client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def invoke_text(prompt: str, max_tokens: int | None = None, temperature: float | None = None) -> str | None:
    """Return generated text, or None if no LLM is configured / call fails."""
    if not llm_enabled():
        return None
    try:
        return _chat(
            prompt,
            max_tokens=max_tokens or LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE if temperature is None else temperature,
            json_mode=False,
        )
    except Exception as exc:  # never crash the pipeline on provider errors
        log.warning("LLM text call failed: %s", exc)
        return None


def invoke_json(prompt: str, max_tokens: int | None = None) -> dict | None:
    """Return parsed JSON, or None if no LLM is configured / call fails."""
    if not llm_enabled():
        return None
    try:
        raw = _chat(prompt, max_tokens=max_tokens or 900, temperature=0.1, json_mode=True)
        return json.loads(raw)
    except Exception as exc:
        log.warning("LLM json call failed: %s", exc)
        return None
