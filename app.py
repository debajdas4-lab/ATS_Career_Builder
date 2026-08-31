"""ATS Career Builder — Enterprise Edition (Streamlit UI).

Premium navy/violet theme, responsive full-width hero banner, and
fully-working tabs wired to the FastAPI backend.

All content is dynamic — nothing about any candidate is hardcoded.
The UI degrades gracefully if a tab artefact is missing.
"""

from __future__ import annotations

import base64
import html
import os

import httpx
import streamlit as st

from core.ui_auth import auth_headers, ensure_signed_in, signed_in_user


# --------------------------------------------------------------------------- #
# Page configuration                                                          #
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="ATS Career Guide",
    page_icon="🎯",
    layout="wide",
)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #

def setting(name: str, default: str) -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


API_URL = setting(
    "RESUME_API_URL",
    "http://localhost:8000",
).rstrip("/")

UI_CLIENT_SECRET = setting(
    "AZURE_CLIENT_SECRET",
    "",
)


# Gate the app behind Entra ID SSO when the API reports auth is enabled.
# No-op for local development.
ensure_signed_in(API_URL, UI_CLIENT_SECRET)


# --------------------------------------------------------------------------- #
# Navigation state                                                            #
# --------------------------------------------------------------------------- #

NAV_ITEMS = [
    ("analyze", "🎯", "Analyze Job"),
    ("resume", "📄", "Resume"),
    ("linkedin", "in", "LinkedIn"),
    ("naukri", "⌁", "Naukri"),
    ("interview", "◉", "Interview Kit"),
    ("roadmap", "↗", "Career Roadmap"),
    ("research", "◌", "Research"),
]

if "active_nav" not in st.session_state:
    st.session_state["active_nav"] = "analyze"


# --------------------------------------------------------------------------- #
# Theme                                                                       #
# --------------------------------------------------------------------------- #

