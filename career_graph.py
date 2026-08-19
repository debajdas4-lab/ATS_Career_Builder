from __future__ import annotations

import json
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from .career_tools import build_job_spec, gap_analysis, score_fit
from .config import CHROMA_PERSIST_DIR, DEMO_MODE, GROQ_API_KEY, GROQ_MODEL
from .evidence import evidence_guard, extract_candidate_profile
from .kb import CareerKnowledgeBase
from .models import CareerGuideState
from .research import build_research_pack


def candidate_node(state: CareerGuideState) -> CareerGuideState:
    profile = extract_candidate_profile(
        state.get("resume_text", ""),
        state.get("linkedin_profile", ""),
        state.get("naukri_profile", ""),
    )
    kb = CareerKnowledgeBase(CHROMA_PERSIST_DIR)
    kb.upsert("candidate-profile", json.dumps(profile), {"type": "candidate-profile"})
    kb.upsert("candidate-resume", state.get("resume_text", ""), {"type": "candidate-resume"})
    if state.get("linkedin_profile"):
        kb.upsert("candidate-linkedin", state.get("linkedin_profile", ""), {"type": "linkedin"})
    if state.get("naukri_profile"):
        kb.upsert("candidate-naukri", state.get("naukri_profile", ""), {"type": "naukri"})
    return {"candidate_profile": profile}


def jd_node(state: CareerGuideState) -> CareerGuideState:
    spec = build_job_spec(state.get("job_description", ""), source_url=state.get("job_url", ""))
    kb = CareerKnowledgeBase(CHROMA_PERSIST_DIR)
    kb.upsert("job-spec", json.dumps(spec), {"type": "job-spec"})
    kb.upsert("job-description", state.get("job_description", ""), {"type": "job-description"})
    return {"job_spec": spec, "keywords": spec.get("keywords", [])}


def _empty_research(company_url: str = "") -> dict[str, Any]:
    package: dict[str, Any] = {
        "company_profile": {},
        "leadership": [],
        "strategy": [],
        "recent_signals": [],
        "competitors": [],
        "sources": [],
        "market_signals": [],
    }
    if company_url:
        package["company_profile"] = {
            "name": "Company Research",
            "overview": "The company URL was supplied, but detailed public-page research was unavailable during this run.",
            "url": company_url,
        }
        package["sources"] = [{"type": "company", "label": "Company Website", "url": company_url}]
    return package


def research_node(state: CareerGuideState) -> CareerGuideState:
    company_url = state.get("company_url", "").strip()
    try:
        research = build_research_pack(
            company_url=company_url,
            leadership_url=state.get("leadership_url", ""),
            market_urls=state.get("market_urls", []),
            market_query=state.get("market_query", ""),
        )
    except Exception as exc:
        research = _empty_research(company_url)
        research["research_warning"] = f"Public research step failed: {type(exc).__name__}: {exc}"

    if not isinstance(research, dict):
        research = _empty_research(company_url)

    if company_url and not research.get("company_profile") and not research.get("sources"):
        research = _empty_research(company_url)

    kb = CareerKnowledgeBase(CHROMA_PERSIST_DIR)
    if research.get("company_profile"):
        kb.upsert(
            "company-research",
            json.dumps(research["company_profile"], ensure_ascii=False),
            {"type": "company-research"},
        )

    return {"research": research}


