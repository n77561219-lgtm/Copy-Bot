import json
from typing import TypedDict, Literal
from bot.llm import chat, HAIKU


class CriticResult(TypedDict):
    score: float               # итоговый 1-10 (среднее трёх шкал)
    score_style: int           # стиль 1-10
    score_content: int         # контент/смысл 1-10
    score_engagement: int      # вовлечение/крючок 1-10
    verdict: Literal["APPROVE", "REVISE"]
    tip: str                   # одна конкретная подсказка для улучшения
    issues: list[str]
    suggestions: list[str]


_SYSTEM = """\
Ты — строгий редактор Telegram-канала. Оцени пост по трём шкалам.

Верни ТОЛЬКО валидный JSON:
{
  "score_style": 8,
  "score_content": 7,
  "score_engagement": 9,
  "tip": "Одна конкретная подсказка как улучшить пост",
  "issues": ["проблема если есть"],
  "suggestions": ["правка если есть"]
}

Шкалы (каждая 1-10):
- score_style: соответствие стилю автора (лексика, тон, антипаттерны)
- score_content: качество контента (конкретика, польза, отсутствие воды)
- score_engagement: вовлечение (крючок в первом предложении, хочется дочитать)

В tip — одно конкретное наблюдение, например: «Аналогия хороша, но можно развить дальше».
Без tip если всё хорошо.
"""


async def run_critic(post: str, style_profile: dict, user_id: int | None = None) -> CriticResult:
    profile_brief = json.dumps(
        {
            "tone": style_profile.get("tone", {}),
            "antipatterns": style_profile.get("antipatterns", []),
            "forbidden_words": style_profile.get("vocabulary", {}).get("forbidden_words", []),
        },
        ensure_ascii=False,
    )
    raw = await chat(
        model=HAIKU,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Профиль:\n{profile_brief}\n\nПост:\n{post}"},
        ],
        temperature=0.0,
        max_tokens=500,
        user_id=user_id,
        agent="critic",
    )
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        s = int(data.get("score_style", 7))
        c = int(data.get("score_content", 7))
        e = int(data.get("score_engagement", 7))
        avg = round((s + c + e) / 3, 1)
        return CriticResult(
            score=avg,
            score_style=s,
            score_content=c,
            score_engagement=e,
            verdict="APPROVE" if avg >= 7 else "REVISE",
            tip=data.get("tip", ""),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
        )
    except (json.JSONDecodeError, ValueError):
        return CriticResult(
            score=5.0, score_style=5, score_content=5, score_engagement=5,
            verdict="REVISE", tip="", issues=["Не удалось оценить"], suggestions=[],
        )
