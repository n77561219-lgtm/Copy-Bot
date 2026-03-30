"""
Загружает стиль из файла напрямую (без запуска бота).

Использование:
    python scripts/load_style.py tone-of-voice.md
    python scripts/load_style.py data/uploads/result.json
"""
import asyncio
import json
import sys
from pathlib import Path

# make sure imports resolve from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.config import settings
from bot.database import init_db, save_style_examples
from bot.parsers import parse_file
from bot.agents.style_analyst import run_style_analyst, run_style_analyst_from_doc, _is_tov_document


async def main(filepath: str) -> None:
    await init_db()

    path = Path(filepath)
    if not path.exists():
        print(f"❌ Файл не найден: {filepath}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8", errors="ignore")
    print(f"File: {path.name}  ({len(content):,} chars)")

    if _is_tov_document(content):
        print("Tone of Voice document detected — reading directly...")
        profile = await run_style_analyst_from_doc(content)
    else:
        posts = parse_file(path.name, content)
        if not posts:
            print("ERROR: no posts found. Check file format.")
            sys.exit(1)
        print(f"Found {len(posts)} posts. Analysing style...")
        await save_style_examples(posts, path.name)
        profile = await run_style_analyst(posts)

    out = Path(settings.style_profile_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nOK  style_profile.json saved: {out}")
    print(f"    tone      : {profile.get('tone', {}).get('primary', '-')}")
    topics = profile.get("content_patterns", {}).get("main_topics", [])
    print(f"    topics    : {', '.join(topics[:4]) if topics else '-'}")
    forbidden = profile.get("vocabulary", {}).get("forbidden_words", [])
    print(f"    forbidden : {', '.join(forbidden[:5]) if forbidden else '-'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python scripts/load_style.py <путь_к_файлу>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