def fit_node(state: CareerGuideState) -> CareerGuideState:
    resume = state.get("resume_text", "")
    spec = state.get("job_spec", {})
    fit = score_fit(resume, spec)
    gaps = gap_analysis(resume, spec)
    return {
        "ats_analysis": fit,
        "job_fit": {
            "overall": fit.get("score", 0),
            "recommendation": fit.get("recommendation", "REVIEW"),
            "strengths": gaps.get("strong", []),
            "partial": gaps.get("partial", []),
            "risks": gaps.get("missing", []),
        },
        "keyword_gap": {
            "matched": fit.get("matched_keywords", []),
            "missing": fit.get("missing_keywords", []),
        },
        "skill_gap": gaps,
        "experience_gap": {"missing_evidence": gaps.get("missing", [])},
        "career_gap": {"priority_gaps": gaps.get("missing", [])},
    }


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _plain_text(value: Any) -> str:
    if not value:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = re.sub(r"^```(?:markdown|text)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.M)
    return text.strip()


def _compact_context(state: CareerGuideState) -> tuple[str, str, str, str, str, str]:
    candidate = state.get("candidate_profile", {})
    job = state.get("job_spec", {})
    research = state.get("research", {})
    resume = state.get("resume_text", "")
    gaps = state.get("career_gap", {}).get("priority_gaps", [])
    fit = state.get("job_fit", {})

    kb = CareerKnowledgeBase(CHROMA_PERSIST_DIR)
    evidence = kb.query(" ".join(job.get("keywords", [])[:8]), n_results=3)

    candidate_context = json.dumps(candidate, ensure_ascii=False)[:6000]
    resume_context = resume[:8000]
    job_context = json.dumps(job, ensure_ascii=False)[:4500]
    research_context = json.dumps(
        {
            "company_profile": research.get("company_profile"),
            "leadership": research.get("leadership"),
            "strategy": research.get("strategy"),
            "market_signals": research.get("market_signals"),
            "sources": research.get("sources"),
        },
        ensure_ascii=False,
    )[:3000]
    gap_context = json.dumps(gaps, ensure_ascii=False)[:1000]
    fit_context = json.dumps(fit, ensure_ascii=False)[:1200]
    evidence_context = json.dumps(evidence, ensure_ascii=False)[:2500]

    return (
        candidate_context,
        resume_context,
        job_context,
        research_context,
        gap_context,
        fit_context + "\nEvidence:\n" + evidence_context,
    )


def _generate_cover_letter(llm, candidate_context: str, resume_context: str, job_context: str, fit_context: str) -> str:
    prompt = f"""Write a concise, professional cover letter for the target role.
Use ONLY the candidate evidence below. Never invent employers, dates, certifications, metrics, ownership, or skills.
Return plain text only. Do not use JSON, Markdown headings, **, ##, tables, or --- separators.

CANDIDATE:
{candidate_context[:2500]}

RESUME:
{resume_context[:3500]}

TARGET JOB:
{job_context[:2500]}

ROLE FIT:
{fit_context[:1000]}
"""
    try:
        response = llm.invoke(prompt)
        return _plain_text(response.content if isinstance(response.content, str) else str(response.content))
    except Exception:
        return ""



def _fallback_linkedin(profile: dict[str, Any], job: dict[str, Any], resume_text: str) -> dict[str, Any]:
    headline = str(profile.get("headline") or "Technical Program & Transformation Leader")
    keywords = [str(x) for x in (job.get("keywords") or [])[:10] if str(x).strip()]
    about = str(profile.get("summary") or profile.get("professional_summary") or "Experienced technology and transformation leader with a track record of leading complex, cross-functional programs and delivering measurable business outcomes.")
    return {
        "headline": headline,
        "about_or_summary": about,
        "skills": keywords,
        "keywords": keywords,
        "changes": [
            "Align the headline to the target role without adding unsupported claims.",
            "Prioritize experience and skills already evidenced in the resume.",
            "Use concise achievement bullets with verified outcomes only.",
        ],
    }


def _fallback_naukri(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    headline = str(profile.get("headline") or "Technical Program & Transformation Leader")
    keywords = [str(x) for x in (job.get("keywords") or [])[:12] if str(x).strip()]
    return {
        "title": headline,
        "key_summary": str(profile.get("summary") or profile.get("professional_summary") or "Experienced technology and transformation leader focused on complex program delivery, governance and business outcomes."),
        "core_competencies": keywords,
        "keywords": keywords,
        "changes": [
            "Keep the profile concise and keyword-aligned to the target role.",
            "Use employer-wise experience with dates and verified achievements.",
        ],
    }


def generation_node(state: CareerGuideState) -> CareerGuideState:
    if DEMO_MODE or not GROQ_API_KEY:
        return demo_generation(state)

    from langchain_groq import ChatGroq

    llm = ChatGroq(model=GROQ_MODEL, temperature=0.15, api_key=GROQ_API_KEY)
    candidate_context, resume_context, job_context, research_context, gap_context, fit_context = _compact_context(state)

    prompt = f"""You are an evidence-first ATS Career Guide.
Return ONLY valid JSON with these keys:
optimized_resume, cover_letter, linkedin_optimization, naukri_optimization, interview_kit, career_roadmap.

Rules:
- Never invent employers, dates, degrees, certifications, metrics, ownership, or skills.
- Candidate evidence is authoritative; company research is context only.
- Preserve every employer as a separate employer block.
- Keep the optimized resume complete, professional, plain text, and ATS-friendly.
- Do NOT use Markdown syntax such as **, ##, ###, ---, tables, or fenced code blocks in optimized_resume or cover_letter.
- Keep the resume concise enough to complete; do not stop after the first employers.
- Do not duplicate Education, Certifications, Core Skills, or Experience sections.
- Return an actual cover_letter, not instructions about how to write one.

CANDIDATE:
{candidate_context}

SOURCE RESUME:
{resume_context}

TARGET JOB:
{job_context}

COMPANY / MARKET CONTEXT:
{research_context}

PRIORITY GAPS:
{gap_context}

FIT / EVIDENCE:
{fit_context}

Output requirements:
- interview_kit: resume_questions, company_questions, leadership_questions, technical_or_domain_questions, gap_questions.
- career_roadmap: 30_days, 60_days, 90_days, longer_term.
- linkedin_optimization and naukri_optimization: headline, about_or_summary, skills, keywords, changes.
"""

    warnings: list[str] = []
    try:
        response = llm.invoke(prompt)
        raw = response.content if isinstance(response.content, str) else str(response.content)
        payload = _parse_json(raw) or {}
    except Exception as exc:
        payload = {}
        warnings.append(f"Primary AI generation failed: {type(exc).__name__}: {exc}")

    # Dedicated compact cover-letter recovery, using correctly scoped variables.
    cover_letter = _plain_text(payload.get("cover_letter", ""))
    if not cover_letter:
        cover_letter = _generate_cover_letter(llm, candidate_context, resume_context, job_context, fit_context)
        if not cover_letter:
            warnings.append("Cover letter generation was unavailable for this run.")

    optimized = _plain_text(payload.get("optimized_resume", ""))
    guard = evidence_guard(optimized, state.get("candidate_profile", {})) if optimized else {"pass": True, "unsupported_claims": []}
    if not guard.get("pass", True):
        warnings.append("Evidence review required for one or more quantified claims in the generated resume.")

    research = state.get("research", {})
    if isinstance(research, dict) and research.get("research_warning"):
        warnings.append(str(research["research_warning"]))

    linkedin_optimization = payload.get("linkedin_optimization", {})
    naukri_optimization = payload.get("naukri_optimization", {})
    if not linkedin_optimization:
        linkedin_optimization = _fallback_linkedin(state.get("candidate_profile", {}), state.get("job_spec", {}), state.get("resume_text", ""))
        warnings.append("LinkedIn optimization fallback was used because the primary AI response did not return a structured LinkedIn artifact.")
    if not naukri_optimization:
        naukri_optimization = _fallback_naukri(state.get("candidate_profile", {}), state.get("job_spec", {}))
        warnings.append("Naukri optimization fallback was used because the primary AI response did not return a structured Naukri artifact.")

    return {
        "optimized_resume": optimized,
        "cover_letter": cover_letter,
        "linkedin_optimization": linkedin_optimization,
        "naukri_optimization": naukri_optimization,
        "interview_kit": payload.get("interview_kit", {}),
        "career_roadmap": payload.get("career_roadmap", {}),
        "evidence_validation": guard,
        "warnings": warnings,
    }


def demo_generation(state: CareerGuideState) -> CareerGuideState:
    spec = state.get("job_spec", {})
    profile = state.get("candidate_profile", {})
    keywords = spec.get("keywords", [])
    optimized = (
        "ATS CAREER GUIDE RESUME DRAFT\n\nSUMMARY\n"
        + (profile.get("headline") or "Experienced professional aligned to the target role.")
        + "\n\nCORE SKILLS\n"
        + ", ".join(keywords[:18])
        + "\n\nPROFESSIONAL EXPERIENCE\n"
        + state.get("resume_text", "")[:5000]
    )
    return {
        "optimized_resume": optimized,
        "cover_letter": "Demo mode cover letter placeholder. Enable GROQ_API_KEY for personalized generation.",
        "linkedin_optimization": {"headline": profile.get("headline", ""), "keywords": keywords[:15]},
        "naukri_optimization": {"headline": profile.get("headline", ""), "keywords": keywords[:15]},
        "interview_kit": {
            "resume_questions": ["Walk me through the most relevant transformation you led."],
            "company_questions": ["Why this company and this role?"],
            "leadership_questions": ["How do you align competing executive stakeholders?"],
            "technical_or_domain_questions": ["How do you manage technical risk in a transformation program?"],
            "gap_questions": state.get("career_gap", {}).get("priority_gaps", []),
        },
        "career_roadmap": {
            "30_days": ["Finalize role-specific positioning", "Prepare five STAR stories"],
            "60_days": ["Close the top recurring skill gap"],
            "90_days": ["Run mock interviews and calibrate answers"],
            "longer_term": ["Build evidence in the highest-demand target capability"],
        },
        "warnings": ["Demo mode is enabled or GROQ_API_KEY is missing; generated materials are placeholders."],
    }


def build_career_graph():
    graph = StateGraph(CareerGuideState)
    graph.add_node("candidate_intelligence", candidate_node)
    graph.add_node("job_intelligence", jd_node)
    graph.add_node("company_research", research_node)
    graph.add_node("fit_analysis", fit_node)
    graph.add_node("application_and_coaching", generation_node)
    graph.add_edge(START, "candidate_intelligence")
    graph.add_edge("candidate_intelligence", "job_intelligence")
    graph.add_edge("job_intelligence", "company_research")
    graph.add_edge("company_research", "fit_analysis")
    graph.add_edge("fit_analysis", "application_and_coaching")
    graph.add_edge("application_and_coaching", END)
    return graph.compile()


def run_career_guide(**kwargs: Any) -> CareerGuideState:
    return build_career_graph().invoke(kwargs)
