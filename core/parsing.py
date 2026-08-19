from __future__ import annotations

import json
import re
from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader


def extract_resume_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    elif lower.endswith(".docx"):
        document = Document(BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        for table in document.tables:
            for row in table.rows:
                text += "\n" + " | ".join(cell.text for cell in row.cells)
    elif lower.endswith((".txt", ".md")):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Supported formats: PDF, DOCX, TXT and MD.")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 80:
        raise ValueError("The uploaded file did not contain enough readable text.")
    return text


async def fetch_job_description(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Job URL must start with http:// or https://")
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            data = json.loads(script.string or script.get_text(" "))
            for item in data if isinstance(data, list) else [data]:
                if isinstance(item, dict) and str(item.get("@type", "")).lower() == "jobposting":
                    candidates.append(BeautifulSoup(str(item.get("description", "")), "html.parser").get_text(" "))
        except Exception:
            pass
    for selector in ("main", "article", "[role=main]", ".job-description", "#job-description"):
        candidates += [element.get_text(" ", strip=True) for element in soup.select(selector)]
    result = max((re.sub(r"\s+", " ", item).strip() for item in candidates if len(item) > 80), key=len, default="")
    if not result:
        raise ValueError("Could not extract the JD. Paste the full JD instead.")
    return result[:50000]
