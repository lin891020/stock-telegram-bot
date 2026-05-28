import anthropic as _anthropic
from openai import OpenAI
from bot.config import ANTHROPIC_API_KEY, GITHUB_TOKEN, LLM_PROVIDER

# Use Sonnet for deep analysis, Haiku for conversational finance coach
ANTHROPIC_ANALYSIS_MODEL = "claude-sonnet-4-6"
ANTHROPIC_CHAT_MODEL = "claude-haiku-4-5-20251001"
GITHUB_MODEL = "gpt-4o-mini"
GITHUB_BASE_URL = "https://models.inference.ai.azure.com"

# Alias for patching in tests
anthropic = _anthropic


def call_llm(system: str, user: str, model: str = ANTHROPIC_ANALYSIS_MODEL) -> str:
    """Synchronous LLM call. Returns full response text.

    In async handlers, wrap with: await asyncio.to_thread(call_llm, system, user)
    """
    if LLM_PROVIDER == "anthropic":
        return _call_anthropic(system, user, model)
    return _call_github(system, user)


def _call_anthropic(system: str, user: str, model: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def _call_github(system: str, user: str) -> str:
    client = OpenAI(api_key=GITHUB_TOKEN, base_url=GITHUB_BASE_URL)
    response = client.chat.completions.create(
        model=GITHUB_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""
