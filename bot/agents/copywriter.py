import json
from bot.llm import chat, SONNET

_LENGTH_HINTS = {
    "short":  "Длина поста: КОРОТКИЙ — строго 50-80 слов. Только суть, ноль вступлений.",
    "medium": "Длина поста: СТАНДАРТНАЯ — 100-200 слов.",
    "long":   "Длина поста: РАЗВЁРНУТЫЙ — 200-350 слов. Добавь историю, пример или аналогию.",
}


def _system_prompt(style_profile: dict, length: str = "medium") -> str:
    profile_str = json.dumps(style_profile, ensure_ascii=False, indent=2)
    length_rule = _LENGTH_HINTS.get(length, _LENGTH_HINTS["medium"])
    return f"""\
Ты — копирайтер Telegram-канала. Пишешь СТРОГО в стиле автора по профилю.

ПРОФИЛЬ СТИЛЯ:
{profile_str}

ПРАВИЛА:
1. Лексика, тон и структура — точно из профиля
2. {length_rule}
3. Первое предложение — крючок, сразу в суть
4. Запрещённые слова и antipatterns — никогда не используй
5. Хэштеги — только если автор их использует в профиле
6. Верни ТОЛЬКО текст поста, без комментариев и пояснений
"""


async def run_copywriter(
    topic: str,
    style_profile: dict,
    research: str = "",
    feedback: str = "",
    previous_draft: str = "",
    post_type: str = "мнение",
    length: str = "medium",
) -> str:
    parts = [f"Напиши пост на тему: {topic}"]
    if post_type:
        parts.append(f"Формат: {post_type}")
    if research:
        parts.append(f"\nФактура:\n{research}")
    if previous_draft:
        parts.append(f"\nПредыдущий вариант (нужно улучшить):\n{previous_draft}")
    if feedback:
        parts.append(f"\nЗамечания редактора:\n{feedback}")

    return await chat(
        model=SONNET,
        messages=[
            {"role": "system", "content": _system_prompt(style_profile, length)},
            {"role": "user", "content": "\n".join(parts)},
        ],
        temperature=0.75,
        max_tokens=1000,
    )
