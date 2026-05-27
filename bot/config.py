import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value

TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.environ.get("GITHUB_REPO", "")
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "anthropic")
ALLOWED_TELEGRAM_ID: int = int(_require("ALLOWED_TELEGRAM_ID"))
