import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MAX_OUTPUT_TOKENS = int(os.getenv("GROQ_MAX_OUTPUT_TOKENS", "1800"))
GROQ_TPM_SAFE_MODE = os.getenv("GROQ_TPM_SAFE_MODE", "true").lower() == "true"
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
MAX_RESUME_BYTES = int(os.getenv("MAX_RESUME_BYTES", "8000000"))
ENABLE_COMPANY_RESEARCH = os.getenv("ENABLE_COMPANY_RESEARCH", "false").lower() == "true"
