from __future__ import annotations

import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .config import DEMO_MODE, GROQ_API_KEY, GROQ_MODEL
from .mcp_tools import extract_keywords, score_resume


class ResumeState(TypedDict, total=False):
    resume_text: str
    job_description: str
    keywords: list[str]
    analysis: dict
    optimized_resume: str
    cover_note: str
    warnings: list[str]


def keyword_node(state: ResumeState) -> ResumeState:
    keywords = extract_keywords(state["job_description"])
    return {"keywords": keywords, "analysis": score_resume(state["resume_text"], keywords)}


def optimize_node(state: ResumeState) -> ResumeState:
    if DEMO_MODE or not GROQ_API_KEY:
        return {
            "optimized_resume": _demo_resume(state),
            "cover_note": "Demo mode was used. Add GROQ_API_KEY for AI rewriting.",
            "warnings": ["AI rewrite was not called because DEMO_MODE is enabled or GROQ_API_KEY is missing."],
        }
    from langchain_groq import ChatGroq

    llm = ChatGroq(model=GROQ_MODEL, temperature=0.15, api_key=GROQ_API_KEY)
    prompt = f"""You are an ATS resume strategist and ethical career coach.
Rewrite the resume for the job description without inventing employers, dates, degrees, metrics, or skills.
Use only facts present in the resume. You may improve wording, ordering, clarity, and bullet structure.
Return valid JSON with exactly two keys: optimized_resume and cover_note.
optimized_resume must be plain text with these sections: SUMMARY, CORE SKILLS, PROFESSIONAL EXPERIENCE, EDUCATION, CERTIFICATIONS.
Use concise ATS-readable bullets, standard headings, no tables, no columns, no icons and no graphics.
Job keywords: {json.dumps(state['keywords'])}
Resume:\n{state['resume_text'][:24000]}
Job description:\n{state['job_description'][:24000]}"""
    response = llm.invoke(prompt)
    raw = response.content if isinstance(response.content, str) else str(response.content)
    payload = _parse_model_payload(raw)
    if payload:
        return {
            "optimized_resume": clean_resume_text(payload.get("optimized_resume", "")),
            "cover_note": str(payload.get("cover_note", "Review the generated draft before using it.")),
            "warnings": [],
        }
    return {"optimized_resume": clean_resume_text(raw), "cover_note": "Review the generated draft before using it.", "warnings": ["The model returned non-JSON output; the cleaned draft is shown."]}


def _parse_model_payload(raw: str) -> dict | None:
    candidate = raw.strip()
    candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*```$", "", candidate)
    try:
        payload = json.loads(candidate)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(candidate[start : end + 1])
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                match = re.search(r'"optimized_resume"\s*:\s*"(.*?)(?:"\s*,\s*"cover_note"|"\s*})', candidate, flags=re.DOTALL)
                if match:
                    value = match.group(1).replace("\\n", "\n").replace('\\"', '"')
                    return {"optimized_resume": value}
                return None
        return None


def clean_resume_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:text|markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    if "optimized_resume" in cleaned:
        payload = _parse_model_payload(cleaned)
        if payload and payload.get("optimized_resume"):
            cleaned = str(payload["optimized_resume"])
    return cleaned.strip()


def _demo_resume(state: ResumeState) -> str:
    return "ATS-OPTIMIZED RESUME DRAFT\n\nSUMMARY\nExperienced professional aligned to the target role, with emphasis on the capabilities identified in the job description.\n\nCORE SKILLS\n" + ", ".join(state["keywords"]) + "\n\nPROFESSIONAL EXPERIENCE\n" + state["resume_text"][:4500] + "\n\nEDUCATION\nRetain the education details from the source resume.\n\nCERTIFICATIONS\nRetain relevant certifications from the source resume."


def build_graph():
    graph = StateGraph(ResumeState)
    graph.add_node("keyword_analysis", keyword_node)
    graph.add_node("resume_optimization", optimize_node)
    graph.add_edge(START, "keyword_analysis")
    graph.add_edge("keyword_analysis", "resume_optimization")
    graph.add_edge("resume_optimization", END)
    return graph.compile()


def optimize_resume(resume_text: str, job_description: str) -> ResumeState:
    return build_graph().invoke({"resume_text": resume_text, "job_description": job_description})
