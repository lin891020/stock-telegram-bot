import pytest
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GITHUB_TOKEN", "test_gh_token")
os.environ.setdefault("GITHUB_REPO", "test/repo")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ALLOWED_TELEGRAM_ID", "123456789")
