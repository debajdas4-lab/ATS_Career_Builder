from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.config import MAX_RESUME_BYTES
from core.docx_export import build_docx
from core.graph import optimize_resume
from core.parsing import extract_resume_text, fetch_job_description

app = FastAPI(title="Resume Optimizer API", version="1.0.0")


class OptimizeTextRequest(BaseModel):
    resume_text: str = Field(min_length=80)
    job_description: str = Field(min_length=80)


class ExportDocxRequest(BaseModel):
    resume_text: str = Field(min_length=80)


def _result(resume_text: str, job_description: str) -> dict:
    state = optimize_resume(resume_text, job_description)
    return {
        "status": "success",
        "ats_analysis": state.get("analysis", {}),
        "keywords": state.get("keywords", []),
        "optimized_resume": state.get("optimized_resume", ""),
        "cover_note": state.get("cover_note", ""),
        "warnings": state.get("warnings", []),
    }


@app.get("/")
def health() -> dict:
    return {"status": "Running", "application": "Resume Optimizer", "version": "1.0.0"}


@app.post("/v1/optimize")
async def optimize(
    resume: UploadFile = File(...),
    job_description: str = Form(""),
    job_url: str = Form(""),
) -> dict:
    content = await resume.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume file exceeds the configured size limit.")
    try:
        resume_text = extract_resume_text(resume.filename or "resume.txt", content)
        jd = job_description.strip() or await fetch_job_description(job_url.strip())
        if len(jd) < 80:
            raise ValueError("Provide a job description as text or a URL.")
        return _result(resume_text, jd)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/v1/optimize-text")
def optimize_text(request: OptimizeTextRequest) -> dict:
    return _result(request.resume_text, request.job_description)


@app.post("/v1/export-docx")
def export_docx(request: ExportDocxRequest) -> Response:
    return Response(
        content=build_docx(request.resume_text),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=ats-optimized-resume.docx"},
    )
