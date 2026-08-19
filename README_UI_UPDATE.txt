ATS Career Builder V3 - Restored Premium UI

FILES
- app.py: drop-in replacement for the simplified V3 Streamlit app
- ats_career_guide_banner.png: required hero banner asset

INSTALL
1. Stop Streamlit with Ctrl+C.
2. Back up the existing V3 app.py.
3. Copy both files into the root ATS_Career_Builder_V3 folder.
4. Confirm the FastAPI V3 backend is running:
   uvicorn api.main:app --reload --port 8000
5. Start Streamlit:
   streamlit run app.py

The restored app retains the original navy/violet sidebar, banner, typography,
job URL and pasted-JD workflow, company/market inputs, results tabs, DOCX export,
and V3 multi-agent metrics. It calls POST /v3/career-guide.
