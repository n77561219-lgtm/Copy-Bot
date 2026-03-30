import json
from bot.llm import chat, SONNET

# ─── prompt for analysing raw posts ──────────────────────────────────────────
_SYSTEM = """\
Ты — аналитик авторского стиля. Изучи посты из Telegram-канала и составь профиль стиля.

Верни ТОЛЬКО валидный JSON:
{
  "vocabulary": {
    "favorite_words": ["слово1", "слово2"],
    "favorite_phrases": ["оборот1", "оборот2"],
    "forbidden_words": ["безусловно", "несомненно", "в мире где"],
    "opening_patterns": ["типичное начало1", "типичное начало2"],
    "closing_patterns": ["типичный конец1"]
  },
  "structure": {
    "avg_post_length_words": 120,
    "sentence_style": "короткие и рубленые",
    "uses_line_breaks_often": true,
    "lists_usage": "редко"
  },
  "tone": {
    "primary": "прямой",
    "secondary": "разговорный",
    "humor": "иногда",
    "swearing": "нет"
  },
  "formatting": {
    "emoji": "редко",
    "caps": "для акцента",
    "dashes": "em",
    "ellipsis": "часто"
  },
  "content_patterns": {
    "main_topics": ["тема1", "тема2"],
    "post_types": ["мнение", "кейс"],
    "typical_hook": "описание типичного первого предложения"
  },
  "antipatterns": [
    "что автор НИКОГДА не пишет — конкретно"
  ],
  "style_examples": {
    "best_opening": "лучший пример первого предложения из постов",
    "best_post_fragment": "лучший отрывок, максимально характерный для стиля"
  }
}
"""


def _select_sample(posts: list[str], max_posts: int = 80) -> list[str]:
    """Take early + middle + recent posts for a representative sample."""
    if len(posts) <= max_posts:
        return posts
    early = posts[:20]
    recent = posts[-30:]
    mid_start, mid_end = 20, len(posts) - 30
    step = max(1, (mid_end - mid_start) // 30)
    middle = posts[mid_start:mid_end:step][:30]
    seen: set[str] = set()
    result: list[str] = []
    for p in early + middle + recent:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result[:max_posts]


# ─── prompt for a structured Tone-of-Voice document ─────────────────────────
_SYSTEM_TOV = """\
Тебе передан структурированный документ Tone of Voice автора.
Преобразуй его в профиль стиля в формате JSON — точно, без выдумки.
Используй только то, что написано в документе. Никаких добавлений.

Верни ТОЛЬКО валидный JSON той же структуры:
{
  "vocabulary": {
    "favorite_words": [],
    "favorite_phrases": [],
    "forbidden_words": [],
    "opening_patterns": [],
    "closing_patterns": []
  },
  "structure": {
    "avg_post_length_words": 120,
    "sentence_style": "",
    "uses_line_breaks_often": true,
    "lists_usage": "редко"
  },
  "tone": {
    "primary": "",
    "secondary": "",
    "humor": "",
    "swearing": "нет"
  },
  "formatting": {
    "emoji": "нет",
    "caps": "нет",
    "dashes": "em",
    "ellipsis": "редко"
  },
  "content_patterns": {
    "main_topics": [],
    "post_types": [],
    "typical_hook": ""
  },
  "antipatterns": [],
  "style_examples": {
    "best_opening": "",
    "best_post_fragment": ""
  }
}
"""


def _is_tov_document(content: str) -> bool:
    """Detect if the file is a structured Tone of Voice doc rather than raw posts."""
    markers = ["tone of voice", "тон голоса", "слова-маркеры", "запрещённые слова",
               "антипаттерн", "правила написания", "мой стиль"]
    lower = content.lower()
    return sum(1 for m in markers if m in lower) >= 2


async def run_style_analyst_from_doc(doc_content: str) -> dict:
    """Build style profile directly from a structured ToV document."""
    raw = await chat(
        model=SONNET,
        messages=[
            {"role": "system", "content": _SYSTEM_TOV},
            {"role": "user", "content": f"Документ Tone of Voice:\n\n{doc_content}"},
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"raw_analysis": raw, "antipatterns": [], "vocabulary": {}, "tone": {}}


async def run_style_analyst(posts: list[str]) -> dict:
    sample = _select_sample(posts)
    posts_text = "\n\n---\n\n".join(
        f"[Пост {i + 1}]\n{post}" for i, post in enumerate(sample)
    )
    raw = await chat(
        model=SONNET,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Посты автора:\n\n{posts_text}"},
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"raw_analysis": raw, "antipatterns": [], "vocabulary": {}, "tone": {}}
