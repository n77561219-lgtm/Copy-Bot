"""Topic search agent — converts user query to YouTube hashtags, scrapes via Apify, summarizes with LLM."""
import json
import httpx

from bot.llm import chat, HAIKU
from bot.config import settings


async def _query_to_hashtags(query: str) -> list[str]:
    raw = await chat(
        model=HAIKU,
        messages=[
            {
                "role": "system",
                "content": (
                    "Convert the user's topic (may be in Russian) to 3-4 English YouTube hashtags "
                    "suitable for searching trends on YouTube. "
                    "Return ONLY a valid JSON array of strings. No hashtag symbol, no prose."
                ),
            },
            {"role": "user", "content": query},
        ],
        temperature=0.0,
        max_tokens=100,
    )
    clean = raw.strip()
    start = clean.find("[")
    end = clean.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Could not extract hashtags JSON: {clean[:100]}")
    return json.loads(clean[start:end])


async def _scrape_youtube(hashtags: list[str]) -> list[dict]:
    token = settings.apify_token
    if not token:
        raise RuntimeError("APIFY_TOKEN не задан в .env")
    url = (
        "https://api.apify.com/v2/acts/streamers~youtube-video-scraper-by-hashtag"
        "/run-sync-get-dataset-items"
    )
    params = {"token": token, "timeout": 90, "memory": 256}
    payload = {"hashtags": hashtags, "maxResults": 5}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, params=params, json=payload)
        if resp.status_code == 401:
            raise RuntimeError("Неверный APIFY_TOKEN — проверь .env")
        if resp.status_code == 402:
            raise RuntimeError("Недостаточно кредитов Apify — apify.com/billing")
        resp.raise_for_status()
        return resp.json()


async def _summarize_topics(query: str, videos: list[dict]) -> list[dict]:
    video_lines = "\n".join(
        f"- {v.get('title', '')} ({v.get('viewCount', 0)} views)"
        for v in videos[:20]
        if v.get("title")
    )
    raw = await chat(
        model=HAIKU,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты контент-стратег. На основе названий YouTube-видео по теме "
                    "выдели 3 трендовых подтемы для написания постов. "
                    "Верни ТОЛЬКО валидный JSON-массив:\n"
                    '[\n  {"title": "Тема поста (по-русски, макс 8 слов)", '
                    '"angle": "Один конкретный угол/хук для поста (по-русски)"},\n  ...\n]\n'
                    "Ровно 3 элемента. Весь текст на русском."
                ),
            },
            {
                "role": "user",
                "content": f"Тема поиска: {query}\n\nВидео с YouTube:\n{video_lines}",
            },
        ],
        temperature=0.3,
        max_tokens=400,
    )
    clean = raw.strip()
    start = clean.find("[")
    end = clean.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"LLM не вернул JSON: {clean[:200]}")
    result = json.loads(clean[start:end])
    topics = [
        {"title": str(t.get("title", "")), "angle": str(t.get("angle", ""))}
        for t in result[:3]
        if isinstance(t, dict) and t.get("title")
    ]
    if not topics:
        raise ValueError("Список тем пуст после парсинга")
    return topics


async def run_topic_search(query: str) -> list[dict]:
    hashtags = await _query_to_hashtags(query)
    videos = await _scrape_youtube(hashtags)
    if not videos:
        raise ValueError("YouTube не вернул данных по этой теме")
    return await _summarize_topics(query, videos)
