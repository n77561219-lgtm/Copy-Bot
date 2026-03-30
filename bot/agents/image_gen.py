"""Image generation via OpenRouter chat completions (google/gemini-2.5-flash-image, 16:9)."""
import base64
import logging
import httpx

from bot.config import settings
from bot.llm import chat, HAIKU

logger = logging.getLogger(__name__)


async def _make_image_prompt(post_text: str) -> str:
    result = await chat(
        model=HAIKU,
        messages=[
            {
                "role": "system",
                "content": (
                    "You create concise image prompts for AI image generators. "
                    "Given a social media post in Russian, write a SHORT (1-2 sentences) "
                    "English image description that visually represents the post's theme. "
                    "Focus on visual elements, mood, and metaphor. "
                    "No text in the image. No people's faces. Photorealistic or illustrative style. "
                    "Wide landscape 16:9 format."
                ),
            },
            {
                "role": "user",
                "content": f"Post:\n{post_text[:800]}\n\nWrite image prompt:",
            },
        ],
        temperature=0.7,
        max_tokens=150,
    )
    return result.strip()


def _extract_image(data: dict) -> bytes | str:
    """Try every known format to extract image bytes or URL from a chat completion response."""
    message = data["choices"][0]["message"]
    content = message.get("content")
    logger.info("Full message keys: %s", list(message.keys()))
    logger.info("Image response content type=%s value=%s", type(content).__name__, str(content)[:500])

    # --- list of content blocks ---
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type", "")

            if t == "image_url":
                url = block["image_url"]["url"]
                if url.startswith("data:"):
                    _, b64 = url.split(",", 1)
                    return base64.b64decode(b64)
                return url

            if t == "image":
                src = block.get("source", {})
                if src.get("type") == "base64":
                    return base64.b64decode(src["data"])
                if src.get("type") == "url":
                    return src["url"]

            # Gemini inline_data format
            if "inline_data" in block:
                return base64.b64decode(block["inline_data"]["data"])

    # --- plain string ---
    if isinstance(content, str):
        s = content.strip()
        if s.startswith("http"):
            return s
        if s.startswith("data:"):
            _, b64 = s.split(",", 1)
            return base64.b64decode(b64)

    # --- Gemini native: message.parts ---
    for part in message.get("parts", []) or []:
        if isinstance(part, dict):
            if "inline_data" in part:
                return base64.b64decode(part["inline_data"]["data"])
            if part.get("type") == "image_url":
                url = part["image_url"]["url"]
                if url.startswith("data:"):
                    _, b64 = url.split(",", 1)
                    return base64.b64decode(b64)
                return url

    # --- top-level data array (some providers) ---
    for item in data.get("data", []) or []:
        if isinstance(item, dict):
            if "b64_json" in item:
                return base64.b64decode(item["b64_json"])
            if "url" in item:
                return item["url"]

    # --- raw base64 in top-level fields ---
    for key in ("b64_json", "url"):
        if key in data:
            val = data[key]
            if key == "b64_json":
                return base64.b64decode(val)
            return val

    raise RuntimeError(
        f"Cannot extract image. message keys={list(message.keys())}, "
        f"content type={type(content).__name__}, preview={str(content)[:200]}"
    )


async def generate_image(post_text: str) -> tuple[bytes | str, str]:
    """
    Generate a 16:9 image matching the post's theme.
    Returns (image_data, prompt) where image_data is bytes or URL string.
    """
    prompt = await _make_image_prompt(post_text)

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/copy-bot",
                "X-Title": "Telegram Copy Bot",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.model_image,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Generate a wide 16:9 landscape image: {prompt}. "
                            "No text, no watermarks."
                        ),
                    }
                ],
            },
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Image API error {response.status_code}: {response.text[:300]}"
        )

    data = response.json()
    logger.info("Full image response keys: %s", list(data.keys()))
    image_data = _extract_image(data)
    return image_data, prompt
