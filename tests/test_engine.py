"""Fast, dependency-light tests for the dynamic engine.

Run with:  python -m pytest -q   (or)   python tests/test_engine.py
These assert the two properties the refactor guarantees:
  1) NO hardcoded candidate data — profile is extracted from the input resume.
  2) Keywords are DYNAMIC — they come from the JD, and change with the JD.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.keywords import extract_keywords
from core.pipeline import run_career_guide
from core.profile import extract_profile
from core.scoring import score_resume

RESUME_A = """
JANE MARTINEZ
Senior Data Engineer | Cloud & Analytics
jane.martinez@example.com | +1 415 555 0110 | linkedin.com/in/janemartinez

PROFESSIONAL SUMMARY
Data engineer with 9 years building large-scale ETL pipelines on AWS and GCP,
Spark, and Airflow. Reduced pipeline runtime 40% and cut cloud spend 25%.

SKILLS
Python, SQL, Spark, Airflow, AWS, GCP, Snowflake, dbt, Kafka, Terraform

PROFESSIONAL EXPERIENCE
Senior Data Engineer, DataCo, 2019-Present
- Built streaming ingestion with Kafka processing 2M events per minute.
- Migrated 30 legacy jobs to Airflow, improving reliability 35%.

EDUCATION
BS Computer Science, State University, 2014
"""

JD_DATA = """
Key Responsibilities
Design and maintain scalable ETL pipelines using Spark and Airflow.
Build streaming data ingestion with Kafka. Optimize Snowflake warehouses.
Requirements
5+ years of data engineering with Python and SQL. Experience with dbt and
Terraform. Strong AWS cloud background.
"""

JD_PM = """
Key Responsibilities
Lead program management and create project plans, milestone tracking and
roadmap planning. Partner with product and engineering. Communicate status to
senior leadership.
Requirements
3+ years in project management and business systems analysis.
"""


def test_profile_is_extracted_not_hardcoded():
    p = extract_profile(RESUME_A)
    assert p["name"].lower().startswith("jane"), p["name"]
    assert p["contact"]["email"] == "jane.martinez@example.com"
    assert any("spark" in s.lower() or "aws" in s.lower() for s in p["skills"])
    # The candidate's name must never leak into skills.
    assert not any(tok in {"jane", "martinez"} for s in p["skills"] for tok in s.lower().split())
    print("PASS: profile extracted dynamically ->", p["name"], p["contact"]["email"])


def test_keywords_are_dynamic():
    kw_data = set(k.lower() for k in extract_keywords(JD_DATA))
    kw_pm = set(k.lower() for k in extract_keywords(JD_PM))
    assert kw_data != kw_pm, "keywords should differ per JD"
    assert any("spark" in k or "airflow" in k or "kafka" in k for k in kw_data), kw_data
    assert any("program management" in k or "project" in k for k in kw_pm), kw_pm
    print("PASS: keywords differ per JD")
    print("  data JD:", sorted(list(kw_data))[:6])
    print("  pm   JD:", sorted(list(kw_pm))[:6])


def test_relevant_resume_scores_higher_than_irrelevant():
    aligned = score_resume(RESUME_A, JD_DATA)["score"]     # data resume vs data JD
    misaligned = score_resume(RESUME_A, JD_PM)["score"]     # data resume vs PM JD
    assert aligned > misaligned, (aligned, misaligned)
    print(f"PASS: aligned={aligned} > misaligned={misaligned}")


def test_pipeline_populates_all_tabs():
    res = run_career_guide(resume_text=RESUME_A, job_description=JD_DATA)
    for tab in ["linkedin_optimization", "naukri_optimization", "interview_kit", "career_roadmap"]:
        assert res[tab], f"{tab} empty"
    assert res["optimized_resume"].strip()
    assert res["score_after"] >= res["score_before"]
    print(f"PASS: all tabs populated; score {res['score_before']} -> {res['score_after']}")


if __name__ == "__main__":
    test_profile_is_extracted_not_hardcoded()
    test_keywords_are_dynamic()
    test_relevant_resume_scores_higher_than_irrelevant()
    test_pipeline_populates_all_tabs()
    print("\nALL TESTS PASSED ✅")
