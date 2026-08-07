import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
MAX_RESUME_BYTES = int(os.getenv("MAX_RESUME_BYTES", "8000000"))

