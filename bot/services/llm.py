import logging
from typing import NamedTuple

import httpx
import anthropic as _anthropic
from openai import OpenAI
from bot.config import ANTHROPIC_API_KEY, GEMINI_API_KEY, GITHUB_TOKEN, LLM_PROVIDER
from bot.services.settings import get_saved_model, save_model

anthropic = _anthropic
logger = logging.getLogger(__name__)

class ModelInfo(NamedTuple):
    label: str        # 按鈕上顯示的名字
    provider: str     # anthropic / gemini / github
    note: str = ""    # 選單裡的一行說明（價格、適合什麼）


# 模型代號用官方完整字串，不要自己加日期後綴（例如 claude-haiku-4-5，
# 不是 claude-haiku-4-5-20251001）——加了會變成無效代號。
AVAILABLE_MODELS: dict[str, ModelInfo] = {
    "claude-opus-5":   ModelInfo("Opus 5",   "anthropic", "最強推理｜$5 / $25 每百萬 token"),
    "claude-sonnet-5": ModelInfo("Sonnet 5", "anthropic", "高性價比｜$2 / $10（預設）"),
    "claude-haiku-4-5": ModelInfo("Haiku 4.5", "anthropic", "最便宜最快｜$1 / $5"),
    "gemini-3.5-flash": ModelInfo("Gemini 3.5 Flash", "gemini", "免費｜快速輕量"),
    "gemini-3.1-pro-preview": ModelInfo("Gemini 3.1 Pro", "gemini", "免費（限額）｜深度推理"),
    "gpt-4o-mini": ModelInfo("GPT-4o Mini", "github", "免費｜穩定備援"),
}

# 深度分析用 Sonnet 5：比舊的 Sonnet 4.6 又便宜（$2/$10 vs $3/$15）又更強，
# 換過去沒有任何取捨。要更深的推理可以用 /model 切 Opus 5（同價位但能力更高）。
ANTHROPIC_ANALYSIS_MODEL = "claude-sonnet-5"
# /finance 與 /learn 用它：對話式教練與教學內容不需要主力模型的推理深度。
# （晨報以前也走這裡，但新聞已改成只列標題、完全不呼叫 LLM。）
ANTHROPIC_CHAT_MODEL = "claude-haiku-4-5"
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


class LLMUnavailable(RuntimeError):
    """模型端的問題（額度用盡、金鑰失效、供應商當機），不是資料問題。

    分開一種例外，是因為使用者該做的事完全不同：資料抓不到「稍後再試」
    是對的，額度用盡再試一百次也一樣。實測信用額度用盡那次，畫面只寫
    「分析失敗，請稍後再試」，看不出要去儲值。
    """

    def __init__(self, reason: str, hint: str = ""):
        super().__init__(reason)
        self.reason, self.hint = reason, hint


# 供應商錯誤訊息 → 給使用者的白話。比對的是小寫後的訊息內容。
_LLM_HINTS = (
    ("credit balance", "API 額度用盡，需要儲值"),
    ("quota", "API 額度用盡或超過用量限制"),
    ("rate limit", "呼叫太頻繁，等幾分鐘再試"),
    ("authentication", "API key 無效或過期"),
    ("permission", "API key 沒有這個模型的權限"),
    ("not_found", "模型代號不存在，用 /model 換一個"),
    ("overloaded", "模型端忙碌中，稍後再試"),
)


def _describe(exc: Exception) -> str:
    text = str(exc).lower()
    for needle, hint in _LLM_HINTS:
        if needle in text:
            return hint
    return ""


def call_llm(system: str, user: str, model: str | None = None) -> str:
    """Synchronous LLM call. Uses current selected model if model is None."""
    target = model or _current_model
    info = AVAILABLE_MODELS.get(target)
    provider = info.provider if info else LLM_PROVIDER

    try:
        if provider == "anthropic":
            return _call_anthropic(system, user, target)
        if provider == "gemini":
            return _call_gemini(system, user, target)
        return _call_github(system, user)
    except LLMUnavailable:
        raise
    except Exception as exc:
        logger.error("LLM 呼叫失敗（provider=%s, model=%s）：%s", provider, target, exc)
        raise LLMUnavailable(type(exc).__name__, _describe(exc)) from exc


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
