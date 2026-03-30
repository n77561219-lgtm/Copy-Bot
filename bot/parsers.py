import json
import re
from pathlib import Path


def parse_telegram_json(content: str) -> list[str]:
    """Parse Telegram channel export (result.json)."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    posts = []
    for msg in data.get("messages", []):
        if msg.get("type") != "message":
            continue

        raw = msg.get("text", "")

        # text can be a plain string or a list of mixed entities
        if isinstance(raw, list):
            parts = []
            for part in raw:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.append(part.get("text", ""))
            raw = "".join(parts)

        raw = raw.strip()
        if len(raw) > 50:
            posts.append(raw)

    return posts


def parse_telegram_md(content: str) -> list[str]:
    """Parse Telegram export as Markdown / plain text."""
    # Try splitting by horizontal rules first
    blocks = re.split(r"\n-{3,}\n|\n={3,}\n", content)

    # If that didn't work, try splitting by date-time lines
    if len(blocks) <= 1:
        date_pattern = re.compile(
            r"^(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}",
            re.MULTILINE,
        )
        parts = date_pattern.split(content)
        blocks = [p.strip() for p in parts if p.strip()]

    posts = []
    for block in blocks:
        # Strip leading date/time line if present
        block = re.sub(
            r"^\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}.*\n?", "", block
        ).strip()
        block = re.sub(
            r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}.*\n?", "", block
        ).strip()
        if len(block) > 50:
            posts.append(block)

    return posts


def parse_file(filename: str, content: str) -> list[str]:
    """Auto-detect format and return deduplicated posts."""
    ext = Path(filename).suffix.lower()
    posts = parse_telegram_json(content) if ext == ".json" else parse_telegram_md(content)

    seen: set[str] = set()
    unique: list[str] = []
    for p in posts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique
