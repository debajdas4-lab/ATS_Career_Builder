from __future__ import annotations

import html
import json
import os
import re

import httpx
import streamlit as st

st.set_page_config(page_title="ATS Career Guide", page_icon="🎯", layout="wide")


def setting(name: str, default: str) -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


def resume_preview(text: str) -> str:
    """Render ATS resume text with clear employer/project hierarchy."""
    headings = {
        "SUMMARY", "PROFILE", "PROFESSIONAL SUMMARY", "EXECUTIVE EXPERTISE",
        "CORE SKILLS", "SKILLS", "CORE COMPETENCIES",
        "PROFESSIONAL EXPERIENCE", "EXPERIENCE",
        "EDUCATION", "CERTIFICATIONS", "EDUCATION AND CERTIFICATIONS",
        "EDUCATION & CERTIFICATIONS", "PROJECTS",
    }
    parts = ["<div class='resume-paper'>"]
    bullets: list[str] = []

    def flush_bullets() -> None:
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in bullets) + "</ul>")
            bullets.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_bullets()
            continue

        normalized = line.upper().rstrip(":")
        if normalized in headings:
            flush_bullets()
            parts.append(f"<h3>{html.escape(line.title())}</h3>")
        elif normalized == "KEY PROGRAMS / PROJECTS":
            flush_bullets()
            parts.append("<div class='resume-project-label'>Key Programs / Projects</div>")
        elif line.upper().startswith("PROJECT:"):
            flush_bullets()
            project = line.split(":", 1)[1].strip()
            parts.append(f"<h5 class='resume-project'>{html.escape(project)}</h5>")
        elif " | " in line and not line.startswith(("- ", "* ", "• ")):
            flush_bullets()
            # Employer/role header lines emitted by the Career Guide.
            parts.append(f"<div class='resume-employer'>{html.escape(line)}</div>")
        elif line.startswith(("- ", "* ", "• ")):
            bullets.append(line[2:].strip())
        else:
            flush_bullets()
            parts.append(f"<p>{html.escape(line)}</p>")

    flush_bullets()
    parts.append("</div>")
    return "".join(parts)


def parse_possible_json(value):
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw:
        return value
    cleaned = re.sub(r"^```(?:json)?\\s*", "", raw, flags=re.I)
    cleaned = re.sub(r"\\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except (TypeError, ValueError):
        return value



def clean_resume_for_export(text: str) -> str:
    """Remove Markdown artifacts and normalize resume formatting before display/export."""
    if not text:
        return ""

    lines = []
    for raw in str(text).splitlines():
        line = raw.strip()

        # Remove standalone Markdown fences/rules.
        if line in {"```", "```markdown", "```text", "---", "***", "___"}:
            continue

        # Remove heading markers and horizontal rules.
        line = re.sub(r"^\s{0,6}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*_]{3,}\s*$", "", line)

        # Remove emphasis markers but retain the text.
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"__(.*?)__", r"\1", line)
        line = re.sub(r"(?<!\*)\*(?!\s)(.*?)(?<!\s)\*(?!\*)", r"\1", line)
        line = re.sub(r"(?<!_)_(?!\s)(.*?)(?<!\s)_(?!_)", r"\1", line)

        # Convert Markdown bullets to the renderer's plain bullet format.
        line = re.sub(r"^\s*[-*+]\s+", "• ", line)

        # Normalize repeated spaces.
        line = re.sub(r"[ \t]{2,}", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines).strip()


def extract_generated_numeric_claims(warnings) -> list[str]:
    """Extract numeric claims from Evidence Guard warnings for display."""
    claims = []
    for warning in warnings or []:
        match = re.search(r"quantified claims:\s*(.+)$", str(warning), flags=re.I)
        if match:
            claims.extend([x.strip() for x in re.split(r",\s*|\.\s+", match.group(1)) if x.strip()])
    return list(dict.fromkeys(claims))


def normalize_resume_output(value) -> str:
    parsed = parse_possible_json(value)
    if isinstance(parsed, dict):
        value = parsed.get("optimized_resume") or parsed.get("resume") or parsed.get("content") or ""
    return clean_resume_for_export(str(value or ""))


def render_structured_content(value, empty_message="No content available."):
    value = parse_possible_json(value)
    if value in (None, "", {}, []):
        st.info(empty_message)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            st.markdown(f"**{str(key).replace('_', ' ').title()}**")
            render_structured_content(item)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                render_structured_content(item)
            else:
                st.markdown(f"- {item}")
    else:
        st.write(value)



