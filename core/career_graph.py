from __future__ import annotations

import json
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from .career_tools import build_job_spec, gap_analysis, score_fit
from .config import DEMO_MODE, GROQ_API_KEY, GROQ_MODEL
from .evidence import evidence_guard, extract_candidate_profile
from .models import CareerGuideState
from .research import build_research_pack
from .kb import CareerKnowledgeBase
from .config import CHROMA_PERSIST_DIR


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


def research_node(state: CareerGuideState) -> CareerGuideState:
    research = build_research_pack(
        company_url=state.get("company_url", ""),
        leadership_url=state.get("leadership_url", ""),
        market_urls=state.get("market_urls", []),
        market_query=state.get("market_query", ""),
    )
    kb = CareerKnowledgeBase(CHROMA_PERSIST_DIR)
    if research.get("company_profile"):
        kb.upsert("company-research", json.dumps(research["company_profile"]), {"type": "company-research"})
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
        "keyword_gap": {"matched": fit.get("matched_keywords", []), "missing": fit.get("missing_keywords", [])},
        "skill_gap": gaps,
        "experience_gap": {"missing_evidence": gaps.get("missing", [])},
        "career_gap": {"priority_gaps": gaps.get("missing", [])},
    }


def generation_node(state: CareerGuideState) -> CareerGuideState:
    if DEMO_MODE or not GROQ_API_KEY:
        return demo_generation(state)

    from langchain_groq import ChatGroq

    llm = ChatGroq(model=GROQ_MODEL, temperature=0.15, api_key=GROQ_API_KEY)
    candidate = state.get("candidate_profile", {})
    job = state.get("job_spec", {})
    research = state.get("research", {})
    kb = CareerKnowledgeBase(CHROMA_PERSIST_DIR)
    evidence_context = kb.query(" ".join(job.get("keywords", [])[:12]), n_results=6)
    prompt = f"""You are an evidence-first ATS Career Guide.
Return ONLY valid JSON with exactly these keys:
optimized_resume, cover_letter, linkedin_optimization, naukri_optimization, interview_kit, career_roadmap.
Never invent employers, dates, degrees, certifications, metrics, ownership, or skills.
Use only evidence from the candidate profile/resume. Treat company research as context, not candidate evidence.
Candidate profile:
{json.dumps(candidate)[:18000]}
Resume:
{state.get('resume_text','')[:24000]}
Job:
{json.dumps(job)[:14000]}
Company research:
{json.dumps(research)[:12000]}
Retrieved career evidence:
{json.dumps(evidence_context)[:12000]}

For interview_kit return JSON containing 5 sections: resume_questions, company_questions, leadership_questions, technical_or_domain_questions, gap_questions.
For career_roadmap return 30_days, 60_days, 90_days and longer_term.
For LinkedIn/Naukri optimization return headline, about_or_summary, skills, keywords, and changes.
"""
    response = llm.invoke(prompt)
    raw = response.content if isinstance(response.content, str) else str(response.content)
    payload = parse_json(raw) or {}
    if not payload.get("cover_letter") and not DEMO_MODE:
        cover_prompt = f"""Write a concise professional cover letter for the target role using only the candidate evidence below.
Do not invent employers, dates, metrics, ownership or skills. Return plain text only; no JSON, Markdown headings, bullets, **, ## or --- separators.
Candidate:
{candidate_context[:3500]}
Target Job:
{job_context[:3000]}
Job Gaps:
{json.dumps(gaps, ensure_ascii=False)[:700]}
"""
        try:
            cover_response = llm.invoke(cover_prompt)
            cover_text = cover_response.content if isinstance(cover_response.content, str) else str(cover_response.content)
            payload["cover_letter"] = cover_text.strip()
        except Exception:
            warnings.append("Cover letter generation was unavailable for this run.")

    optimized = str(payload.get("optimized_resume", "")).strip()
    guard = evidence_guard(optimized, candidate)
    warnings = []
    if not guard["pass"]:
        warnings.append("Evidence guard flagged unsupported numeric claims in the generated resume. Review before use.")
    return {
        "optimized_resume": optimized,
        "cover_letter": str(payload.get("cover_letter", "")),
        "linkedin_optimization": payload.get("linkedin_optimization", {}),
        "naukri_optimization": payload.get("naukri_optimization", {}),
        "interview_kit": payload.get("interview_kit", {}),
        "career_roadmap": payload.get("career_roadmap", {}),
        "warnings": warnings,
    }


def demo_generation(state: CareerGuideState) -> CareerGuideState:
    spec = state.get("job_spec", {})
    profile = state.get("candidate_profile", {})
    keywords = spec.get("keywords", [])
    optimized = "ATS CAREER GUIDE RESUME DRAFT\n\nSUMMARY\n" + (profile.get("headline") or "Experienced professional aligned to the target role.") + "\n\nCORE SKILLS\n" + ", ".join(keywords[:18]) + "\n\nPROFESSIONAL EXPERIENCE\n" + state.get("resume_text", "")[:5000]
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


def parse_json(raw: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
        return None


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
