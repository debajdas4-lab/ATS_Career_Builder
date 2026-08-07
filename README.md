# Resume Optimizer

An end-to-end resume optimization application that accepts a PDF, DOCX or text resume and a job description. It extracts ATS-oriented keywords, scores transparent keyword/section coverage, and creates an ATS-readable resume draft with Groq through a LangGraph workflow.

## Architecture

```text
Streamlit Cloud → FastAPI on Render → LangGraph
                                      ├─ MCP keyword extraction tool
                                      ├─ ATS scoring tool
                                      └─ Groq resume rewriting node
```

The MCP server in `mcp_server.py` exposes `extract_job_keywords` and `calculate_ats_score` for future MCP clients. The same tool logic is used locally by the LangGraph nodes so the application remains deployable without requiring a separate MCP server process.

## Local run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `GROQ_API_KEY` in `.env`, then run the API and UI in separate terminals:

```powershell
uvicorn api.main:app --reload --port 8000
streamlit run app.py
```

Set `DEMO_MODE=true` to test the upload and scoring flow without calling Groq. Demo mode does not provide a production-quality rewrite; it is only a safe local smoke test.

## Deployment

1. Create a separate GitHub repository, for example `resume-optimizer`.
2. Upload the contents of this folder to the repository root.
3. In Render, create a Web Service from the repository. The included `render.yaml` uses FastAPI and Uvicorn.
4. Add `GROQ_API_KEY` as a Render secret and deploy. Confirm the generated URL returns the health response at `/` and API documentation at `/docs`.
5. In Streamlit Community Cloud, deploy `app.py` from the same repository or a separate frontend repository.
6. Add this Streamlit secret:

```toml
RESUME_API_URL = "https://your-render-service.onrender.com"
```

## Responsible-use guardrails

- The model is instructed not to invent jobs, dates, education, metrics or skills.
- The interface explicitly asks the user to verify every claim.
- Keyword scoring is transparent and is not presented as a hiring prediction.
- Do not upload confidential resumes unless your deployment and data-retention controls are appropriate for that information.