st.markdown("""
<style>
    :root {
        --cg-navy: #08142f;
        --cg-blue: #3155e7;
        --cg-indigo: #5b3ff5;
        --cg-cyan: #1fb8d9;
        --cg-ink: #18233b;
        --cg-muted: #667085;
        --cg-line: #e5eaf2;
        --cg-bg: #f7f9fc;
        --cg-card: #ffffff;
    }

    /* NEW: cleaner system sans-serif stack for a modern enterprise UI */
    html, body, [class*="css"], .stApp {
        font-family: "Segoe UI", Inter, system-ui, -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
    }

    .stApp {
        background: linear-gradient(180deg, #f8faff 0%, #f6f8fc 100%);
        color: var(--cg-ink);
    }

    /* MODIFIED: keep a small, controlled gap above the hero without clipping it */
    [data-testid="stMainBlockContainer"] {
        padding-top: 1.1rem !important;
    }
    [data-testid="stMainBlockContainer"] > div:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    [data-testid="stImage"] {
        margin-top: 0.35rem;
        margin-bottom: 0.75rem;
    }
    /* NEW: add subtle breathing room so hero text does not touch the image edge */
    [data-testid="stImage"] img {
        padding-top: 8px;
        box-sizing: border-box;
        border-radius: 12px;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #07132f 0%, #0d1b3f 55%, #101f4a 100%);
        border-right: 1px solid rgba(255,255,255,.08);
    }

    [data-testid="stSidebar"] * { color: #edf2ff; }
    [data-testid="stSidebar"] .stMarkdown p { color: #b9c5e4; }

    .cg-brand {
        padding: 4px 6px 22px 6px;
        border-bottom: 1px solid rgba(255,255,255,.10);
        margin-bottom: 18px;
    }
    .cg-brand-title {
        font-size: 1.22rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        line-height: 1.05;
    }
    .cg-brand-title span { color: #6d76ff; }
    .cg-brand-subtitle {
        font-size: .74rem;
        color: #91a0c7 !important;
        margin-top: 6px;
    }
    .cg-nav-label {
        color: #7786ad !important;
        font-size: .68rem;
        font-weight: 700;
        letter-spacing: .12em;
        text-transform: uppercase;
        margin: 16px 0 7px;
    }
    .cg-nav-item {
        padding: 9px 10px;
        border-radius: 10px;
        margin: 2px 0;
        font-size: .90rem;
        color: #d9e1f7 !important;
    }
    .cg-nav-item.active {
        background: linear-gradient(90deg, rgba(68,95,245,.95), rgba(93,74,245,.92));
        box-shadow: 0 8px 20px rgba(40,58,170,.28);
        color: #fff !important;
        font-weight: 700;
    }
    .cg-protip {
        margin-top: 24px;
        padding: 14px;
        border-radius: 14px;
        background: linear-gradient(135deg, #2f2a7b 0%, #4b2a91 100%);
        border: 1px solid rgba(255,255,255,.12);
        box-shadow: 0 14px 32px rgba(0,0,0,.20);
    }
    .cg-protip-title { font-weight: 700; font-size: .84rem; margin-bottom: 4px; }
    .cg-protip-copy { font-size: .72rem; color: #d9dcff !important; line-height: 1.45; }

    .cg-kicker {
        font-size: .88rem;
        font-weight: 800;
        letter-spacing: .11em;
        color: var(--cg-blue);
        text-transform: uppercase;
        margin-top: 4px;
        margin-bottom: 4px;
    }
    /* MODIFIED: reduce headline size and improve hierarchy */
    .cg-title {
        font-size: 1.42rem;
        line-height: 1.15;
        font-weight: 800;
        letter-spacing: -0.035em;
        color: var(--cg-ink);
        margin: 0 0 6px;
        max-width: 980px;
    }
    .cg-subtitle {
        color: var(--cg-muted);
        font-size: .98rem;
        line-height: 1.5;
        margin-bottom: 16px;
    }
    .cg-section-title {
        font-size: 1.15rem;
        font-weight: 780;
        letter-spacing: -.02em;
        color: var(--cg-ink);
        margin-top: 4px;
        margin-bottom: 6px;
    }
    .cg-helper {
        color: var(--cg-muted);
        font-size: .83rem;
        margin-bottom: 10px;
    }
    /* MODIFIED: replace the large warning box with a compact tooltip */
    .cg-tooltip-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: -2px 0 6px;
    }
    .cg-tooltip {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #eef3ff;
        color: #3155e7;
        border: 1px solid #cdd8ff;
        font-size: .72rem;
        font-weight: 800;
        cursor: help;
    }
    .cg-tooltip-text {
        visibility: hidden;
        opacity: 0;
        position: absolute;
        z-index: 20;
        left: 28px;
        top: 50%;
        transform: translateY(-50%);
        width: 340px;
        padding: 10px 12px;
        border-radius: 10px;
        background: #10204b;
        color: #ffffff;
        font-size: .74rem;
        font-weight: 500;
        line-height: 1.45;
        box-shadow: 0 10px 26px rgba(16,24,40,.18);
        transition: opacity .15s ease;
    }
    .cg-tooltip:hover .cg-tooltip-text {
        visibility: visible;
        opacity: 1;
    }
    .cg-image-spacer {
        height: 0.75rem;
    }

    .cg-or {
        display: flex;
        align-items: center;
        gap: 10px;
        color: #98a1b2;
        font-size: .74rem;
        font-weight: 700;
        letter-spacing: .1em;
        text-transform: uppercase;
        margin: 8px 0 4px;
    }
    .cg-or::before, .cg-or::after {
        content: '';
        height: 1px;
        background: var(--cg-line);
        flex: 1;
    }
    .cg-card {
        background: var(--cg-card);
        border: 1px solid var(--cg-line);
        border-radius: 16px;
        padding: 18px 20px;
        box-shadow: 0 10px 26px rgba(16,24,40,.055);
    }
    /* NEW: highlighted research section with inline help tooltip */
    .cg-research-header {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 12px;
        border-radius: 10px;
        background: linear-gradient(90deg, #eef3ff 0%, #f6f2ff 100%);
        border: 1px solid #d8ddff;
        color: #253b91;
        font-weight: 800;
        font-size: .92rem;
        margin-bottom: 10px;
    }
    .cg-research-help {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #3155e7;
        color: white;
        font-size: .68rem;
        font-weight: 800;
        cursor: help;
    }
    .cg-research-help span {
        visibility: hidden;
        opacity: 0;
        position: absolute;
        z-index: 20;
        left: 28px;
        top: 50%;
        transform: translateY(-50%);
        width: 300px;
        padding: 10px 12px;
        border-radius: 10px;
        background: #10204b;
        color: #ffffff;
        font-size: .73rem;
        font-weight: 500;
        line-height: 1.45;
        box-shadow: 0 10px 26px rgba(16,24,40,.18);
        transition: opacity .15s ease;
    }
    .cg-research-help:hover span {
        visibility: visible;
        opacity: 1;
    }

    .cg-small-label {
        color: #7a8497;
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .07em;
        text-transform: uppercase;
        margin-bottom: 5px;
    }
    /* MODIFIED: high-contrast, readable action buttons */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #3155e7 0%, #5b3ff5 100%) !important;
        color: #ffffff !important;
        border: 0 !important;
        border-radius: 10px !important;
        font-weight: 750 !important;
        min-height: 2.7rem;
        box-shadow: 0 8px 18px rgba(61,71,210,.24);
    }
    div.stButton > button[kind="primary"] p,
    div.stButton > button[kind="primary"] span {
        color: #ffffff !important;
    }
    div.stButton > button:disabled {
        color: #98a2b3 !important;
        background: #eef1f6 !important;
        box-shadow: none !important;
    }
    /* NEW: consistent contrast for download/action buttons */
    div.stDownloadButton > button {
        background: #eef3ff !important;
        color: #2442a8 !important;
        border: 1px solid #ccd7ff !important;
        border-radius: 9px !important;
        font-weight: 700 !important;
    }
    div.stDownloadButton > button p,
    div.stDownloadButton > button span {
        color: #2442a8 !important;
    }
    .resume-paper { background:#ffffff; border:1px solid #d9e3e8; border-radius:14px; padding:36px 44px; color:#263238; box-shadow:0 12px 32px rgba(15,57,76,.10); min-height:650px; }
    .resume-paper h3 { color:#3155e7; font-size:1.05rem; letter-spacing:.08em; text-transform:uppercase; border-bottom:2px solid #e8edff; padding-bottom:7px; margin:24px 0 10px; }
    .resume-paper p { line-height:1.55; margin:7px 0; }
    .resume-paper ul { margin-top:4px; padding-left:22px; }
    .resume-paper li { line-height:1.5; margin:5px 0; }
    .resume-employer {
        margin: 18px 0 5px;
        padding: 9px 12px;
        border-left: 4px solid #3155e7;
        background: #f5f7ff;
        color: #18233b;
        font-size: .98rem;
        font-weight: 800;
    }
    .resume-project-label {
        margin: 10px 0 5px;
        color: #667085;
        font-size: .76rem;
        font-weight: 800;
        letter-spacing: .08em;
        text-transform: uppercase;
    }
    .resume-project {
        margin: 10px 0 3px;
        color: #253b91;
        font-size: .93rem;
        font-weight: 800;
    }

    /* =========================================================
       MODIFIED: UNIFIED PROFESSIONAL ACTION BUTTONS
       ========================================================= */

    /* Active Streamlit action buttons */
    [data-testid="stButton"] button,
    div.stButton > button,
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-secondary"] {
        background: linear-gradient(90deg, #3155E7 0%, #5146E5 100%) !important;
        background-color: #3155E7 !important;
        border: 1px solid #3155E7 !important;
        border-radius: 9px !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        min-height: 44px !important;
        box-shadow: 0 6px 16px rgba(49, 85, 231, 0.22) !important;
        opacity: 1 !important;
    }

    [data-testid="stButton"] button *,
    div.stButton > button *,
    button[data-testid="stBaseButton-primary"] *,
    button[data-testid="stBaseButton-secondary"] * {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        opacity: 1 !important;
    }

    [data-testid="stButton"] button:hover,
    div.stButton > button:hover,
    button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="stBaseButton-secondary"]:hover {
        background: linear-gradient(90deg, #2546C7 0%, #4338CA 100%) !important;
        background-color: #2546C7 !important;
        border-color: #2546C7 !important;
        color: #FFFFFF !important;
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(49, 85, 231, 0.28) !important;
    }

    /* File uploader Browse files button */
    [data-testid="stFileUploader"] button,
    [data-testid="stFileUploader"] button[data-testid="stBaseButton-secondary"] {
        background: linear-gradient(90deg, #3155E7 0%, #5146E5 100%) !important;
        background-color: #3155E7 !important;
        border: 1px solid #3155E7 !important;
        border-radius: 9px !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        min-height: 40px !important;
        box-shadow: 0 5px 14px rgba(49, 85, 231, 0.20) !important;
        opacity: 1 !important;
    }

    [data-testid="stFileUploader"] button *,
    [data-testid="stFileUploader"] button p,
    [data-testid="stFileUploader"] button span {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        opacity: 1 !important;
    }

    [data-testid="stFileUploader"] button:hover {
        background: linear-gradient(90deg, #2546C7 0%, #4338CA 100%) !important;
        background-color: #2546C7 !important;
        border-color: #2546C7 !important;
        color: #FFFFFF !important;
    }

    /* Download buttons use the same visual language */
    [data-testid="stDownloadButton"] button,
    div.stDownloadButton > button {
        background: linear-gradient(90deg, #3155E7 0%, #5146E5 100%) !important;
        background-color: #3155E7 !important;
        border: 1px solid #3155E7 !important;
        border-radius: 9px !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }

    [data-testid="stDownloadButton"] button *,
    div.stDownloadButton > button * {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }


    /* MODIFIED: larger, clearer Job Description field labels */
    [data-testid="stTextInput"] label p,
    [data-testid="stTextArea"] label p,
    [data-testid="stFileUploader"] label p {
        font-size: 1.02rem !important;
        font-weight: 650 !important;
        color: var(--cg-ink) !important;
        letter-spacing: -0.01em !important;
    }


    /* MODIFIED: reduce excess horizontal whitespace around the main workspace */
    [data-testid="stMainBlockContainer"] {
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
    }

    /* MODIFIED: left-align the OR separator instead of centering the title */
    .cg-or {
        justify-content: flex-start !important;
        gap: 10px !important;
        margin: 8px 0 4px !important;
        max-width: 100% !important;
    }

    .cg-or::before {
        flex: 0 0 34px !important;
    }

    .cg-or::after {
        flex: 1 1 auto !important;
    }


    /* FINAL MODIFIED: minimize whitespace above the hero banner */
    [data-testid="stMainBlockContainer"] {
        padding-top: 0.15rem !important;
    }

    [data-testid="stMainBlockContainer"] > div:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }

    .cg-image-spacer {
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    [data-testid="stImage"] {
        margin-top: 0 !important;
    }

    /* FINAL MODIFIED: center the OR separator and its title */
    .cg-or {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 12px !important;
        width: 100% !important;
        margin: 8px 0 4px !important;
        text-align: center !important;
    }

    .cg-or::before,
    .cg-or::after {
        content: '' !important;
        height: 1px !important;
        background: var(--cg-line) !important;
        flex: 1 1 0 !important;
    }


    /* MODIFIED: mandatory field marker */
    .cg-required-label {
        display: inline-flex;
        align-items: flex-start;
        gap: 3px;
        margin: 0 0 5px 0;
        color: var(--cg-ink);
        font-size: 1.02rem;
        font-weight: 650;
        letter-spacing: -0.01em;
        line-height: 1.2;
    }

    .cg-required-star {
        color: #dc2626;
        font-size: .78rem;
        font-weight: 900;
        line-height: 1;
        position: relative;
        top: -2px;
    }

    /* Hide native labels where custom mandatory labels are used */
    .cg-hide-next-label + div [data-testid="stWidgetLabel"] {
        display: none !important;
    }


    /* FINAL: align hero banner and workspace content to the same horizontal grid */
    [data-testid="stMainBlockContainer"] {
        padding-left: 1.75rem !important;
        padding-right: 1.75rem !important;
        padding-top: 0.15rem !important;
        max-width: 100% !important;
    }

    [data-testid="stImage"] {
        width: 100% !important;
        margin-left: 0 !important;
        margin-right: 0 !important;
    }

    [data-testid="stImage"] > div,
    [data-testid="stImage"] img {
        width: 100% !important;
        max-width: 100% !important;
        margin-left: 0 !important;
        margin-right: 0 !important;
        display: block !important;
    }

    /* FINAL: centered workspace kicker with balanced spacing */
    .cg-kicker {
        text-align: center !important;
        width: 100% !important;
        font-size: .90rem !important;
        margin-top: 0.80rem !important;
        margin-bottom: 0.45rem !important;
    }

    /* FINAL: refined main headline */
    .cg-title {
        font-size: 1.38rem !important;
        line-height: 1.18 !important;
        margin-top: 0 !important;
        margin-bottom: 0.40rem !important;
    }

</style>
""", unsafe_allow_html=True)

