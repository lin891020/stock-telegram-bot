import httpx
import anthropic as _anthropic
from openai import OpenAI
from bot.config import ANTHROPIC_API_KEY, GEMINI_API_KEY, GITHUB_TOKEN, LLM_PROVIDER

anthropic = _anthropic

# Model registry: key → (display_name, provider)
AVAILABLE_MODELS: dict[str, tuple[str, str]] = {
    "claude-opus-4-8":            ("Opus 4.8（付費，旗艦）",           "anthropic"),
    "claude-sonnet-4-6":          ("Sonnet 4.6（付費，最強）",        "anthropic"),
    "gemini-3.5-flash":           ("Gemini 3.5 Flash（免費，最強）",   "gemini"),
    "gemini-3.1-pro-preview":     ("Gemini 3.1 Pro（免費，限額）",    "gemini"),
    "gpt-4o-mini":               ("GPT-4o Mini（免費，穩定）",       "github"),
}

ANTHROPIC_ANALYSIS_MODEL = "claude-sonnet-4-6"
ANTHROPIC_CHAT_MODEL = "claude-haiku-4-5-20251001"
GITHUB_MODEL = "gpt-4o-mini"
GITHUB_BASE_URL = "https://models.inference.ai.azure.com"

_current_model: str = ANTHROPIC_ANALYSIS_MODEL


def get_current_model() -> str:
    return _current_model


def set_current_model(model_key: str) -> None:
    global _current_model
    if model_key not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown model: {model_key}")
    _current_model = model_key


def call_llm(system: str, user: str, model: str | None = None) -> str:
    """Synchronous LLM call. Uses current selected model if model is None."""
    target = model or _current_model
    _, provider = AVAILABLE_MODELS.get(target, ("", LLM_PROVIDER))

    if provider == "anthropic":
        return _call_anthropic(system, user, target)
    if provider == "gemini":
        return _call_gemini(system, user, target)
    return _call_github(system, user)


def _call_anthropic(system: str, user: str, model: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def _call_gemini(system: str, user: str, model: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 未設定，請至 .env 填入 API key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": 8192},
    }
    resp = httpx.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=120.0)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_github(system: str, user: str) -> str:
    client = OpenAI(api_key=GITHUB_TOKEN, base_url=GITHUB_BASE_URL)
    response = client.chat.completions.create(
        model=GITHUB_MODEL,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""