st.markdown(
    """
    <style>

    /* ===================================================================== */
    /* GLOBAL THEME                                                          */
    /* ===================================================================== */

    :root {
        --navy: #0F1626;
        --navy2: #141B2E;
        --sidebar: #101830;

        --card: #1B2540;
        --card2: #202B49;

        --border: #334466;
        --border-light: #2B3A5E;

        --violet: #6C5CE7;
        --violet2: #8B7BF0;

        --white: #FFFFFF;
        --text: #EAF0FF;
        --text-soft: #DCE6FA;
        --muted: #AEBED9;
        --muted2: #8FA0C4;

        --success: #67E8A5;
        --warning: #FBBF24;
        --danger: #FF6B6B;
    }


    /* ===================================================================== */
    /* MAIN APPLICATION                                                      */
    /* ===================================================================== */

    .stApp {
        background:
            linear-gradient(
                180deg,
                var(--navy) 0%,
                var(--navy2) 100%
            ) !important;

        color: var(--text) !important;
    }


    .main .block-container {
        max-width: 1500px;
        padding-top: 0.25rem !important;
        padding-bottom: 3rem;
    }

    /* Minimize Streamlit's top chrome gap without shifting the banner
       into the browser/header area. */
    [data-testid="stAppViewContainer"] > .main {
        padding-top: 0rem !important;
    }

    [data-testid="stHeader"] {
        height: 0rem !important;
        min-height: 0rem !important;
    }

    [data-testid="stToolbar"] {
        top: 0rem !important;
    }


    /* Make standard Streamlit text readable */
    .stApp p,
    .stApp span,
    .stApp label {
        color: inherit;
    }


    /* ===================================================================== */
    /* SIDEBAR                                                               */
    /* ===================================================================== */

    section[data-testid="stSidebar"] {
        background: var(--sidebar) !important;
        border-right: 1px solid #22304F;
    }


    section[data-testid="stSidebar"] * {
        color: var(--text-soft);
    }


    .brand {
        font-size: 1.35rem;
        font-weight: 800;
        margin: .2rem 0 .1rem;
    }


    .brand .w {
        color: #FFFFFF;
    }


    .brand .v {
        color: var(--violet2);
    }


    .brand-sub {
        color: var(--muted2) !important;
        font-size: .82rem;
        line-height: 1.3;
        margin-bottom: .6rem;
    }


    .nav-group {
        color: #7C8AA8 !important;
        font-size: .7rem;
        font-weight: 800;
        letter-spacing: .14em;
        margin: 1rem 0 .35rem;
        text-transform: uppercase;
    }


    section[data-testid="stSidebar"] .stButton > button {
        width: 100%;
        text-align: left;

        background: transparent;
        color: #C7D3EC !important;

        border: 1px solid transparent;
        border-radius: 10px;

        padding: .5rem .75rem;

        font-weight: 600;
        font-size: .95rem;

        transition: all .15s ease;
    }


    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #182241 !important;
        color: #FFFFFF !important;
        border-color: #22304F;
    }


    .nav-active > button {
        background:
            linear-gradient(
                90deg,
                var(--violet),
                var(--violet2)
            ) !important;

        color: #FFFFFF !important;
        border-color: transparent !important;

        box-shadow:
            0 6px 16px rgba(108, 92, 231, .35);
    }


    /* ===================================================================== */
    /* FULL-WIDTH HERO BANNER                                                */
    /* ===================================================================== */

    .ats-banner {
        width: 100%;
        max-width: 100%;
        overflow: hidden;

        border-radius: 14px;

        margin: 0 0 1.2rem 0;
        padding: 0;

        line-height: 0;

        background: #10182B;

        box-shadow:
            0 8px 30px rgba(0, 0, 0, .20);
    }


    .ats-banner img {
        width: 100%;
        max-width: 100%;

        height: auto;

        display: block;

        object-fit: contain;
        object-position: center;

        border: 0;
    }


    /* ===================================================================== */
    /* HERO TEXT                                                             */
    /* ===================================================================== */

    .hero-tag {
        color: #9B8EF7 !important;

        letter-spacing: .16em;

        font-size: .68rem;
        font-weight: 800;

        margin-top: .5rem;
        margin-bottom: .1rem;
    }


    .hero-title {
        color: #FFFFFF !important;

        font-size: 1.45rem;
        font-weight: 800;

        margin: .15rem 0 .15rem;
    }


    .hero-sub {
        color: #AEBED9 !important;

        font-size: .88rem;

        margin-bottom: .7rem;
    }


    .field-label {
        color: #E6EDFB !important;

        font-weight: 700;
        font-size: .85rem;

        margin: .5rem 0 .2rem;
    }


    /* ===================================================================== */
    /* INPUTS                                                                */
    /* ===================================================================== */

    .stTextInput input,
    .stTextArea textarea {
        background: #111A2E !important;

        color: #FFFFFF !important;

        border: 1px solid #34466B !important;

        border-radius: 8px !important;
    }


    .stTextInput input::placeholder,
    .stTextArea textarea::placeholder {
        color: #8191B3 !important;
    }


    .stTextInput input:focus,
    .stTextArea textarea:focus {
        border-color: var(--violet) !important;

        box-shadow:
            0 0 0 1px var(--violet) !important;
    }


    /* ===================================================================== */
    /* PRIMARY BUTTON                                                        */
    /* ===================================================================== */

    .stButton > button[kind="primary"] {
        background:
            linear-gradient(
                90deg,
                var(--violet),
                var(--violet2)
            ) !important;

        color: #FFFFFF !important;

        border: none !important;

        font-weight: 700;

        min-height: 48px;

        border-radius: 10px;
    }


    .stButton > button[kind="primary"]:hover {
        box-shadow:
            0 6px 20px rgba(108, 92, 231, .40);
    }


    /* ===================================================================== */
    /* DOWNLOAD BUTTONS                                                      */
    /* ===================================================================== */

    /* Streamlit st.download_button uses a separate DOM/test id from st.button.
       Give TXT/DOCX actions the same visual language as the primary actions. */
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stDownloadButton"] button[data-testid="stBaseButton-secondary"],
    div[data-testid="stDownloadButton"] button[kind="secondary"] {
        appearance: none !important;
        -webkit-appearance: none !important;
        width: 100% !important;
        background: linear-gradient(90deg, #6C5CE7 0%, #8B7BF0 100%) !important;
        background-color: #6C5CE7 !important;
        color: #FFFFFF !important;
        border: 1px solid #6C5CE7 !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        min-height: 46px !important;
        padding: 0.55rem 1rem !important;
        opacity: 1 !important;
        box-shadow: 0 4px 12px rgba(108, 92, 231, .22) !important;
        text-shadow: none !important;
    }

    div[data-testid="stDownloadButton"] button:hover,
    div[data-testid="stDownloadButton"] button[data-testid="stBaseButton-secondary"]:hover,
    div[data-testid="stDownloadButton"] button[kind="secondary"]:hover {
        background: linear-gradient(90deg, #5B4BE0 0%, #796BE9 100%) !important;
        background-color: #5B4BE0 !important;
        color: #FFFFFF !important;
        border-color: #5B4BE0 !important;
    }

    div[data-testid="stDownloadButton"] button *,
    div[data-testid="stDownloadButton"] button span,
    div[data-testid="stDownloadButton"] button p,
    div[data-testid="stDownloadButton"] button svg {
        color: #FFFFFF !important;
        fill: currentColor !important;
        stroke: currentColor !important;
        opacity: 1 !important;
    }

    /* Disabled-state styling only applies when the app actually disables a
       download button; it should remain readable rather than white-on-white. */
    div[data-testid="stDownloadButton"] button:disabled {
        background: #2A3552 !important;
        background-color: #2A3552 !important;
        color: #9FB0CC !important;
        border-color: #3A496B !important;
        opacity: 1 !important;
        box-shadow: none !important;
    }

    div[data-testid="stDownloadButton"] button:disabled * {
        color: #9FB0CC !important;
        fill: currentColor !important;
        stroke: currentColor !important;
    }

    /* ===================================================================== */
    /* TABS                                                                  */
    /* ===================================================================== */

    .stTabs [data-baseweb="tab-list"] {
        gap: .35rem;

        background: transparent !important;
    }


    .stTabs [data-baseweb="tab"] {
        background: #1B2540 !important;

        color: #B8C6E0 !important;

        border-radius: 10px 10px 0 0;

        padding: .65rem 1rem;

        font-weight: 600;

        border: 1px solid #2F3E5E !important;
    }


    .stTabs [data-baseweb="tab"] * {
        color: #B8C6E0 !important;
    }


    .stTabs [aria-selected="true"] {
        background:
            linear-gradient(
                90deg,
                var(--violet),
                var(--violet2)
            ) !important;

        color: #FFFFFF !important;

        border-color: transparent !important;
    }


    .stTabs [aria-selected="true"] * {
        color: #FFFFFF !important;
    }


    .stTabs [data-baseweb="tab-panel"] {
        background: #161F38 !important;

        border: 1px solid #2F3E5E !important;

        border-top: none;

        border-radius: 0 0 12px 12px;

        padding: 1.2rem;
    }


    /* ===================================================================== */
    /* METRIC CARDS                                                          */
    /* ===================================================================== */

    div[data-testid="stMetric"] {
        background: #1B2540 !important;

        border: 1px solid #334466 !important;

        border-radius: 12px !important;

        padding: .9rem 1rem !important;
    }


    div[data-testid="stMetric"] label {
        color: #AEBEDD !important;
    }


    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #FFFFFF !important;

        font-weight: 800 !important;
    }


    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: var(--success) !important;
    }


    /* ===================================================================== */
    /* HEADINGS                                                              */
    /* ===================================================================== */

    .stApp h1,
    .stApp h2,
    .stApp h3,
    .stApp h4 {
        color: #FFFFFF !important;
    }


    /* ===================================================================== */
    /* RESUME CARD                                                           */
    /* ===================================================================== */

    .resume-card {
        background: #10182B !important;

        border: 1px solid #334466 !important;

        border-radius: 12px;

        padding: 1rem 1.2rem;

        color: #E6EDFB !important;

        font-size: .9rem;

        line-height: 1.5;
    }


    .resume-h {
        color: #9B8EF7 !important;

        font-weight: 800;

        letter-spacing: .06em;

        margin: .8rem 0 .3rem;
    }

    /* ===================================================================== */
    /* FILE UPLOADER — Streamlit Cloud + Local                               */
    /* ===================================================================== */

    [data-testid="stFileUploader"] {
        width: 100% !important;
    }

    /* IMPORTANT: stFileUploader is not consistently a <section> in Cloud.
       Target Streamlit test IDs directly so this works in both environments. */
    [data-testid="stFileUploaderDropzone"] {
        width: 100% !important;
        background: #1B2540 !important;
        border: 1px dashed #52658A !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        opacity: 1 !important;
    }

    [data-testid="stFileUploaderDropzone"] div,
    [data-testid="stFileUploaderDropzone"] span,
    [data-testid="stFileUploaderDropzone"] p {
        color: #EAF0FF !important;
        opacity: 1 !important;
    }

    [data-testid="stFileUploaderDropzone"] small {
        color: #AEBED9 !important;
        opacity: 1 !important;
        font-size: 0.78rem !important;
    }

    [data-testid="stFileUploaderDropzone"] svg {
        color: #DCE6FA !important;
        opacity: 1 !important;
    }

    /* Browse/Upload button: cover BaseWeb variants used by Community Cloud. */
    [data-testid="stFileUploader"] button,
    [data-testid="stFileUploaderDropzone"] button,
    [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"],
    [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
        appearance: none !important;
        -webkit-appearance: none !important;
        background: linear-gradient(90deg, #6C5CE7 0%, #8B7BF0 100%) !important;
        background-color: #6C5CE7 !important;
        color: #FFFFFF !important;
        border: 1px solid #6C5CE7 !important;
        border-radius: 9px !important;
        font-weight: 700 !important;
        min-height: 42px !important;
        padding: 0.45rem 1rem !important;
        opacity: 1 !important;
        box-shadow: 0 4px 12px rgba(108, 92, 231, .25) !important;
        text-shadow: none !important;
    }

    [data-testid="stFileUploader"] button:hover,
    [data-testid="stFileUploaderDropzone"] button:hover,
    [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:hover,
    [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]:hover {
        background: linear-gradient(90deg, #5B4BE0 0%, #796BE9 100%) !important;
        background-color: #5B4BE0 !important;
        color: #FFFFFF !important;
        border-color: #5B4BE0 !important;
    }

    [data-testid="stFileUploader"] button *,
    [data-testid="stFileUploaderDropzone"] button *,
    [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] *,
    [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] * {
        color: #FFFFFF !important;
        opacity: 1 !important;
    }

    [data-testid="stFileUploader"] button svg,
    [data-testid="stFileUploaderDropzone"] button svg {
        color: #FFFFFF !important;
        stroke: #FFFFFF !important;
        opacity: 1 !important;
    }

    [data-testid="stFileUploaderFileName"] {
        color: #FFFFFF !important;
    }

    /* ===================================================================== */
    /* STATUS / ALERTS */

    /* Defensive override for any native Streamlit status widgets still rendered. */
    div[data-testid="stStatusWidget"],
    div[data-testid="stStatusWidget"] > div,
    div[data-testid="stStatusWidget"] summary,
    div[data-testid="stStatusWidget"] [data-testid="stMarkdownContainer"] {
        background: #1B2540 !important;
        color: #EAF0FF !important;
        border-color: #334466 !important;
        opacity: 1 !important;
    }

    div[data-testid="stStatusWidget"] svg {
        color: #8B7BF0 !important;
        stroke: #8B7BF0 !important;
        opacity: 1 !important;
    }

    /* Custom progress panel used by Analyze Job. It avoids Cloud-specific
       Streamlit/BaseWeb status styling differences entirely. */
    .cg-progress-panel {
        background: #1B2540 !important;
        border: 1px solid #334466 !important;
        border-radius: 12px !important;
        padding: 1rem 1.2rem !important;
        margin: .8rem 0 1.2rem !important;
        color: #EAF0FF !important;
        box-shadow: 0 8px 24px rgba(0,0,0,.16) !important;
    }

    .cg-progress-title {
        color: #FFFFFF !important;
        font-weight: 750 !important;
        font-size: 1rem !important;
        margin-bottom: .7rem !important;
    }

    .cg-progress-step {
        color: #B7C5DF !important;
        margin: .36rem 0 !important;
        font-size: .9rem !important;
        line-height: 1.35 !important;
    }

    .cg-progress-step.done {
        color: #67E8A5 !important;
    }

    .cg-progress-step.active {
        color: #FFFFFF !important;
        font-weight: 650 !important;
    }

    .cg-progress-step.pending {
        color: #7182A5 !important;
    }

    .cg-progress-spinner {
        display: inline-block !important;
        width: .75rem !important;
        height: .75rem !important;
        margin-right: .45rem !important;
        border: 2px solid #56698F !important;
        border-top-color: #8B7BF0 !important;
        border-radius: 50% !important;
        vertical-align: -.08rem !important;
    }

    .stAlert {
        background: #1B2540 !important;

        color: #EAF0FF !important;
    }


    /* ===================================================================== */
    /* EXPANDER                                                              */
    /* ===================================================================== */

    /* Streamlit Cloud renders the expander header with a native <summary>
       element. Style the real DOM node instead of the legacy CSS class so
       the closed/open states stay readable without requiring hover. */
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] > details > summary {
        background: #1B2540 !important;
        color: #EAF0FF !important;
        border: 1px solid #334466 !important;
        border-radius: 12px !important;
        opacity: 1 !important;
        min-height: 54px !important;
    }

    [data-testid="stExpander"] summary:hover,
    [data-testid="stExpander"] > details > summary:hover {
        background: #202B49 !important;
        color: #FFFFFF !important;
    }

    [data-testid="stExpander"] summary *,
    [data-testid="stExpander"] > details > summary * {
        color: #EAF0FF !important;
        fill: currentColor !important;
        stroke: currentColor !important;
        opacity: 1 !important;
    }

    [data-testid="stExpander"] summary:hover *,
    [data-testid="stExpander"] > details > summary:hover * {
        color: #FFFFFF !important;
    }

    /* The visible label is commonly a paragraph/span generated by BaseWeb. */
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span {
        color: #EAF0FF !important;
        font-weight: 650 !important;
        opacity: 1 !important;
    }

    [data-testid="stExpander"] summary:hover p,
    [data-testid="stExpander"] summary:hover span {
        color: #FFFFFF !important;
    }

    [data-testid="stExpander"] > details {
        background: transparent !important;
        border: 0 !important;
        opacity: 1 !important;
    }

    [data-testid="stExpander"] > details[open] > summary {
        border-bottom-left-radius: 0 !important;
        border-bottom-right-radius: 0 !important;
    }


    /* ===================================================================== */
    /* DIVIDERS                                                              */
    /* ===================================================================== */

    hr {
        border-color: #2B3A5E !important;
    }


    /* ===================================================================== */
    /* RESPONSIVE                                                            */
    /* ===================================================================== */

    @media (max-width: 900px) {

        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }

        .ats-banner {
            border-radius: 8px;
        }

        .hero-title {
            font-size: 1.25rem;
        }

    }

    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Rendering helpers                                                           #
# --------------------------------------------------------------------------- #

def resume_preview(text: str) -> str:
    heads = {
        "PROFESSIONAL SUMMARY",
        "CORE COMPETENCIES",
        "SELECTED CAREER HIGHLIGHTS",
        "PROFESSIONAL EXPERIENCE",
        "EARLIER PROFESSIONAL EXPERIENCE",
        "TECHNICAL SKILLS",
        "EDUCATION & CERTIFICATIONS",
        "EDUCATION AND CERTIFICATIONS",
        "EDUCATION",
        "CORE LEADERSHIP & TECHNICAL EXPERTISE",
    }

    out = ['<div class="resume-card">']

    for raw in (text or "").splitlines():

        line = raw.strip()

        if not line:
            out.append("<br>")
            continue

        if line.upper().rstrip(":") in heads:
            out.append(
                f'<div class="resume-h">'
                f'{html.escape(line.upper())}'
                f'</div>'
            )

        elif line.startswith(("- ", "* ", "• ")):
            out.append(
                f'• {html.escape(line[2:])}<br>'
            )

        else:
            out.append(
                f'{html.escape(line)}<br>'
            )

    out.append("</div>")

    return "".join(out)


def render_structured(
    value,
    empty="No content generated for this section.",
):
    if value in (None, "", {}, []):
        st.info(empty)
        return

    if isinstance(value, dict):

        for key, item in value.items():

            st.markdown(
                f"**{str(key).replace('_', ' ').title()}**"
            )

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
# Sidebar                                                                    #
# --------------------------------------------------------------------------- #

with st.sidebar:

    st.markdown(
        '<div class="brand">'
        '<span class="w">ATS</span> '
        '<span class="v">Career Guide</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="brand-sub">'
        'AI Career Intelligence &amp; Application Copilot'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="nav-group">Core Tools</div>',
        unsafe_allow_html=True,
    )

    for key, icon, label in NAV_ITEMS:

        active = (
            st.session_state["active_nav"] == key
        )

        wrap_open = (
            '<div class="nav-active">'
            if active
            else ""
        )

        wrap_close = (
            "</div>"
            if active
            else ""
        )

        if wrap_open:
            st.markdown(
                wrap_open,
                unsafe_allow_html=True,
            )

        if st.button(
            f"{icon}  {label}",
            key=f"nav_{key}",
            width="stretch",
        ):
            st.session_state["active_nav"] = key

        if wrap_close:
            st.markdown(
                wrap_close,
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="nav-group">Workspace</div>',
        unsafe_allow_html=True,
    )

    st.button(
        "🗂  My Projects",
        key="nav_projects",
        width="stretch",
    )

    st.button(
        "📊  Saved Reports",
        key="nav_reports",
        width="stretch",
    )

    st.divider()

    _user = signed_in_user()

    if _user:
        st.caption(
            f"👤 Signed in: {_user.get('name')}"
        )

    st.caption(
        "✦ Pro tip: add your LinkedIn & Naukri profile "
        "text and a company URL for deeper positioning "
        "and interview prep."
    )

    st.caption(f"API: {API_URL}")


# --------------------------------------------------------------------------- #
# Full-width hero banner                                                     #
# --------------------------------------------------------------------------- #

banner = os.path.join(
    os.path.dirname(__file__),
    "assets",
    "ats_career_guide_banner.png",
)


if os.path.exists(banner):

    # Read banner and embed it directly into the page.
    # This allows the image to scale to the available page width
    # while preserving its original aspect ratio.

    with open(banner, "rb") as f:
        banner_b64 = base64.b64encode(
            f.read()
        ).decode("utf-8")

    st.markdown(
        f"""
        <div class="ats-banner">
            <img
                src="data:image/png;base64,{banner_b64}"
                alt="ATS Career Guide"
            >
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Hero + inputs                                                              #
# --------------------------------------------------------------------------- #

st.markdown(
    '<div class="hero-tag">'
    'CAREER INTELLIGENCE WORKSPACE'
    '</div>',
    unsafe_allow_html=True,
)


st.markdown(
    '<div class="hero-title">'
    'Elevate Your Career. Realize Your Potential.'
    '</div>',
    unsafe_allow_html=True,
)


st.markdown(
    '<div class="hero-sub">'
    'Upload your resume and a job description to get a dynamic ATS score, '
    'a premium tailored resume, and end-to-end application guidance.'
    '</div>',
    unsafe_allow_html=True,
)


st.markdown(
    '<div class="field-label">'
    'Upload Your Resume *'
    '</div>',
    unsafe_allow_html=True,
)


resume_file = st.file_uploader(
    "Resume",
    type=["pdf", "docx", "txt", "md"],
    label_visibility="collapsed",
)


st.markdown(
    '<div class="field-label">'
    'Job Description URL'
    '</div>',
    unsafe_allow_html=True,
)


jd_url = st.text_input(
    "JD URL",
    placeholder=(
        "Paste a public job URL "
        "(LinkedIn, Naukri, careers page)..."
    ),
    label_visibility="collapsed",
)


st.markdown(
    '<div class="field-label">'
    'OR, PASTE JOB DESC. BELOW'
    '</div>',
    unsafe_allow_html=True,
)


jd_text = st.text_area(
    "JD text",
    height=150,
    placeholder=(
        "Paste the full job description here..."
    ),
    label_visibility="collapsed",
)


# --------------------------------------------------------------------------- #
# Optional research inputs                                                   #
# --------------------------------------------------------------------------- #

with st.expander(
    "➕ Add company, leadership & market inputs (optional)"
):

    c1, c2 = st.columns(2)

    with c1:

        company_url = st.text_input(
            "Company Website / Profile URL"
        )

        linkedin_profile = st.text_area(
            "LinkedIn Profile Data",
            height=100,
        )

        naukri_profile = st.text_area(
            "Naukri Profile Data",
            height=100,
        )

    with c2:

        leadership_url = st.text_input(
            "Leadership / Investor-Relations URL"
        )

        market_query = st.text_input(
            "Market Research Query"
        )

        market_urls = st.text_area(
            "Additional Research URLs",
            height=100,
        )


# --------------------------------------------------------------------------- #
# Run analysis                                                               #
# --------------------------------------------------------------------------- #

def render_progress_panel(placeholder, active_index: int, state: str = "running", message: str = "Building your career guide..."):
    steps = [
        "Inputs received",
        "Extracting dynamic keywords & candidate profile",
        "Scoring resume against the job description",
        "Generating premium resume & application artefacts",
    ]
    rows = []
    for idx, step in enumerate(steps):
        if state == "complete" or idx < active_index:
            cls, icon = "done", "✓"
        elif state == "error" and idx == active_index:
            cls, icon = "active", "✕"
        elif idx == active_index:
            cls, icon = "active", '<span class="cg-progress-spinner"></span>'
        else:
            cls, icon = "pending", "○"
        rows.append(f'<div class="cg-progress-step {cls}">{icon} {html.escape(step)}</div>')
    placeholder.markdown(
        '<div class="cg-progress-panel">'
        f'<div class="cg-progress-title">{html.escape(message)}</div>'
        + ''.join(rows)
        + '</div>',
        unsafe_allow_html=True,
    )

# Run analysis                                                               #
# --------------------------------------------------------------------------- #

run_disabled = (
    resume_file is None
    or (
        not jd_text.strip()
        and not jd_url.strip()
    )
)


if st.button(
    "🚀  Analyze job & build career guide",
    type="primary",
    width="stretch",
):

    if run_disabled:

        st.warning(
            "Please upload your resume and provide "
            "a job URL or paste the job description."
        )

        st.stop()


    progress = st.empty()
    render_progress_panel(progress, 3, "running", "Building your career guide...")

    try:
        resp = httpx.post(
            f"{API_URL}/v3/career-guide",
            files={
                "resume": (
                    resume_file.name,
                    resume_file.getvalue(),
                    resume_file.type or "text/plain",
                )
            },
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
            headers=auth_headers(),
            timeout=httpx.Timeout(240.0, read=None),
        )
        resp.raise_for_status()
        st.session_state["result"] = resp.json()
        st.session_state["research_fallback_attempted"] = False
        render_progress_panel(progress, 4, "complete", "Career Guide ready")

    except httpx.HTTPStatusError as exc:
        render_progress_panel(progress, 3, "error", "Career Guide failed")
        st.error(
            f"API returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:400]}"
        )

    except httpx.RequestError as exc:
        render_progress_panel(progress, 3, "error", "Could not connect to the API")
        st.error(f"Could not connect to the API at {API_URL}: {exc}")


# --------------------------------------------------------------------------- #
# Results                                                                    #
# --------------------------------------------------------------------------- #

result = st.session_state.get("result")

# Independent V3 research fallback. The primary career-guide response can finish
# successfully even when public-page scraping fails, so retrieve research again
# through the dedicated route when a company URL was supplied.
if result and company_url.strip():
    existing_research = result.get("research") or {}
    research_missing = not isinstance(existing_research, dict) or not (
        existing_research.get("company_profile") or existing_research.get("sources")
    )
    if research_missing and not st.session_state.get("research_fallback_attempted", False):
        st.session_state["research_fallback_attempted"] = True
        try:
            research_response = httpx.post(
                f"{API_URL}/v3/research",
                data={
                    "company_url": company_url.strip(),
                    "leadership_url": leadership_url.strip(),
                    "market_urls": market_urls,
                    "market_query": market_query.strip(),
                },
                headers=auth_headers(),
                timeout=45.0,
            )
            research_response.raise_for_status()
            research_payload = research_response.json()
            recovered_research = research_payload.get("research") or {}
            if isinstance(recovered_research, dict) and (
                recovered_research.get("company_profile") or recovered_research.get("sources")
            ):
                result["research"] = recovered_research
                result["sources"] = recovered_research.get("sources", [])
                st.session_state["result"] = result
        except Exception as research_exc:
            result.setdefault("warnings", []).append(
                f"Research fallback failed: {type(research_exc).__name__}: {research_exc}"
            )

if result:

    st.divider()

    before = result.get(
        "score_before",
        0,
    )

    after = result.get(
        "score_after",
        0,
    )

    fit = result.get(
        "job_fit",
        {},
    )


    # ----------------------------------------------------------------------- #
    # Top score cards                                                         #
    # ----------------------------------------------------------------------- #

    k1, k2, k3, k4 = st.columns(4)


    k1.metric(
        "Overall fit",
        f"{fit.get('overall', 0)} / 100",
    )


    k2.metric(
        "ATS — Current",
        f"{before} / 100",
    )


    k3.metric(
        "ATS — Upgraded",
        f"{after} / 100",
        delta=f"{after - before:+d} pts",
    )


    k4.metric(
        "Decision",
        fit.get(
            "recommendation",
            "REVIEW",
        ),
    )


    # ----------------------------------------------------------------------- #
    # Score calculation                                                       #
    # ----------------------------------------------------------------------- #

    comp = result.get(
        "ats_analysis",
        {},
    ).get(
        "components",
        {},
    )


    st.caption(
        f"Score = 65% keyword coverage "
        f"({comp.get('keyword_coverage', 0):.0%}) + "
        f"15% semantic match "
        f"({comp.get('semantic_similarity', 0):.0%}) + "
        f"20% section completeness "
        f"({comp.get('section_completeness', 0):.0%}). "
        f"Resume generation mode: "
        f"{result.get('generation_mode', 'n/a')}."
    )


    # ----------------------------------------------------------------------- #
    # Result tabs                                                             #
    # ----------------------------------------------------------------------- #

    tabs = st.tabs(
        [
            "Fit & Gaps",
            "Resume",
            "LinkedIn",
            "Naukri",
            "Interview Kit",
            "Career Roadmap",
            "Research",
        ]
    )


    # ======================================================================= #
    # FIT & GAPS                                                              #
    # ======================================================================= #

    with tabs[0]:

        st.subheader(
            "ATS score dashboard"
        )


        d1, d2, d3 = st.columns(3)


        d1.metric(
            "Keyword coverage",
            f"{comp.get('keyword_coverage', 0):.0%}",
        )


        d2.metric(
            "Semantic match",
            f"{comp.get('semantic_similarity', 0):.0%}",
        )


        d3.metric(
            "Section completeness",
            f"{comp.get('section_completeness', 0):.0%}",
        )


        st.subheader(
            "Strengths (matched keywords)"
        )


        st.write(
            ", ".join(
                fit.get(
                    "strengths",
                    [],
                )
            )
            or "No strong matches detected."
        )


        if fit.get("partial"):

            st.subheader(
                "Partial matches"
            )

            st.write(
                ", ".join(
                    fit.get(
                        "partial",
                        [],
                    )
                )
            )


        st.subheader(
            "Gaps (missing keywords)"
        )


        st.write(
            ", ".join(
                fit.get(
                    "gaps",
                    [],
                )
            )
            or "No major gaps detected."
        )


        if fit.get("missing_sections"):

            st.warning(
                "Missing resume sections: "
                + ", ".join(
                    fit["missing_sections"]
                )
            )


    # ======================================================================= #
    # RESUME                                                                  #
    # ======================================================================= #

    with tabs[1]:

        for warning in result.get(
            "warnings",
            [],
        ):
            st.warning(warning)


        resume_out = result.get(
            "optimized_resume",
            "",
        )


        st.markdown(
            resume_preview(resume_out),
            unsafe_allow_html=True,
        )


        c_txt, c_docx = st.columns(2)


        c_txt.download_button(
            "⬇ Download TXT",
            resume_out,
            "ats-career-guide-resume.txt",
            "text/plain",
            width="stretch",
        )


        try:

            docx = httpx.post(
                f"{API_URL}/v3/export-docx",

                json={
                    "resume_text": resume_out
                },

                headers=auth_headers(),

                timeout=60,
            )

            docx.raise_for_status()


            c_docx.download_button(
                "⬇ Download DOCX",

                docx.content,

                "ats-career-guide-resume.docx",

                "application/"
                "vnd.openxmlformats-officedocument."
                "wordprocessingml.document",

                width="stretch",
            )


        except Exception as exc:

            c_docx.warning(
                f"DOCX export unavailable: {exc}"
            )


    # ======================================================================= #
    # LINKEDIN                                                                #
    # ======================================================================= #

    with tabs[2]:

        render_structured(
            result.get(
                "linkedin_optimization",
                {},
            )
        )


    # ======================================================================= #
    # NAUKRI                                                                  #
    # ======================================================================= #

    with tabs[3]:

        render_structured(
            result.get(
                "naukri_optimization",
                {},
            )
        )


    # ======================================================================= #
    # INTERVIEW KIT                                                           #
    # ======================================================================= #

    with tabs[4]:

        kit = result.get(
            "interview_kit",
            {},
        )


        labels = {

            "resume_questions":
                "Resume-specific questions",

            "company_questions":
                "Company questions",

            "leadership_questions":
                "Leadership questions",

            "technical_or_domain_questions":
                "Technical / domain questions",

            "gap_questions":
                "Gap questions",

            "star_story_blueprints":
                "STAR story blueprints",
        }


        if isinstance(
            kit,
            dict,
        ) and kit:

            for key, title in labels.items():

                if kit.get(key):

                    st.subheader(title)

                    render_structured(
                        kit.get(key)
                    )

        else:

            st.info(
                "No interview kit generated."
            )


    # ======================================================================= #
    # CAREER ROADMAP                                                          #
    # ======================================================================= #

    with tabs[5]:

        render_structured(
            result.get(
                "career_roadmap",
                {},
            )
        )


    # ======================================================================= #
    # RESEARCH                                                                #
    # ======================================================================= #

    with tabs[6]:

        research = (
            result.get("research")
            or {}
        )


        if (
            isinstance(research, dict)
            and (
                research.get("company_profile")
                or research.get("sources")
            )
        ):

            cp = research.get(
                "company_profile",
                {},
            )


            if cp.get("overview"):

                st.write(
                    cp["overview"]
                )


            if research.get("strategy"):

                st.subheader(
                    "Business & strategic signals"
                )


                for signal in research["strategy"]:

                    st.markdown(
                        f"- {signal}"
                    )


            if research.get("sources"):

                st.subheader(
                    "Sources"
                )


                for src in research["sources"]:

                    st.markdown(
                        f"- "
                        f"[{src.get('label', 'Source')}]"
                        f"({src.get('url', '#')})"
                    )


        else:
            warning = research.get("research_warning") if isinstance(research, dict) else ""
            if company_url.strip():
                st.warning(
                    "A company URL was supplied, but no readable research package was returned. "
                    + (str(warning) if warning else "The public page may require JavaScript or may block automated access.")
                )
                st.caption("The supplied URL was received. Add a leadership URL or market query for additional research signals.")
            else:
                st.info("Add a company URL or market inputs above to enable public-page research.")
