import json
from typing import TypedDict, Literal
from bot.llm import chat, HAIKU

Intent = Literal["WRITE_POST", "EDIT_POST", "CONTENT_PLAN", "SHOW_PLAN", "HELP", "UNKNOWN"]


class DispatchResult(TypedDict):
    intent: Intent
    topic: str   # for WRITE_POST
    text: str    # for EDIT_POST
    days: int    # for CONTENT_PLAN


_SYSTEM = """\
Ты — диспетчер Telegram-бота для копирайтера. Классифицируй намерение пользователя.

Возможные intent:
- WRITE_POST   — написать новый пост (извлеки тему в topic)
- EDIT_POST    — отредактировать присланный текст (сам текст в text)
- CONTENT_PLAN — создать контент-план (количество дней в days, по умолчанию 7)
- SHOW_PLAN    — показать текущий контент-план
- HELP         — помощь / список команд
- UNKNOWN      — не понял запрос

Верни ТОЛЬКО валидный JSON без markdown-блоков:
{"intent": "...", "topic": "...", "text": "...", "days": 7}
"""


async def run_dispatcher(user_message: str, user_id: int | None = None) -> DispatchResult:
    raw = await chat(
        model=HAIKU,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=300,
        user_id=user_id,
        agent="dispatcher",
    )
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        return DispatchResult(
            intent=data.get("intent", "UNKNOWN"),
            topic=data.get("topic", ""),
            text=data.get("text", ""),
            days=int(data.get("days", 7)),
        )
    except (json.JSONDecodeError, ValueError, KeyError):
        return DispatchResult(intent="UNKNOWN", topic="", text="", days=7)