API_URL = setting("RESUME_API_URL", "http://localhost:8000").rstrip("/")
# V3 API contract: /v3/career-guide and /v3/export-docx

with st.sidebar:
    st.markdown("""
    <div class='cg-brand'>
      <div class='cg-brand-title'>ATS <span>Career Guide</span></div>
      <div class='cg-brand-subtitle'>AI Career Intelligence & Application Copilot</div>
    </div>
    <div class='cg-nav-label'>Core tools</div>
    <div class='cg-nav-item active'>🎯 &nbsp; Analyze Job</div>
    <div class='cg-nav-item'>📄 &nbsp; Resume</div>
    <div class='cg-nav-item'>in &nbsp; LinkedIn</div>
    <div class='cg-nav-item'>⌁ &nbsp; Naukri</div>
    <div class='cg-nav-item'>◉ &nbsp; Interview Kit</div>
    <div class='cg-nav-item'>⌁ &nbsp; Career Roadmap</div>
    <div class='cg-nav-item'>◌ &nbsp; Research</div>
    <div class='cg-nav-label'>Workspace</div>
    <div class='cg-nav-item'>▱ &nbsp; My Projects</div>
    <div class='cg-nav-item'>▤ &nbsp; Saved Reports</div>
    <div class='cg-nav-item'>▥ &nbsp; Evidence Library</div>
    <div class='cg-protip'>
      <div class='cg-protip-title'>✦ Pro tip</div>
      <div class='cg-protip-copy'>Add your LinkedIn and Naukri Profile Data for deeper positioning, evidence matching and interview preparation.</div>
    </div>
    """, unsafe_allow_html=True)
    st.caption("MCP connectors use authorized provider access only.")

