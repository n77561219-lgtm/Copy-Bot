import json
from typing import Literal
from bot.llm import chat, SONNET

EditMode = Literal["shorter", "longer", "punchier", "human", "grammar", "custom"]

_MODE_INSTRUCTIONS: dict[str, str] = {
    "shorter":  "Сократи текст на 30-40% без потери смысла. Убери всё лишнее, оставь суть и удар.",
    "longer":   "Расширь текст на 30-40%: добавь конкретный пример, деталь или аналогию в стиле автора. Не лей воду.",
    "punchier": "Сделай текст хлёстче: усиль первое предложение, убери мягкие формулировки, добавь конкретику и остроту.",
    "human":    "Убери AI-паттерны, сделай живым. Текст должен звучать как человек — с паузами, разговорными словами, честностью.",
    "grammar":  "Исправь грамматику, пунктуацию и опечатки. Стиль и содержание не трогай — только техническая правка.",
}


def _system_prompt(style_profile: dict, mode: EditMode, custom_instruction: str) -> str:
    profile_brief = json.dumps(
        {
            "vocabulary": style_profile.get("vocabulary", {}),
            "tone": style_profile.get("tone", {}),
            "antipatterns": style_profile.get("antipatterns", []),
        },
        ensure_ascii=False,
        indent=2,
    )
    instruction = _MODE_INSTRUCTIONS.get(mode, custom_instruction)
    return f"""\
Ты — редактор Telegram-постов. Правишь текст строго в стиле автора.

ПРОФИЛЬ СТИЛЯ:
{profile_brief}

ЗАДАЧА: {instruction}

Верни ТОЛЬКО отредактированный текст поста, без пояснений.
"""


async def run_editor(
    post: str,
    style_profile: dict,
    mode: EditMode = "human",
    custom_instruction: str = "",
    issues: list[str] | None = None,
    user_id: int | None = None,
) -> str:
    user_content = f"Текст для правки:\n{post}"
    if issues:
        user_content += "\n\nЗамечания:\n" + "\n".join(f"- {i}" for i in issues)

    return await chat(
        model=SONNET,
        messages=[
            {"role": "system", "content": _system_prompt(style_profile, mode, custom_instruction)},
            {"role": "user", "content": user_content},
        ],
        temperature=0.4,
        max_tokens=1000,
        user_id=user_id,
        agent="editor",
    )
