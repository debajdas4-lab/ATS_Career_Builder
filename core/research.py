"""Robust public company / market research adapter for ATS Career Builder."""
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


def fetch_public_page(url: str, *, max_chars: int = 12000) -> tuple[str, str]:
    url = clean_source_url(url)
    if not url:
        return "", ""
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Research URL must start with http:// or https://")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(follow_redirects=True, timeout=20.0, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        element.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text[:max_chars], clean_source_url(str(response.url))


def search_market(query: str, max_results: int = 5) -> list[dict[str, str]]:
    if not TAVILY_API_KEY or not query.strip():
        return []
    response = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query.strip(),
            "max_results": max_results,
            "include_answer": False,
        },
        timeout=25.0,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {
            "title": str(item.get("title", "")),
            "url": clean_source_url(str(item.get("url", ""))),
            "content": str(item.get("content", ""))[:1600],
        }
        for item in data.get("results", [])
        if item.get("url")
    ]


def company_name_from_text(text: str, url: str) -> str:
    if text:
        first = re.split(r"[|–—-]", text.strip(), maxsplit=1)[0].strip()
        if 2 <= len(first) <= 90:
            return first
    host = urlparse(url).netloc.replace("www.", "")
    return host.split(".")[0].replace("-", " ").title() if host else "Company Research"


def build_company_profile(text: str, url: str) -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", text or "").strip()
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    useful = [s.strip() for s in sentences if 45 <= len(s.strip()) <= 360][:4]
    overview = " ".join(useful) or clean[:900]
    return {
        "name": company_name_from_text(clean, url),
        "overview": overview,
        "url": clean_source_url(url),
    }


def infer_strategy_signals(text: str) -> list[str]:
    lower = (text or "").lower()
    mapping = {
        "growth / expansion": ["growth", "expansion", "scale", "scaling"],
        "cost optimization": ["cost", "efficiency", "productivity", "optimization"],
        "ai transformation": ["artificial intelligence", "generative ai", "genai", "machine learning", "ai"],
        "cloud modernization": ["cloud", "modernization", "migration", "hybrid cloud"],
        "customer experience": ["customer experience", "customer-centric", "user experience"],
        "operational excellence": ["operational excellence", "automation", "process improvement"],
        "security and compliance": ["security", "cybersecurity", "identity", "compliance", "privacy"],
        "enterprise platforms": ["enterprise platform", "enterprise software", "platform"],
    }
    return [label for label, terms in mapping.items() if any(term in lower for term in terms)]


def infer_competitors(text: str) -> list[str]:
    candidates = re.findall(
        r"\b(?:Microsoft|Amazon|AWS|Google|Oracle|SAP|Salesforce|Accenture|Deloitte|IBM|Cisco|HP|Dell|HPE)\b",
        text or "",
        flags=re.I,
    )
    return list(dict.fromkeys(candidates))


def _company_fallback(company_url: str, message: str = "") -> dict[str, Any]:
    url = clean_source_url(company_url)
    name = company_name_from_text("", url)
    return {
        "name": name,
        "overview": message or f"Public company page supplied: {url}",
        "url": url,
    }


def build_research_pack(
    company_url: str = "",
    leadership_url: str = "",
    market_urls: list[str] | None = None,
    market_query: str = "",
) -> dict[str, Any]:
    company_url = clean_source_url(company_url)
    leadership_url = clean_source_url(leadership_url)
    sources: list[dict[str, str]] = []
    company_profile: dict[str, Any] = {}
    leadership: list[dict[str, Any]] = []
    strategy: list[str] = []
    market_signals: list[str] = []
    competitors: list[str] = []
    warnings: list[str] = []

    if company_url:
        try:
            text, final_url = fetch_public_page(company_url)
            target_url = final_url or company_url
            if text:
                company_profile = build_company_profile(text, target_url)
                strategy.extend(infer_strategy_signals(text))
                competitors.extend(infer_competitors(text))
            else:
                company_profile = _company_fallback(company_url, "The company page returned no readable text; the supplied public URL is retained as the research source.")
        except Exception as exc:
            warnings.append(f"Direct company-page retrieval failed: {type(exc).__name__}: {exc}")
            company_profile = _company_fallback(company_url, "Direct company-page retrieval failed; the supplied public URL is retained and the research adapter will use search results when available.")
            if TAVILY_API_KEY:
                try:
                    host = urlparse(company_url).netloc.replace("www.", "")
                    results = search_market(f"site:{host} company strategy products AI enterprise latest", max_results=5)
                    combined = " ".join(r.get("content", "") for r in results)
                    if combined:
                        company_profile = build_company_profile(combined, company_url)
                        strategy.extend(infer_strategy_signals(combined))
                        competitors.extend(infer_competitors(combined))
                    for result in results:
                        sources.append({
                            "type": "company-search",
                            "label": result.get("title", "Company Search Result"),
                            "url": result.get("url", ""),
                        })
                except Exception as exc2:
                    warnings.append(f"Company search fallback failed: {type(exc2).__name__}: {exc2}")
        sources.append({"type": "company", "label": "Company Website", "url": company_url})

    if leadership_url:
        try:
            text, final_url = fetch_public_page(leadership_url)
            target_url = final_url or leadership_url
            overview = build_company_profile(text, target_url).get("overview", "")
            leadership.append({"overview": overview, "url": target_url})
            sources.append({"type": "leadership", "label": "Leadership / Investor Relations", "url": target_url})
        except Exception as exc:
            warnings.append(f"Leadership-page retrieval failed: {type(exc).__name__}: {exc}")
            leadership.append({"overview": "Leadership page could not be retrieved during this run.", "url": leadership_url})
            sources.append({"type": "leadership", "label": "Leadership / Investor Relations", "url": leadership_url})

    for raw_url in market_urls or []:
        url = clean_source_url(raw_url)
        if not url:
            continue
        try:
            text, final_url = fetch_public_page(url)
            market_signals.extend(infer_strategy_signals(text))
            sources.append({"type": "market", "label": "Market Research", "url": final_url or url})
        except Exception as exc:
            warnings.append(f"Market URL retrieval failed for {url}: {type(exc).__name__}: {exc}")
            sources.append({"type": "market", "label": "Market Research URL", "url": url})

    if market_query.strip() and TAVILY_API_KEY:
        try:
            for result in search_market(market_query):
                content = result.get("content", "")
                market_signals.extend(infer_strategy_signals(content))
                sources.append({
                    "type": "market-search",
                    "label": result.get("title", "Market Search Result"),
                    "url": result.get("url", ""),
                })
        except Exception as exc:
            warnings.append(f"Market search failed: {type(exc).__name__}: {exc}")
    elif market_query.strip() and not TAVILY_API_KEY:
        warnings.append("Market search query was supplied, but TAVILY_API_KEY is not configured.")

    if company_url and not company_profile:
        company_profile = _company_fallback(company_url)

    unique_sources: list[dict[str, str]] = []
    seen = set()
    for source in sources:
        key = (source.get("type", ""), source.get("label", ""), source.get("url", ""))
        if key not in seen:
            seen.add(key)
            unique_sources.append(source)

    return {
        "company_profile": company_profile,
        "leadership": leadership,
        "strategy": list(dict.fromkeys(strategy))[:12],
        "recent_signals": [],
        "competitors": list(dict.fromkeys(competitors))[:10],
        "sources": unique_sources,
        "market_signals": list(dict.fromkeys(market_signals))[:15],
        "research_warning": " | ".join(warnings) if warnings else "",
    }
