from __future__ import annotations

import html
import os

import httpx
import streamlit as st

st.set_page_config(page_title="Resume Optimizer", page_icon="🎯", layout="wide")


def setting(name: str, default: str) -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


def resume_preview(text: str) -> str:
    headings = {"SUMMARY", "PROFESSIONAL SUMMARY", "CORE SKILLS", "SKILLS", "PROFESSIONAL EXPERIENCE", "EXPERIENCE", "EDUCATION", "CERTIFICATIONS", "PROJECTS"}
    parts = ["<div class='resume-paper'>"]
    bullets: list[str] = []

    def flush_bullets() -> None:
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in bullets) + "</ul>")
            bullets.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        safe = html.escape(line)
        if safe.upper().rstrip(":") in headings:
            flush_bullets()
            parts.append(f"<h3>{safe.title()}</h3>")
        elif line.startswith(("- ", "* ", "• ")):
            bullets.append(html.escape(line[2:].strip()))
        else:
            flush_bullets()
            parts.append(f"<p>{safe}</p>")
    flush_bullets()
    parts.append("</div>")
    return "".join(parts)


st.markdown("""
<style>
.resume-paper { background:#ffffff; border:1px solid #d9e3e8; border-radius:14px; padding:36px 44px; color:#263238; box-shadow:0 12px 32px rgba(15,57,76,.10); min-height:650px; }
.resume-paper h3 { color:#1f6f8b; font-size:1.05rem; letter-spacing:.08em; text-transform:uppercase; border-bottom:2px solid #d7edf2; padding-bottom:7px; margin:24px 0 10px; }
.resume-paper p { line-height:1.55; margin:7px 0; }
.resume-paper ul { margin-top:4px; padding-left:22px; }
.resume-paper li { line-height:1.5; margin:5px 0; }
</style>
""", unsafe_allow_html=True)

API_URL = setting("RESUME_API_URL", "http://localhost:8000").rstrip("/")

st.title("🎯 Resume Optimizer")
st.caption("Make your resume clearer, ATS-friendly and better aligned to the role—without inventing experience.")

with st.sidebar:
    st.subheader("How it works")
    st.markdown("1. Upload your resume\n2. Paste a job description or URL\n3. Analyze recruiter keywords\n4. Generate an ATS-readable draft")
    st.info("Always review AI output and verify every claim before applying.")

resume_file = st.file_uploader("Upload your resume", type=["pdf", "docx", "txt", "md"])
jd_text = st.text_area("Paste the job description", height=220, placeholder="Paste the full role description here...")
jd_url = st.text_input("Or provide a public job-description URL")

if st.button("✨ Analyze and rebuild resume", type="primary", disabled=resume_file is None or (not jd_text.strip() and not jd_url.strip())):
    with st.spinner("Extracting keywords, scoring alignment and preparing your ATS draft..."):
        try:
            response = httpx.post(
                f"{API_URL}/v1/optimize",
                files={"resume": (resume_file.name, resume_file.getvalue(), resume_file.type)},
                data={"job_description": jd_text, "job_url": jd_url},
                timeout=120,
            )
            response.raise_for_status()
            st.session_state["result"] = response.json()
        except Exception as exc:
            st.error(f"Could not reach the Resume Optimizer API: {exc}")

result = st.session_state.get("result")
if result:
    analysis = result.get("ats_analysis", {})
    st.divider()
    left, right = st.columns([1, 2])
    with left:
        st.metric("ATS alignment", f"{analysis.get('score', 0)} / 100")
        st.write("**Matched keywords**")
        st.write(", ".join(analysis.get("matched_keywords", [])) or "None detected")
        st.write("**Priority gaps**")
        st.write(", ".join(analysis.get("missing_keywords", [])) or "No major gaps detected")
    with right:
        st.subheader("ATS-optimized resume draft")
        optimized_resume = result.get("optimized_resume", "")
        st.markdown(resume_preview(optimized_resume), unsafe_allow_html=True)
        st.download_button("Download draft as TXT", optimized_resume, "ats-optimized-resume.txt", "text/plain")
        try:
            docx_response = httpx.post(
                f"{API_URL}/v1/export-docx",
                json={"resume_text": optimized_resume},
                timeout=30,
            )
            docx_response.raise_for_status()
            st.download_button(
                "📄 Download premium DOCX",
                docx_response.content,
                "ats-optimized-resume.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except Exception:
            st.caption("DOCX export is unavailable until the API is running.")
        st.caption(result.get("cover_note", ""))
    for warning in result.get("warnings", []):
        st.warning(warning)

