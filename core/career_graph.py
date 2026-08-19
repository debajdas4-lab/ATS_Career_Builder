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
    evidence_context = kb.query(" ".join(job.get("keywords", [])[:10]), n_results=3)
    # Keep the generation request comfortably below low-tier Groq TPM limits.
    # The candidate profile, JobSpec and retrieved evidence already contain the
    # highest-value structured information, so the raw documents are included
    # only as compact supporting context rather than being resent in full.
    candidate_context = json.dumps(candidate, ensure_ascii=False)[:7500]
    resume_context = state.get("resume_text", "")[:8500]
    job_context = json.dumps(job, ensure_ascii=False)[:5500]

    # Research can contain full fetched pages. Keep only decision-useful fields
    # and aggressively cap them before they reach the LLM.
    compact_research = {
        key: research.get(key)
        for key in ("company_profile", "leadership", "strategy", "market", "sources")
        if research.get(key)
    }
    research_context = json.dumps(compact_research, ensure_ascii=False)[:3500]

    # ChromaDB retrieval is useful evidence, but six large chunks duplicated too
    # much of the resume. Keep only the top three and cap the serialized context.
    compact_evidence = evidence_context[:3] if isinstance(evidence_context, list) else evidence_context
    evidence_text = json.dumps(compact_evidence, ensure_ascii=False)[:3000]

    gaps = state.get("career_gap", {}).get("priority_gaps", [])
    fit = state.get("job_fit", {})

    prompt = f"""You are an evidence-first ATS Career Guide.
Return ONLY valid JSON with exactly these keys:
optimized_resume, cover_letter, linkedin_optimization, naukri_optimization, interview_kit, career_roadmap.

Rules:
- Never invent employers, dates, degrees, certifications, metrics, ownership, or skills.
- Candidate evidence is authoritative. Company research is context only.
- Preserve important quantified achievements when supported by evidence.
- Be concise: avoid repeating the same evidence across outputs.

CANDIDATE PROFILE:
{candidate_context}

SELECTED RESUME EVIDENCE:
{resume_context}

TARGET JOB:
{job_context}

JOB FIT:
{json.dumps(fit, ensure_ascii=False)[:1800]}

PRIORITY GAPS:
{json.dumps(gaps, ensure_ascii=False)[:1200]}

COMPANY / MARKET CONTEXT:
{research_context}

RETRIEVED EVIDENCE:
{evidence_text}

Output requirements:
- interview_kit: resume_questions, company_questions, leadership_questions, technical_or_domain_questions, gap_questions.
- career_roadmap: 30_days, 60_days, 90_days, longer_term.
- linkedin_optimization and naukri_optimization: headline, about_or_summary, skills, keywords, changes.
"""
    response = llm.invoke(prompt)
    raw = response.content if isinstance(response.content, str) else str(response.content)
    payload = parse_json(raw)

    warnings: list[str] = []

    # A long multi-artifact response can occasionally be truncated or malformed.
    # Retry once with a smaller recovery prompt instead of silently returning
    # empty Resume/Cover Letter/Profile/Roadmap outputs.
    if not payload or not str(payload.get("optimized_resume", "")).strip():
        recovery_prompt = f"""Return ONLY one valid JSON object. No markdown fences and no commentary.
Required keys:
optimized_resume, cover_letter, linkedin_optimization, naukri_optimization, interview_kit, career_roadmap.

Use only the evidence below. Never invent employers, dates, degrees, certifications, metrics, ownership, or skills.
Keep the optimized resume concise but complete. Keep all other outputs concise.

CANDIDATE:
{candidate_context[:5000]}

RESUME EVIDENCE:
{resume_context[:6000]}

TARGET JOB:
{job_context[:3500]}

PRIORITY GAPS:
{json.dumps(gaps, ensure_ascii=False)[:800]}

COMPANY CONTEXT:
{research_context[:1500]}
"""
        recovery_response = llm.invoke(recovery_prompt)
        recovery_raw = (
            recovery_response.content
            if isinstance(recovery_response.content, str)
            else str(recovery_response.content)
        )
        recovered = parse_json(recovery_raw)
        if recovered:
            payload = recovered
            warnings.append(
                "The first generation response was incomplete; the Career Guide automatically regenerated a compact valid result."
            )
        else:
            payload = {}
            warnings.append(
                "The AI response could not be parsed into the required structured output. Retry the analysis with shorter profile/research inputs."
            )

    optimized = str(payload.get("optimized_resume", "")).strip()
    guard = evidence_guard(optimized, candidate) if optimized else {"pass": True}
    if not guard["pass"]:
        warnings.append(
            "Evidence guard flagged unsupported numeric claims in the generated resume. Review before use."
        )

    return {
        "optimized_resume": optimized,
        "cover_letter": str(payload.get("cover_letter", "")).strip(),
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
    """Parse a model JSON object while tolerating markdown/prose wrappers."""
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    # Extract the largest complete-looking JSON object from surrounding prose.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        try:
            value = json.loads(candidate)
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