st.markdown("<div class='cg-image-spacer'></div>", unsafe_allow_html=True)
st.image("ats_career_guide_banner.png", use_container_width=True)
st.markdown("<div class='cg-kicker'>CAREER INTELLIGENCE WORKSPACE</div>", unsafe_allow_html=True)
# MODIFIED: smaller, more executive-style page headline
st.markdown("<div class='cg-title'>Elevate Your Career. Realize Your Potential.</div>", unsafe_allow_html=True)
st.markdown("<div class='cg-subtitle'>Start with the job link, then add the full job description for the most reliable analysis. The Career Guide connects ATS optimization, company research, interview preparation and career gaps in one workflow.</div>", unsafe_allow_html=True)

st.markdown("<div class='cg-required-label'>Upload Your Resume<span class='cg-required-star'>*</span></div>", unsafe_allow_html=True)
resume_file = st.file_uploader("Upload Your Resume", type=["pdf", "docx", "txt", "md"], label_visibility="collapsed")

st.markdown("<div class='cg-section-title'>Job Description Source</div>", unsafe_allow_html=True)
st.markdown("<div class='cg-helper'>Start with the job link. We will extract the role details and use them to tailor the career analysis.</div>", unsafe_allow_html=True)

# MODIFIED: compact inline warning tooltip beside the JD URL field
tooltip_html = """<div class='cg-tooltip-row'><span class='cg-tooltip'>i<span class='cg-tooltip-text'>Some job portals may not expose the full job description because of JavaScript rendering, login requirements or access restrictions. If extraction is incomplete, copy and paste the full JD below for the most reliable analysis.</span></span><span style='color:#667085;font-size:.76rem;'>URL extraction works best with public job pages.</span></div>"""
st.markdown(tooltip_html, unsafe_allow_html=True)
jd_url = st.text_input("Job description URL", placeholder="Paste the public job URL here — LinkedIn, Naukri, company careers page, etc.")
st.markdown("<div class='cg-or'>or paste the job description</div>", unsafe_allow_html=True)
# MODIFIED: shorter JD box so downstream controls remain visible without excessive scrolling
jd_text = st.text_area("Job description", height=150, placeholder="Paste the full job description here…")

