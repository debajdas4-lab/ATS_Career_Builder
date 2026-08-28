"""ATS Career Builder  Enterprise Edition (Streamlit UI).

Premium navy/violet theme, hero banner, and fully-working tabs wired to the
FastAPI backend. All content is dynamic  nothing about any candidate is
hardcoded. The UI degrades gracefully if a tab artefact is missing.
"""
from __future__ import annotations

import html
import os

import httpx
import streamlit as st

from core.ui_auth import auth_headers, ensure_signed_in, signed_in_user

st.set_page_config(page_title="ATS Career Guide", layout="wide")


def setting(name: str, default: str) -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


API_URL = setting("RESUME_API_URL", "http://localhost:8000").rstrip("/")
UI_CLIENT_SECRET = setting("AZURE_CLIENT_SECRET", "")

# Gate the app behind Entra ID SSO when the API reports auth is enabled.
# No-op (open access) for local development.
ensure_signed_in(API_URL, UI_CLIENT_SECRET)

# --------------------------------------------------------------------------- #
# Navigation state                                                             #
# --------------------------------------------------------------------------- #
NAV_ITEMS = [
    ("analyze", "", "Analyze Job"),
    ("resume", "", "Resume"),
    ("linkedin", "in", "LinkedIn"),
    ("naukri", "", "Naukri"),
    ("interview", "", "Interview Kit"),
    ("roadmap", "", "Career Roadmap"),
    ("research", "", "Research"),
]
if "active_nav" not in st.session_state:
    st.session_state["active_nav"] = "analyze"

