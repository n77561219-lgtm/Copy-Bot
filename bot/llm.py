import asyncio
import logging
from openai import AsyncOpenAI
from bot.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/copy-bot",
                "X-Title": "Telegram Copy Bot",
            },
        )
    return _client


async def chat(
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2000,
    user_id: int | None = None,
    agent: str = "",
) -> str:
    response = await get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content.strip()

    usage = response.usage
    if usage and user_id is not None:
        asyncio.create_task(_log(user_id, agent, model, usage.prompt_tokens, usage.completion_tokens))

    return text


async def _log(user_id: int, agent: str, model: str, inp: int, out: int) -> None:
    try:
        from bot.database import log_tokens
        await log_tokens(user_id, agent, model, inp, out)
    except Exception as e:
        logger.debug("token_log failed: %s", e)


# Shortcuts
HAIKU  = settings.model_haiku
SONNET = settings.model_sonnet
TRENDS = settings.model_trends
