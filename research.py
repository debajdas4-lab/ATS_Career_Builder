from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .config import TAVILY_API_KEY


def clean_source_url(value: str) -> str:
    if not value:
        return ""
    text = str(value).strip()
    match = re.search(r"https?://[^\s\]\}\)\"'<]+", text)
    if match:
        text = match.group(0)
    return text.rstrip("]}'\"),.;")


def fetch_public_page(url: str, *, max_chars: int = 10000) -> tuple[str, str]:
    url = clean_source_url(url)
    if not url:
        return "", ""
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Research URL must start with http:// or https://")

    with httpx.Client(follow_redirects=True, timeout=15) as client:
        response = client.get(url, headers={"User-Agent": "ATSCareerGuide/1.0"})
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text[:max_chars], clean_source_url(str(response.url))


def search_market(query: str, max_results: int = 4) -> list[dict[str, str]]:
    if not TAVILY_API_KEY or not query.strip():
        return []
    response = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results, "include_answer": False},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {
            "title": str(item.get("title", "")),
            "url": clean_source_url(str(item.get("url", ""))),
            "content": str(item.get("content", ""))[:1200],
        }
        for item in data.get("results", [])
    ]


def company_name_from_text(text: str, url: str) -> str:
    if text:
        first = re.split(r"[|–—-]", text.strip(), maxsplit=1)[0].strip()
        if 2 <= len(first) <= 80:
            return first
    host = urlparse(url).netloc.replace("www.", "")
    return host.split(".")[0].replace("-", " ").title() if host else "Company Research"


def build_company_profile(text: str, url: str) -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", text or "").strip()
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    useful = [s.strip() for s in sentences if 45 <= len(s.strip()) <= 320][:3]
    overview = " ".join(useful) or clean[:500]
    return {
        "name": company_name_from_text(clean, url),
        "overview": overview,
        "url": clean_source_url(url),
    }


def infer_strategy_signals(text: str) -> list[str]:
    lower = (text or "").lower()
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
    return [label for label, terms in mapping.items() if any(term in lower for term in terms)]


def infer_competitors(text: str) -> list[str]:
    candidates = re.findall(
        r"\b(?:Microsoft|Amazon|Google|Oracle|SAP|Salesforce|Accenture|Deloitte|IBM|Cisco)\b",
        text or "",
        flags=re.I,
    )
    return list(dict.fromkeys(candidates))


def build_research_pack(
    company_url: str = "",
    leadership_url: str = "",
    market_urls: list[str] | None = None,
    market_query: str = "",
) -> dict[str, Any]:
    sources: list[dict[str, str]] = []
    company_profile: dict[str, Any] = {}
    leadership: list[dict[str, Any]] = []
    strategy: list[str] = []
    market_signals: list[str] = []
    competitors: list[str] = []

    company_url = clean_source_url(company_url)
    leadership_url = clean_source_url(leadership_url)

    if company_url:
        text, final_url = fetch_public_page(company_url)
        company_profile = build_company_profile(text, final_url or company_url)
        sources.append({"type": "company", "label": "Company Website", "url": clean_source_url(final_url or company_url)})
        strategy = infer_strategy_signals(text)
        competitors = infer_competitors(text)

    if leadership_url:
        text, final_url = fetch_public_page(leadership_url)
        leadership = [{"overview": build_company_profile(text, final_url or leadership_url).get("overview", ""), "url": clean_source_url(final_url or leadership_url)}]
        sources.append({"type": "leadership", "label": "Leadership / Investor Relations", "url": clean_source_url(final_url or leadership_url)})

    for raw_url in market_urls or []:
        url = clean_source_url(raw_url)
        if not url:
            continue
        text, final_url = fetch_public_page(url)
        market_signals.extend(infer_strategy_signals(text))
        sources.append({"type": "market", "label": "Market Research", "url": clean_source_url(final_url or url)})

    if market_query.strip():
        for result in search_market(market_query):
            market_signals.extend(infer_strategy_signals(result.get("content", "")))
            sources.append({
                "type": "market-search",
                "label": result.get("title", "") or "Market Search Result",
                "url": clean_source_url(result.get("url", "")),
            })

    # Guaranteed non-empty research package whenever a research input was supplied.
    if company_url and not company_profile:
        company_profile = build_company_profile("", company_url)
        sources.append({"type": "company", "label": "Company Website", "url": company_url})

    unique_sources = []
    seen_sources = set()
    for source in sources:
        key = (source.get("type", ""), source.get("label", ""), source.get("url", ""))
        if key not in seen_sources:
            seen_sources.add(key)
            unique_sources.append(source)

    return {
        "company_profile": company_profile,
        "leadership": leadership,
        "strategy": list(dict.fromkeys(strategy))[:12],
        "recent_signals": [],
        "competitors": competitors[:10],
        "sources": unique_sources,
        "market_signals": list(dict.fromkeys(market_signals))[:15],
    }
