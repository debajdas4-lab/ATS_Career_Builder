from core.career_tools import build_job_spec,score_fit
JD="Director Technical Program Manager. Lead cross-functional Product and Engineering programs, roadmap alignment, technical risk, distributed systems, cloud technologies, operational excellence and mentoring."
RESUME="Technical Program Manager leading global cross-functional teams, program governance, risk mitigation, PaaS cloud transition, architecture and operational excellence."
def test_score_bounds():
    out=score_fit(RESUME,build_job_spec(JD));assert 0<=out["score"]<=100
def test_truthful_gap():
    out=score_fit(RESUME,build_job_spec(JD));assert "distributed systems" in out["missing_keywords"]
