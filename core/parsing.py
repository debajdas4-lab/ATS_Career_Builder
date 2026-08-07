from __future__ import annotations

import re
from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader


def extract_resume_text(filename: str, content: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif name.endswith(".docx"):
        doc = Document(BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                text += "\n" + " | ".join(cell.text for cell in row.cells)
    elif name.endswith(".txt") or name.endswith(".md"):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Supported resume formats are PDF, DOCX, TXT and MD.")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text.strip()) < 80:
        raise ValueError("The uploaded file did not contain enough readable text.")
    return text.strip()


async def fetch_job_description(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Job-description URL must start with http:// or https://.")
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        response = await client.get(url, headers={"User-Agent": "ResumeOptimizer/1.0"})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    if len(text) < 100:
        raise ValueError("The job-description page did not expose enough readable text.")
    return text[:30000]

