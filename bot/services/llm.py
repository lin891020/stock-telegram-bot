import logging

import httpx
import anthropic as _anthropic
from openai import OpenAI
from bot.config import ANTHROPIC_API_KEY, GEMINI_API_KEY, GITHUB_TOKEN, LLM_PROVIDER
from bot.services.settings import get_saved_model, save_model

anthropic = _anthropic
logger = logging.getLogger(__name__)

# Model registry: key → (display_name, provider)
AVAILABLE_MODELS: dict[str, tuple[str, str]] = {
    "claude-opus-4-8":            ("Opus 4.8（付費，最強推理）",       "anthropic"),
    "claude-sonnet-4-6":          ("Sonnet 4.6（付費，高性價比）",     "anthropic"),
    "claude-haiku-4-5-20251001":  ("Haiku 4.5（付費，最便宜）",       "anthropic"),
    "gemini-3.5-flash":           ("Gemini 3.5 Flash（免費，快速）",   "gemini"),
    "gemini-3.1-pro-preview":     ("Gemini 3.1 Pro（免費，深度）",    "gemini"),
    "gpt-4o-mini":               ("GPT-4o Mini（免費，穩定）",       "github"),
}

ANTHROPIC_ANALYSIS_MODEL = "claude-sonnet-4-6"
ANTHROPIC_CHAT_MODEL = "claude-haiku-4-5-20251001"
GITHUB_MODEL = "gpt-4o-mini"
GITHUB_BASE_URL = "https://models.inference.ai.azure.com"

# 完整財報解讀實測約 6,000 中文字元（≈5K tokens），8192 的餘裕太薄，
# 而且截斷是無聲的——只會看到報告斷在半句。
MAX_TOKENS = 16000

# Client 做成單例：每次呼叫重建會連同 httpx 連線池與 TLS 握手一起重來。
_anthropic_client = None
_github_client = None

# Restore the last /model selection across restarts
_saved = get_saved_model()
_current_model: str = _saved if _saved in AVAILABLE_MODELS else ANTHROPIC_ANALYSIS_MODEL


def get_current_model() -> str:
    return _current_model


def set_current_model(model_key: str) -> None:
    global _current_model
    if model_key not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown model: {model_key}")
    _current_model = model_key
    save_model(model_key)


def call_llm(system: str, user: str, model: str | None = None) -> str:
    """Synchronous LLM call. Uses current selected model if model is None."""
    target = model or _current_model
    _, provider = AVAILABLE_MODELS.get(target, ("", LLM_PROVIDER))

    if provider == "anthropic":
        return _call_anthropic(system, user, target)
    if provider == "gemini":
        return _call_gemini(system, user, target)
    return _call_github(system, user)


def call_llm_light(system: str, user: str) -> str:
    """低難度任務（新聞摘要、收盤速報等）。

    Anthropic provider 時固定用 Haiku 省成本（每天推播都會呼叫）；
    免費 provider（Gemini/GitHub）則照用目前選的模型。
    """
    _, provider = AVAILABLE_MODELS.get(_current_model, ("", LLM_PROVIDER))
    if provider == "anthropic":
        return _call_anthropic(system, user, ANTHROPIC_CHAT_MODEL)
    return call_llm(system, user)


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _text_from(response) -> str:
    """把回應中的文字區塊接起來。

    content 是一串區塊，不保證第一個就是文字——啟用 thinking 的模型
    會把 thinking 區塊排在前面，直接取 content[0].text 會炸。
    """
    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    if response.stop_reason == "max_tokens":
        logger.warning("LLM 回應被 max_tokens 截斷（model=%s）", response.model)
    return "".join(parts)


def _call_anthropic(system: str, user: str, model: str) -> str:
    # 這裡刻意不加 cache_control：system prompt 只有 25-50 tokens，
    # 遠低於 prompt caching 的最低門檻（1024 tokens），加了不會報錯也不會生效。
    response = _get_anthropic_client().messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _text_from(response)


def _call_gemini(system: str, user: str, model: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 未設定，請至 .env 填入 API key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": MAX_TOKENS},
    }
    resp = httpx.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=120.0)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_github(system: str, user: str) -> str:
    global _github_client
    if _github_client is None:
        _github_client = OpenAI(api_key=GITHUB_TOKEN, base_url=GITHUB_BASE_URL)
    response = _github_client.chat.completions.create(
        model=GITHUB_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""
