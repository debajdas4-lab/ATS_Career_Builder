from mcp.server.fastmcp import FastMCP

from core.career_tools import build_job_spec, gap_analysis, score_fit
from core.evidence import extract_candidate_profile

mcp = FastMCP("ats-career-builder-v3")


@mcp.tool()
def analyze_job_description(job_description: str) -> dict:
    return build_job_spec(job_description)


@mcp.tool()
def calculate_semantic_ats_score(resume_text: str, job_description: str) -> dict:
    return score_fit(resume_text, build_job_spec(job_description))


@mcp.tool()
def analyze_candidate_profile(resume_text: str, linkedin_profile: str = "", naukri_profile: str = "") -> dict:
    return extract_candidate_profile(resume_text, linkedin_profile, naukri_profile)


@mcp.tool()
def calculate_career_gaps(resume_text: str, job_description: str) -> dict:
    return gap_analysis(resume_text, build_job_spec(job_description))


if __name__ == "__main__":
    mcp.run(transport="stdio")
