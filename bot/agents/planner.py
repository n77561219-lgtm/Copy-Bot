import json
from datetime import datetime, timedelta
from bot.llm import chat, SONNET

_SYSTEM = """\
Ты — контент-планер Telegram-канала. Создай разнообразный контент-план.

Верни ТОЛЬКО валидный JSON — список объектов:
[
  {
    "date": "2024-01-15",
    "topic": "Конкретная тема поста",
    "format": "мнение",
    "angle": "Угол подачи — что именно сказать об этой теме"
  }
]

Форматы для баланса: мнение, кейс, лайфхак, наблюдение, провокация, личный опыт

Требования:
- Конкретные темы, не абстрактные
- Разные форматы (не несколько одинаковых подряд)
- Провокационный угол хотя бы у 2 постов
- Темы соответствуют тематике канала
"""


async def run_planner(
    days: int,
    style_profile: dict,
    recent_topics: list[str] | None = None,
    user_id: int | None = None,
) -> list[dict]:
    main_topics = style_profile.get("content_patterns", {}).get("main_topics", [])
    post_types = style_profile.get("content_patterns", {}).get("post_types", [])

    parts = [f"Создай контент-план на {days} дней, начиная с сегодня."]
    if main_topics:
        parts.append(f"Тематика канала: {', '.join(main_topics)}")
    if post_types:
        parts.append(f"Типичные форматы автора: {', '.join(post_types)}")
    if recent_topics:
        parts.append(f"Недавние темы (не повторяй): {', '.join(recent_topics[-5:])}")

    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    parts.append(f"Даты: {', '.join(dates)}")

    raw = await chat(
        model=SONNET,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "\n".join(parts)},
        ],
        temperature=0.6,
        max_tokens=2000,
        user_id=user_id,
        agent="planner",
    )
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(clean)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []
