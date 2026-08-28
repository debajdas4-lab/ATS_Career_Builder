"""Lightweight, opt-in company & market research from public pages only."""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from .config import ENABLE_COMPANY_RESEARCH, REQUEST_TIMEOUT
from .utils import dedupe_keep_order, normalize_ws, sentences

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ATSCareerBuilder/1.0)"}


def _fetch(url: str) -> str:
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    return normalize_ws(soup.get_text("\n"))


def build_research_pack(company_url: str = "", leadership_url: str = "",
                        market_urls: list[str] | None = None, market_query: str = "") -> dict:
    empty = {"company_profile": {}, "leadership": [], "strategy": [],
             "market_signals": [], "sources": []}
    if not ENABLE_COMPANY_RESEARCH:
        return empty

    market_urls = market_urls or []
    sources = []
    company_profile = {}
    strategy: list[str] = []
    leadership: list[str] = []

    if company_url:
        text = _fetch(company_url)
        if text:
            company_profile = {"url": company_url, "overview": " ".join(sentences(text)[:4])}
            strategy += sentences(text)[:6]
        sources.append({"type": "company", "label": "Company Website", "url": company_url})

    if leadership_url:
        text = _fetch(leadership_url)
        if text:
            leadership += sentences(text)[:6]
        sources.append({"type": "leadership", "label": "Leadership / IR", "url": leadership_url})

    for url in market_urls:
        text = _fetch(url)
        if text:
            strategy += sentences(text)[:3]
        sources.append({"type": "market", "label": "Market Source", "url": url})

    if not sources:
        return empty

    return {
        "company_profile": company_profile,
        "leadership": dedupe_keep_order(leadership, 8),
        "strategy": dedupe_keep_order(strategy, 10),
        "market_signals": [market_query] if market_query else [],
        "sources": sources,
    }