# --------------------------------------------------------------------------- #
# Theme                                                                        #
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      :root { --navy:#1F2A44; --violet:#6C5CE7; --violet2:#8B7BF0; --ink:#0F1626; }
      .stApp { background: linear-gradient(180deg,#0F1626 0%, #141B2E 100%); }
      section[data-testid="stSidebar"] { background:#101830; border-right:1px solid #22304F; }
      section[data-testid="stSidebar"] * { color:#DCE6FA; }

      /* Sidebar brand */
      .brand { font-size:1.35rem; font-weight:800; margin:.2rem 0 .1rem; }
      .brand .w { color:#FFFFFF; } .brand .v { color:#8B7BF0; }
      .brand-sub { color:#8FA0C4; font-size:.82rem; line-height:1.3; margin-bottom:.6rem; }
      .nav-group { color:#7C8AA8; font-size:.7rem; font-weight:800; letter-spacing:.14em;
                   margin:1rem 0 .35rem; text-transform:uppercase; }

      /* Sidebar nav buttons (Streamlit buttons restyled) */
      section[data-testid="stSidebar"] .stButton > button {
        width:100%; text-align:left; background:transparent; color:#C7D3EC;
        border:1px solid transparent; border-radius:10px; padding:.5rem .75rem;
        font-weight:600; font-size:.95rem; transition:all .15s ease;
      }
      section[data-testid="stSidebar"] .stButton > button:hover {
        background:#182241; color:#FFFFFF; border-color:#22304F;
      }
      /* Active nav item */
      section[data-testid="stSidebar"] .stButton > button:focus:not(:active),
      section[data-testid="stSidebar"] .nav-active > button {
        background:linear-gradient(90deg,var(--violet),var(--violet2)) !important;
        color:#FFFFFF !important; border-color:transparent !important;
        box-shadow:0 6px 16px rgba(108,92,231,.35);
      }

      /* Hero / body text */
      .hero-tag { color:#8B7BF0; letter-spacing:.18em; font-size:.72rem; font-weight:800; }
      .hero-title { color:#EAF0FF; font-size:1.6rem; font-weight:800; margin:.1rem 0 .2rem; }
      .hero-sub { color:#AEBED9; font-size:.94rem; margin-bottom:.4rem; }
      .field-label { color:#DDE6F7; font-weight:700; font-size:.85rem; margin:.5rem 0 .2rem; }

      /* Tabs */
      .stTabs [data-baseweb="tab-list"] { gap:.35rem; }
      .stTabs [data-baseweb="tab"] {
        background:#1B2540; color:#AEBEDD; border-radius:10px 10px 0 0;
        padding:.55rem 1rem; font-weight:600; border:1px solid #263250;
      }
      .stTabs [aria-selected="true"] {
        background:linear-gradient(90deg,var(--violet),var(--violet2)); color:#fff; border-color:transparent;
      }
      .stTabs [data-baseweb="tab-panel"] {
        background:#161F38; border:1px solid #263250; border-top:none;
        border-radius:0 0 12px 12px; padding:1.1rem 1.2rem;
      }
      div[data-testid="stMetric"] {
        background:#1B2540; border:1px solid #2B3A5E; border-radius:12px; padding:.7rem .9rem;
      }
      .resume-card {
        background:#0E1526; border:1px solid #2B3A5E; border-radius:12px;
        padding:1rem 1.2rem; color:#E6EDFB; font-size:.9rem; line-height:1.5;
      }
      .resume-h { color:#8B7BF0; font-weight:800; letter-spacing:.06em; margin:.8rem 0 .3rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Rendering helpers                                                            #
# --------------------------------------------------------------------------- #
def resume_preview(text: str) -> str:
    heads = {
        "PROFESSIONAL SUMMARY", "CORE COMPETENCIES", "SELECTED CAREER HIGHLIGHTS",
        "PROFESSIONAL EXPERIENCE", "EARLIER PROFESSIONAL EXPERIENCE", "TECHNICAL SKILLS",
        "EDUCATION & CERTIFICATIONS", "EDUCATION AND CERTIFICATIONS", "EDUCATION",
        "CORE LEADERSHIP & TECHNICAL EXPERTISE",
    }
    out = ['<div class="resume-card">']
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            out.append("<br>")
            continue
        if line.upper().rstrip(":") in heads:
            out.append(f'<div class="resume-h">{html.escape(line.upper())}</div>')
        elif line[:2] in ("- ", "* ", " "):
            out.append(f" {html.escape(line[2:])}<br>")
        else:
            out.append(f"{html.escape(line)}<br>")
    out.append("</div>")
    return "".join(out)


def render_structured(value, empty="No content generated for this section."):
    if value in (None, "", {}, []):
        st.info(empty)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            st.markdown(f"**{str(key).replace('_', ' ').title()}**")
            render_structured(item, empty)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                render_structured(item, empty)
            else:
                st.markdown(f"- {item}")
    else:
        st.write(value)


# --------------------------------------------------------------------------- #
# Sidebar (grouped nav  matches original design)                              #
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown('<div class="brand"><span class="w">ATS</span> '
                '<span class="v">Career Guide</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-sub">AI Career Intelligence &amp; Application Copilot</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="nav-group">Core Tools</div>', unsafe_allow_html=True)
    for key, icon, label in NAV_ITEMS:
        active = st.session_state["active_nav"] == key
        wrap_open = '<div class="nav-active">' if active else ""
        wrap_close = "</div>" if active else ""
        if wrap_open:
            st.markdown(wrap_open, unsafe_allow_html=True)
        if st.button(f"{icon}  {label}", key=f"nav_{key}", width='stretch'):
            st.session_state["active_nav"] = key
        if wrap_close:
            st.markdown(wrap_close, unsafe_allow_html=True)

    st.markdown('<div class="nav-group">Workspace</div>', unsafe_allow_html=True)
    st.button("My Projects", key="nav_projects", width='stretch')
    st.button("Saved Reports", key="nav_reports", width='stretch')

    st.divider()
    _user = signed_in_user()
    if _user:
        st.caption(f" Signed in: {_user.get('name')}")
    st.caption(" Pro tip: add your LinkedIn & Naukri profile text and a company "
               "URL for deeper positioning and interview prep.")
    st.caption(f"API: {API_URL}")


# --------------------------------------------------------------------------- #
# Hero + inputs                                                                 #
# --------------------------------------------------------------------------- #
banner = os.path.join(os.path.dirname(__file__), "assets", "ats_career_guide_banner.png")
if os.path.exists(banner):
    st.image(banner, width='stretch')

st.markdown('<div class="hero-tag">CAREER INTELLIGENCE WORKSPACE</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-title">Elevate Your Career. Realize Your Potential.</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Upload your resume and a job description to get a dynamic ATS score, '
            'a premium tailored resume, and end-to-end application guidance.</div>', unsafe_allow_html=True)

st.markdown('<div class="field-label">Upload Your Resume *</div>', unsafe_allow_html=True)
resume_file = st.file_uploader("Resume", type=["pdf", "docx", "txt", "md"], label_visibility="collapsed")

st.markdown('<div class="field-label">Job Description URL</div>', unsafe_allow_html=True)
jd_url = st.text_input("JD URL", placeholder="Paste a public job URL (LinkedIn, Naukri, careers page)...",
                       label_visibility="collapsed")
st.markdown('<div class="field-label">OR, PASTE JOB DESC. BELOW</div>', unsafe_allow_html=True)
jd_text = st.text_area("JD text", height=150, placeholder="Paste the full job description here...",
                       label_visibility="collapsed")

with st.expander(" Add company, leadership & market inputs (optional)"):
    c1, c2 = st.columns(2)
    with c1:
        company_url = st.text_input("Company Website / Profile URL")
        linkedin_profile = st.text_area("LinkedIn Profile Data", height=100)
        naukri_profile = st.text_area("Naukri Profile Data", height=100)
    with c2:
        leadership_url = st.text_input("Leadership / Investor-Relations URL")
        market_query = st.text_input("Market Research Query")
        market_urls = st.text_area("Additional Research URLs", height=100)

run_disabled = resume_file is None or (not jd_text.strip() and not jd_url.strip())

if st.button("Analyze job & build career guide", type="primary", width='stretch'):
    if run_disabled:
        st.warning("Please upload your resume and provide a job URL or paste the job description.")
        st.stop()
    with st.status("Building your career guide...", expanded=True) as status:
        status.write(" Inputs received")
        status.write(" Extracting dynamic keywords & candidate profile")
        status.write(" Scoring resume against the job description")
        status.write(" Generating premium resume & application artefacts")
        try:
            resp = httpx.post(
                f"{API_URL}/v3/career-guide",
                files={"resume": (resume_file.name, resume_file.getvalue(), resume_file.type or "text/plain")},
                data={
                    "job_description": jd_text, "job_url": jd_url,
                    "company_url": company_url, "leadership_url": leadership_url,
                    "market_urls": market_urls, "market_query": market_query,
                    "linkedin_profile": linkedin_profile, "naukri_profile": naukri_profile,
                },
                headers=auth_headers(),
                timeout=httpx.Timeout(240.0, read=None),
            )
            resp.raise_for_status()
            st.session_state["result"] = resp.json()
            status.update(label="Career Guide ready", state="complete", expanded=False)
        except httpx.HTTPStatusError as exc:
            status.update(label="Failed", state="error")
            st.error(f"API returned HTTP {exc.response.status_code}: {exc.response.text[:400]}")
        except httpx.RequestError as exc:
            status.update(label="Failed", state="error")
            st.error(f"Could not connect to the API at {API_URL}: {exc}")


# --------------------------------------------------------------------------- #
# Results                                                                       #
# --------------------------------------------------------------------------- #
result = st.session_state.get("result")
if result:
    st.divider()
    before, after = result.get("score_before", 0), result.get("score_after", 0)
    fit = result.get("job_fit", {})

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Overall fit", f"{fit.get('overall', 0)} / 100")
    k2.metric("ATS  Current", f"{before} / 100")
    k3.metric("ATS  Upgraded", f"{after} / 100", delta=f"{after - before:+d} pts")
    k4.metric("Decision", fit.get("recommendation", "REVIEW"))

    comp = result.get("ats_analysis", {}).get("components", {})
    st.caption(
        f"Score = 65% keyword coverage ({comp.get('keyword_coverage', 0):.0%}) + "f"15% semantic match ({comp.get('semantic_similarity', 0):.0%}) + "f"20% section completeness ({comp.get('section_completeness', 0):.0%}). "f"Resume generation mode: {result.get('generation_mode', 'n/a')}."
    )

    tabs = st.tabs(["Fit & Gaps", "Resume", "LinkedIn", "Naukri", "Interview Kit", "Career Roadmap", "Research"])

    with tabs[0]:
        st.subheader("ATS score dashboard")
        d1, d2, d3 = st.columns(3)
        d1.metric("Keyword coverage", f"{comp.get('keyword_coverage', 0):.0%}")
        d2.metric("Semantic match", f"{comp.get('semantic_similarity', 0):.0%}")
        d3.metric("Section completeness", f"{comp.get('section_completeness', 0):.0%}")
        st.subheader("Strengths (matched keywords)")
        st.write(", ".join(fit.get("strengths", [])) or "No strong matches detected.")
        if fit.get("partial"):
            st.subheader("Partial matches")
            st.write(", ".join(fit.get("partial", [])))
        st.subheader("Gaps (missing keywords)")
        st.write(", ".join(fit.get("gaps", [])) or "No major gaps detected.")
        if fit.get("missing_sections"):
            st.warning("Missing resume sections: " + ", ".join(fit["missing_sections"]))

    with tabs[1]:
        for w in result.get("warnings", []):
            st.warning(w)
        resume_out = result.get("optimized_resume", "")
        st.markdown(resume_preview(resume_out), unsafe_allow_html=True)
        c_txt, c_docx = st.columns(2)
        c_txt.download_button(" Download TXT", resume_out, "ats-career-guide-resume.txt", "text/plain",
                              width='stretch')
        try:
            docx = httpx.post(f"{API_URL}/v3/export-docx", json={"resume_text": resume_out},
                              headers=auth_headers(), timeout=60)
            docx.raise_for_status()
            c_docx.download_button(" Download DOCX", docx.content, "ats-career-guide-resume.docx",
                                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   width='stretch')
        except Exception as exc:
            c_docx.warning(f"DOCX export unavailable: {exc}")

    with tabs[2]:
        render_structured(result.get("linkedin_optimization", {}))

    with tabs[3]:
        render_structured(result.get("naukri_optimization", {}))

    with tabs[4]:
        kit = result.get("interview_kit", {})
        labels = {
            "resume_questions": "Resume-specific questions",
            "company_questions": "Company questions",
            "leadership_questions": "Leadership questions",
            "technical_or_domain_questions": "Technical / domain questions",
            "gap_questions": "Gap questions",
            "star_story_blueprints": "STAR story blueprints",
        }
        if isinstance(kit, dict) and kit:
            for key, title in labels.items():
                if kit.get(key):
                    st.subheader(title)
                    render_structured(kit.get(key))
        else:
            st.info("No interview kit generated.")

    with tabs[5]:
        render_structured(result.get("career_roadmap", {}))

    with tabs[6]:
        research = result.get("research") or {}
        if isinstance(research, dict) and (research.get("company_profile") or research.get("sources")):
            cp = research.get("company_profile", {})
            if cp.get("overview"):
                st.write(cp["overview"])
            if research.get("strategy"):
                st.subheader("Business & strategic signals")
                for s in research["strategy"]:
                    st.markdown(f"- {s}")
            if research.get("sources"):
                st.subheader("Sources")
                for src in research["sources"]:
                    st.markdown(f"- [{src.get('label', 'Source')}]({src.get('url', '#')})")
        else:
            st.info("Add a company URL or market inputs above to enable public-page research.")

