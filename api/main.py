from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.career_graph_v3 import run_career_guide_v3
from core.config import MAX_RESUME_BYTES
from core.docx_export import build_docx
from core.parsing import extract_resume_text, fetch_job_description

app = FastAPI(title="ATS Career Builder V3", version="3.1.0")


class ExportRequest(BaseModel):
    resume_text: str = Field(min_length=1)


@app.get("/")
def health():
    return {"status": "Running", "version": "3.1.0"}


@app.post("/v3/career-guide")
async def career_guide(
    resume: UploadFile = File(...),
    analysis_mode: str = Form("Fast Resume"),
    job_description: str = Form(""),
    job_url: str = Form(""),
    company_url: str = Form(""),
    leadership_url: str = Form(""),
    market_urls: str = Form(""),
    market_query: str = Form(""),
    linkedin_profile: str = Form(""),
    naukri_profile: str = Form(""),
):
    content = await resume.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume exceeds the configured size limit")
    try:
        resume_text = extract_resume_text(resume.filename or "resume.txt", content)
        jd = job_description.strip() or await fetch_job_description(job_url.strip())
        result = run_career_guide_v3(
            analysis_mode=analysis_mode,
            resume_text=resume_text,
            job_description=jd,
            job_url=job_url,
            company_url=company_url,
            leadership_url=leadership_url,
            market_urls=[item.strip() for item in market_urls.splitlines() if item.strip()],
            market_query=market_query,
            linkedin_profile=linkedin_profile,
            naukri_profile=naukri_profile,
        )
        return {"status": "success", **result}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Career workflow failed: {type(exc).__name__}: {exc}") from exc


@app.post("/v3/export-docx")
def export_docx(request: ExportRequest):
    return Response(
        build_docx(request.resume_text),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=executive-ats-resume.docx"},
    )
