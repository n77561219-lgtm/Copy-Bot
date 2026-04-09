import json
from bot.llm import chat, SONNET

_LENGTH_HINTS = {
    "short":  "Длина поста: КОРОТКИЙ — строго 50-80 слов. Только суть, ноль вступлений.",
    "medium": "Длина поста: СТАНДАРТНАЯ — 100-200 слов.",
    "long":   "Длина поста: РАЗВЁРНУТЫЙ — 200-350 слов. Добавь историю, пример или аналогию.",
}

_PLATFORM_RULES = {
    "telegram": """\
ПЛАТФОРМА: Telegram-канал
- Форматирование: можно использовать **жирный** и _курсив_ (Markdown) там где уместно
- Эмодзи: 2-4 на весь пост, только там где усиливают смысл
- Хэштеги: только если автор их использует в профиле стиля
- Структура: крючок → тело → вывод/призыв""",

    "vk": """\
ПЛАТФОРМА: ВКонтакте
- Форматирование: ТОЛЬКО простой текст — никакого Markdown (**жирный**, _курсив_ не работают во ВКонтакте)
- Абзацы разделяй пустой строкой (Enter×2)
- Эмодзи: умеренно, 1-3 на пост — меньше чем в Telegram
- Хэштеги: ОБЯЗАТЕЛЬНО добавь 3-5 релевантных хэштегов в самом конце поста (#ниша #тема #ключевоеслово)
- Длина: оптимально 150-300 слов — ВК-аудитория предпочитает средний объём
- Стиль: чуть более разговорный и живой, без излишней «экспертности»""",

    "max": """\
ПЛАТФОРМА: Мессенджер MAX
- Форматирование: поддерживается базовый Markdown (жирный, курсив) — используй умеренно
- Эмодзи: 1-3 на пост, без перегруза
- Длина: КОМПАКТНО — 80-180 слов. Аудитория MAX читает с телефона, ценит краткость
- Тон: живой и разговорный, как личное сообщение другу-эксперту
- Хэштеги: не нужны""",
}


def _system_prompt(style_profile: dict, length: str = "medium", platform: str = "telegram") -> str:
    profile_str = json.dumps(style_profile, ensure_ascii=False, indent=2)
    length_rule = _LENGTH_HINTS.get(length, _LENGTH_HINTS["medium"])
    platform_rules = _PLATFORM_RULES.get(platform, _PLATFORM_RULES["telegram"])
    return f"""\
Ты — копирайтер. Пишешь СТРОГО в стиле автора по профилю, адаптируя под нужную платформу.

ПРОФИЛЬ СТИЛЯ:
{profile_str}

{platform_rules}

ПРАВИЛА:
1. Лексика, тон и структура — точно из профиля стиля
2. {length_rule}
3. Первое предложение — крючок, сразу в суть
4. Запрещённые слова и antipatterns из профиля — никогда не используй
5. Между смысловыми абзацами — пустая строка (\\n\\n)
6. Не используй буллет-списки если это не стиль автора
7. Верни ТОЛЬКО текст поста, без комментариев и пояснений
"""


async def run_copywriter(
    topic: str,
    style_profile: dict,
    research: str = "",
    feedback: str = "",
    previous_draft: str = "",
    post_type: str = "мнение",
    length: str = "medium",
    platform: str = "telegram",
    user_id: int | None = None,
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
            {"role": "system", "content": _system_prompt(style_profile, length, platform)},
            {"role": "user", "content": "\n".join(parts)},
        ],
        temperature=0.75,
        max_tokens=1000,
        user_id=user_id,
        agent="copywriter",
    )