# MODIFIED: make the research purpose visible even when the section is collapsed
st.markdown("<div class='cg-research-header'>Company &amp; Market Intelligence <span class='cg-research-help'>i<span>Use this section to add company, leadership and market context. The Career Guide uses it to connect the job to the employer's business priorities and generate more relevant positioning and interview preparation.</span></span></div>", unsafe_allow_html=True)
with st.expander("Add company, leadership and market inputs", expanded=False):
    c1, c2 = st.columns(2)

    # MODIFIED: Left column — company first, then LinkedIn, then Naukri
    with c1:
        company_url = st.text_input("Company Website / Profile URL")
        linkedin_profile = st.text_area(
            "LinkedIn Profile Data",
            height=108,
            placeholder="Paste your authorized/exported profile text here",
        )
        naukri_profile = st.text_area(
            "Naukri Profile Data",
            height=108,
            placeholder="Paste your authorized/exported profile text here",
        )

    # MODIFIED: Right column — leadership, market query, additional research URLs
    with c2:
        leadership_url = st.text_input("Leadership / Investor-Relations URL")
        market_query = st.text_input(
            "Market Research Query",
            placeholder="e.g. enterprise AI transformation strategy",
        )
        market_urls = st.text_area("Additional Research URLs", height=108)

run_disabled = resume_file is None or (not jd_text.strip() and not jd_url.strip())
if st.button("🚀 Analyze job & build career guide", type="primary", use_container_width=True):
    if run_disabled:
        st.warning("Please upload your resume and provide a job URL or paste the job description before running the Career Guide.")
        st.stop()
    status_box = st.status("Building Your Career Guide", expanded=True)
    status_box.write("✓ Inputs received")
    status_box.write("◌ Reading resume and target role")
    status_box.write("◌ Mapping employers, programs and project evidence")
    status_box.write("◌ Running ATS and gap analysis")
    if company_url or leadership_url or market_urls or market_query:
        status_box.write("◌ Researching company, leadership and market context")
    status_box.write("◌ Preparing optimized resume, interview kit and career roadmap")
    status_box.caption("Detailed career analysis can take a little longer when more evidence and research inputs are provided.")

    try:
        response = httpx.post(
            f"{API_URL}/v3/career-guide",
            files={"resume": (resume_file.name, resume_file.getvalue(), resume_file.type)},
            data={
                "job_description": jd_text,
                "job_url": jd_url,
                "company_url": company_url,
                "leadership_url": leadership_url,
                "market_urls": market_urls,
                "market_query": market_query,
                "linkedin_profile": linkedin_profile,
                "naukri_profile": naukri_profile,
            },
            timeout=180,
        )
        response.raise_for_status()
        st.session_state["career_result"] = response.json()
        status_box.update(label="Career Guide Ready", state="complete", expanded=False)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        try:
            payload = exc.response.json()
            detail = str(payload.get("detail", payload))
        except Exception:
            pass
        st.error(f"ATS Career Guide API returned HTTP {exc.response.status_code}: {detail}")
        if exc.response.status_code == 404:
            st.caption(
                "The deployed Render API did not expose the expected V3 Career Guide route. "
                "Expected: POST /v3/career-guide. Verify the Render deployment is serving ATS Career Builder V3."
            )
        st.caption("If the message mentions JD extraction, paste the full job description in the field above. If it mentions Groq, ChromaDB, or another dependency, check the FastAPI terminal for the full exception.")
    except httpx.RequestError as exc:
        st.error(f"Could not connect to the ATS Career Guide API: {exc}")
    except Exception as exc:
        st.error(f"Unexpected Streamlit error: {type(exc).__name__}: {exc}")


