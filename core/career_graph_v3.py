from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .agents.nodes import ats_agent, candidate_agent, interview_agent, job_agent, linkedin_agent, local_strategy_agent, naukri_agent, research_agent, resume_agent, roadmap_agent
from .models import CareerGuideState


def route_after_resume(state):
    return "research" if state.get("analysis_mode", "Fast Resume") == "Complete Career Guide" else "end"


def build_career_graph_v3():
    graph = StateGraph(CareerGuideState)
    for name, node in [("candidate", candidate_agent), ("job", job_agent), ("ats", ats_agent), ("strategy", local_strategy_agent), ("resume", resume_agent), ("research", research_agent), ("linkedin", linkedin_agent), ("naukri", naukri_agent), ("interview", interview_agent), ("roadmap", roadmap_agent)]:
        graph.add_node(name, node)
    graph.add_edge(START, "candidate")
    graph.add_edge("candidate", "job")
    graph.add_edge("job", "ats")
    graph.add_edge("ats", "strategy")
    graph.add_edge("strategy", "resume")
    graph.add_conditional_edges("resume", route_after_resume, {"research": "research", "end": END})
    graph.add_edge("research", "linkedin")
    graph.add_edge("linkedin", "naukri")
    graph.add_edge("naukri", "interview")
    graph.add_edge("interview", "roadmap")
    graph.add_edge("roadmap", END)
    return graph.compile()


def run_career_guide_v3(**kwargs: Any) -> CareerGuideState:
    return build_career_graph_v3().invoke(kwargs)
