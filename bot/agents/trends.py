"""Trend scouting agent.

Primary source: pytrends (Google Trends, free, no API key).
Fallback: Perplexity Sonar via OpenRouter (if pytrends fails or returns nothing).

Flow:
  1. Translate user's niche keywords to English (Haiku, fast)
  2. Fetch rising queries from Google Trends via pytrends (geo=RU, 7 days)
  3. Pass raw rising queries to Haiku → format as 5 structured trends
  4. On any pytrends failure → fall back to Perplexity Sonar
"""
import asyncio
import json
import logging
import time

from bot.llm import chat, HAIKU, TRENDS

logger = logging.getLogger(__name__)

# ── Perplexity fallback (original implementation) ────────────────────────────

_FALLBACK_SYSTEM = """\
You are a content trend analyst with live internet access. Find 5 trending topics
RIGHT NOW relevant to the author's niche, and return them as a raw JSON array.
Return ONLY a valid JSON array. No prose, no markdown, no code fences. Schema:
[
  {"title": "Short trend name in Russian (max 8 words)", "angle": "One sentence posting angle in Russian"},
  ...
]
Rules: All text in Russian. title: real trend from last 7 days. Exactly 5 items.
"""


async def _run_perplexity_fallback(niche: str) -> list[dict]:
    raw = await chat(
        model=TRENDS,
        messages=[
            {"role": "system", "content": _FALLBACK_SYSTEM},
            {"role": "user", "content": f"Ниша автора: {niche}\n\nНайди 5 актуальных трендов прямо сейчас."},
        ],
        temperature=0.0,
        max_tokens=600,
    )
    clean = raw.strip()
    start, end = clean.find("["), clean.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"JSON not found in Perplexity response: {clean[:200]}")
    result = json.loads(clean[start:end])
    return [
        {"title": str(t.get("title", "")), "angle": str(t.get("angle", ""))}
        for t in result[:5]
        if isinstance(t, dict) and t.get("title")
    ]


# ── pytrends (Google Trends) ──────────────────────────────────────────────────

async def _translate_to_english(topics: list[str]) -> list[str]:
    """Translate Russian niche topics to English for pytrends."""
    raw = await chat(
        model=HAIKU,
        messages=[
            {
                "role": "system",
                "content": (
                    "Translate these niche keywords to English for Google Trends search. "
                    "Return ONLY a JSON array of strings, max 5 items. No prose."
                ),
            },
            {"role": "user", "content": ", ".join(topics)},
        ],
        temperature=0.0,
        max_tokens=100,
    )
    clean = raw.strip()
    start, end = clean.find("["), clean.rfind("]") + 1
    if start == -1 or end == 0:
        return topics[:5]
    try:
        return json.loads(clean[start:end])[:5]
    except json.JSONDecodeError:
        return topics[:5]


def _fetch_rising_queries(keywords: list[str]) -> list[str]:
    """Synchronous pytrends call — run in executor to not block event loop."""
    from pytrends.request import TrendReq

    pytrends = TrendReq(hl="ru-RU", tz=180, timeout=(10, 25), retries=1, backoff_factor=0.5)
    rising_topics: list[str] = []

    try:
        pytrends.build_payload(keywords[:5], timeframe="now 7-d", geo="RU")
        time.sleep(3)
        related = pytrends.related_queries()
        for kw in keywords[:5]:
            df = related.get(kw, {}).get("rising")
            if df is not None and not df.empty:
                for _, row in df.head(6).iterrows():
                    rising_topics.append(row["query"])
        time.sleep(2)

        # Also grab real-time trending searches for Russia
        trending = pytrends.trending_searches(pn="russia")
        if trending is not None and not trending.empty:
            for t in trending[0].head(5).tolist():
                rising_topics.append(str(t))
    except Exception as e:
        logger.warning("pytrends fetch failed: %s", e)

    return rising_topics


async def _format_with_llm(niche: str, raw_topics: list[str]) -> list[dict]:
    """Use Haiku to format raw rising queries into structured post topics."""
    topics_text = "\n".join(f"- {t}" for t in raw_topics[:30])
    raw = await chat(
        model=HAIKU,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты контент-стратег. На основе списка растущих поисковых запросов "
                    "из Google Trends (некоторые на английском) выбери и адаптируй 5 тем "
                    "для постов в Telegram, релевантных нише автора.\n"
                    "Верни ТОЛЬКО валидный JSON-массив:\n"
                    '[\n  {"title": "Тема поста (по-русски, макс 8 слов)", '
                    '"angle": "Один конкретный угол/хук для поста (по-русски)"},\n  ...\n]\n'
                    "Ровно 5 элементов. Весь текст на русском."
                ),
            },
            {
                "role": "user",
                "content": f"Ниша автора: {niche}\n\nРастущие запросы Google Trends:\n{topics_text}",
            },
        ],
        temperature=0.3,
        max_tokens=600,
    )
    clean = raw.strip()
    start, end = clean.find("["), clean.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"LLM не вернул JSON: {clean[:200]}")
    result = json.loads(clean[start:end])
    return [
        {"title": str(t.get("title", "")), "angle": str(t.get("angle", ""))}
        for t in result[:5]
        if isinstance(t, dict) and t.get("title")
    ]


# ── Public API ────────────────────────────────────────────────────────────────

async def run_trends(main_topics: list[str]) -> list[dict]:
    """
    Fetch trending topics.
    Tries Google Trends (pytrends) first, falls back to Perplexity Sonar.
    Returns list of 5 dicts: [{"title": str, "angle": str}, ...]
    """
    niche = ", ".join(main_topics) if main_topics else "AI, технологии, малый бизнес"

    # Step 1: try pytrends
    try:
        logger.info("Fetching trends via pytrends for niche: %s", niche)
        en_keywords = await _translate_to_english(main_topics or ["AI tools", "business automation"])
        logger.info("Translated keywords: %s", en_keywords)

        loop = asyncio.get_event_loop()
        rising = await loop.run_in_executor(None, _fetch_rising_queries, en_keywords)
        logger.info("pytrends rising topics count: %d", len(rising))

        if rising:
            trends = await _format_with_llm(niche, rising)
            if trends:
                logger.info("pytrends success: %d trends", len(trends))
                return trends
    except Exception as e:
        logger.warning("pytrends pipeline failed (%s), falling back to Perplexity", e)

    # Step 2: fallback to Perplexity Sonar
    logger.info("Using Perplexity Sonar fallback")
    trends = await _run_perplexity_fallback(niche)
    if not trends:
        raise ValueError("Trends list is empty after all sources")
    return trends
