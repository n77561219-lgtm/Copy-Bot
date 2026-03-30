"""Trend scouting agent — uses Perplexity Sonar (live web search) via OpenRouter."""
import json

from bot.llm import chat, TRENDS

_SYSTEM = """\
You are a content trend analyst with live internet access. Your task: find 5 trending topics
RIGHT NOW relevant to the author's niche, and return them as a raw JSON array.

Return ONLY a valid JSON array. No prose, no markdown, no code fences. Exactly this schema:
[
  {"title": "Short trend name in Russian (max 8 words)", "angle": "One sentence posting angle in Russian"},
  ...
]

Rules:
- All text in Russian
- title: concise, specific, real trend from last 7 days
- angle: one sentence — what to say about this trend, the hook
- Exactly 5 items
- No markdown, no wrapping text, just the JSON array
"""


async def run_trends(main_topics: list[str]) -> list[dict]:
    """
    Fetch real trending topics via Perplexity Sonar web search.
    Returns list of 5 dicts: [{"title": str, "angle": str}, ...]
    """
    niche = ", ".join(main_topics) if main_topics else "AI, технологии, малый бизнес, маркетинг"

    raw = await chat(
        model=TRENDS,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Ниша автора: {niche}\n\nНайди 5 актуальных трендов прямо сейчас."},
        ],
        temperature=0.0,
        max_tokens=600,
    )

    # Strip markdown fences if model wraps anyway
    clean = raw.strip()
    # Find JSON array bounds robustly
    start = clean.find("[")
    end = clean.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"JSON array not found in response: {clean[:200]}")
    clean = clean[start:end]

    try:
        result = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse trends JSON: {e}. Raw: {clean[:200]}")

    trends = [
        {"title": str(t.get("title", "")), "angle": str(t.get("angle", ""))}
        for t in result[:5]
        if isinstance(t, dict) and t.get("title")
    ]
    if not trends:
        raise ValueError("Trends list is empty after parsing")
    return trends