result = st.session_state.get("career_result")
if result:
    st.divider()
    fit = result.get("job_fit", {})
    ats = result.get("ats_analysis", {})
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Overall fit", f"{fit.get('overall', 0)} / 100")
    k2.metric("ATS fit", f"{ats.get('score', 0)} / 100")
    k3.metric("Leadership fit", f"{ats.get('leadership_score', 0)} / 100")
    k4.metric("Decision", fit.get("recommendation", "REVIEW"))

    tabs = st.tabs(["Fit & Gaps", "Resume", "LinkedIn", "Naukri", "Interview Kit", "Career Roadmap", "Research"])

    with tabs[0]:
        st.subheader("Strengths")
        st.write(", ".join(fit.get("strengths", [])) or "No strong matches detected")
        st.subheader("Gaps")
        st.write(", ".join(fit.get("risks", [])) or "No major gaps detected")
        st.subheader("Keyword gap")
        st.write("**Matched:** " + (", ".join(result.get("keyword_gap", {}).get("matched", [])) or "None"))
        st.write("**Missing:** " + (", ".join(result.get("keyword_gap", {}).get("missing", [])) or "None"))

    with tabs[1]:
        optimized_resume = clean_resume_for_export(normalize_resume_output(result.get("optimized_resume", "")))
        st.markdown(resume_preview(optimized_resume), unsafe_allow_html=True)
        st.download_button("Download TXT", optimized_resume, "ats-career-guide-resume.txt", "text/plain")
        try:
            docx_response = httpx.post(f"{API_URL}/v1/export-docx", json={"resume_text": optimized_resume}, timeout=30)
            docx_response.raise_for_status()
            st.download_button("Download DOCX", docx_response.content, "ats-career-guide-resume.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        except Exception:
            pass
        st.subheader("Cover letter")
        render_structured_content(result.get("cover_letter", ""), "No cover letter was generated.")

    with tabs[2]:
        render_structured_content(result.get("linkedin_optimization", {}), "No LinkedIn optimization was generated.")

    with tabs[3]:
        render_structured_content(result.get("naukri_optimization", {}), "No Naukri optimization was generated.")

    with tabs[4]:
        kit = parse_possible_json(result.get("interview_kit", {}))
        if not isinstance(kit, dict):
            kit = {}
        for section, title in [
            ("resume_questions", "Resume-specific questions"),
            ("company_questions", "Company questions"),
            ("leadership_questions", "Leadership questions"),
            ("technical_or_domain_questions", "Technical / domain questions"),
            ("gap_questions", "Gap questions"),
        ]:
            st.subheader(title)
            items = kit.get(section, [])
            if isinstance(items, list):
                for item in items:
                    st.write(f"- {item}")
            else:
                st.write(items)

    with tabs[5]:
        render_structured_content(result.get("career_roadmap", {}), "No career roadmap was generated.")

    with tabs[6]:
        research = result.get("research", {})
        st.subheader("Company / market signals")
        st.write(", ".join(research.get("strategy", [])) or "Add a company URL to enable public-page research.")
        if research.get("sources"):
            st.subheader("Sources")
            for source in research["sources"]:
                st.write(source)

    for warning in result.get("warnings", []):
        st.warning(warning)
