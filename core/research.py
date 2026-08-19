from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup


def fetch_public_page(url: str, max_chars: int = 10000) -> tuple[str, str]:
    if not url:
        return "", ""
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        response = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        element.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()[:max_chars], str(response.url)


def build_research_pack(company_url="", leadership_url="", market_urls=None, market_query=""):
    output = {"company_profile": {}, "leadership": [], "strategy": [], "market_signals": [], "sources": []}
    items = [("company", company_url), ("leadership", leadership_url)] + [("market", url) for url in (market_urls or [])]
    for kind, url in items:
        if not url:
            continue
        text, final_url = fetch_public_page(url)
        lower = text.lower()
        signals = [label for label, terms in {
            "growth": ["growth", "scale"],
            "AI transformation": ["generative ai", "artificial intelligence"],
            "cloud modernization": ["cloud", "modernization"],
            "operational excellence": ["operational excellence", "automation"],
            "risk and compliance": ["risk", "compliance"],
        }.items() if any(term in lower for term in terms)]
        if kind == "company":
            output["company_profile"] = {"overview": text[:800], "url": final_url}
            output["strategy"] = signals
        elif kind == "leadership":
            output["leadership"].append({"overview": text[:800], "url": final_url})
        else:
            output["market_signals"] += signals
        output["sources"].append({"type": kind, "url": final_url})
    output["market_signals"] = list(dict.fromkeys(output["market_signals"]))
    return output
