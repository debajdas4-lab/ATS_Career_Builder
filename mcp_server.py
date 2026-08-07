from mcp.server.fastmcp import FastMCP

from core.mcp_tools import extract_keywords, score_resume

mcp = FastMCP("resume-optimizer-tools")


@mcp.tool()
def extract_job_keywords(job_description: str) -> list[str]:
    """Extract recruiter and ATS-oriented keywords from a job description."""
    return extract_keywords(job_description)


@mcp.tool()
def calculate_ats_score(resume_text: str, keywords: list[str]) -> dict:
    """Calculate a transparent keyword and section coverage score."""
    return score_resume(resume_text, keywords)


if __name__ == "__main__":
    mcp.run(transport="stdio")

