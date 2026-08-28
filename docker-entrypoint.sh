#!/usr/bin/env bash
# Launch either the API or the UI based on $SERVICE (default: api).
set -euo pipefail

SERVICE="${SERVICE:-api}"
PORT="${PORT:-8000}"

if [[ "$SERVICE" == "ui" ]]; then
  echo "Starting Streamlit UI on port ${PORT} (API at ${RESUME_API_URL:-unset})"
  exec streamlit run app.py \
    --server.port "${PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
else
  echo "Starting FastAPI (uvicorn) on port ${PORT}"
  exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT}"
fi
