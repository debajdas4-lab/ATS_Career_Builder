from __future__ import annotations

import re
from typing import Any

import httpx

from .config import TAVILY_API_KEY
from bs4 import BeautifulSoup


def fetch_public_page(url: str, *, max_chars: int = 12000) -> tuple[str, str]:
    if not url:
        return "", ""
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Research URL must start with http:// or https://")
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        response = client.get(url, headers={"User-Agent": "ATSCareerGuide/1.0"})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text[:max_chars], str(response.url)



def search_market(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Optional market-search adapter. Uses Tavily when configured; otherwise returns no results."""
    if not TAVILY_API_KEY or not query.strip():
        return []
    response = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results, "include_answer": False},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {"title": str(item.get("title", "")), "url": str(item.get("url", "")), "content": str(item.get("content", ""))}
        for item in data.get("results", [])
    ]


def build_research_pack(company_url: str = "", leadership_url: str = "", market_urls: list[str] | None = None, market_query: str = "") -> dict[str, Any]:
    sources: list[dict[str, str]] = []
    company_profile: dict[str, Any] = {}
    leadership: list[dict[str, Any]] = []
    strategy: list[str] = []
    market_signals: list[str] = []
    competitors: list[str] = []

    if company_url:
        text, final_url = fetch_public_page(company_url)
        company_profile = {"raw_text": text, "url": final_url}
        sources.append({"type": "company", "url": final_url})
        strategy = infer_strategy_signals(text)
        competitors = infer_competitors(text)

    if leadership_url:
        text, final_url = fetch_public_page(leadership_url)
        leadership = [{"raw_text": text, "url": final_url}]
        sources.append({"type": "leadership", "url": final_url})

    for url in market_urls or []:
        text, final_url = fetch_public_page(url)
        market_signals.extend(infer_strategy_signals(text))
        sources.append({"type": "market", "url": final_url})

    if market_query:
        for result in search_market(market_query):
            market_signals.extend(infer_strategy_signals(result.get("content", "")))
            sources.append({"type": "market-search", "url": result.get("url", ""), "title": result.get("title", "")})

    if company_url and not company_profile:
        company_profile = {"name": "Company Research", "overview": "The public company page was reached, but readable company text was limited.", "url": clean_source_url(company_url)}
        sources.append({"type": "company", "label": "Company Website", "url": clean_source_url(company_url)})

    return {
        "company_profile": company_profile,
        "leadership": leadership,
        "strategy": list(dict.fromkeys(strategy))[:12],
        "recent_signals": [],
        "competitors": competitors[:10],
        "sources": sources,
        "market_signals": list(dict.fromkeys(market_signals))[:15],
    }


def infer_strategy_signals(text: str) -> list[str]:
    lower = text.lower()
    signals = []
    mapping = {
        "growth": ["growth", "expansion", "scale"],
        "cost optimization": ["cost", "efficiency", "productivity"],
        "ai transformation": ["artificial intelligence", "generative ai", "genai", "ai"],
        "cloud modernization": ["cloud", "modernization", "migration"],
        "customer experience": ["customer experience", "customer-centric", "user experience"],
        "operational excellence": ["operational excellence", "automation", "process improvement"],
        "sustainability": ["sustainability", "net zero", "carbon"],
        "security and risk": ["security", "cybersecurity", "risk", "compliance"],
    }
    for label, terms in mapping.items():
        if any(term in lower for term in terms):
            signals.append(label)
    return signals


def infer_competitors(text: str) -> list[str]:
    candidates = re.findall(r"\b(?:Microsoft|Amazon|Google|Oracle|SAP|Salesforce|Accenture|Deloitte|IBM|Cisco)\b", text, flags=re.I)
    return list(dict.fromkeys(candidates))
