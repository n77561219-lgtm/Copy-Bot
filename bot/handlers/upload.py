import os
import json
import aiofiles
from aiogram import Router, F
from aiogram.types import Message, Document
from bot.config import settings
from bot.database import save_style_examples, get_style_examples_count
from bot.parsers import parse_file
from bot.agents.style_analyst import run_style_analyst, run_style_analyst_from_doc, _is_tov_document

router = Router()

_ALLOWED_EXTENSIONS = {".json", ".md", ".txt"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _style_profile_path(user_id: int) -> str:
    return os.path.join(settings.style_profiles_dir, f"{user_id}.json")


@router.message(F.document)
async def handle_document(message: Message) -> None:
    user_id = message.from_user.id
    doc: Document = message.document
    filename = doc.file_name or "export.txt"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in _ALLOWED_EXTENSIONS:
        await message.answer(
            "❌ Поддерживаются файлы: .json, .md, .txt\n"
            "Экспортируй канал из Telegram Desktop."
        )
        return

    if doc.file_size and doc.file_size > _MAX_FILE_SIZE:
        await message.answer("❌ Файл слишком большой (максимум 10 МБ).")
        return

    status_msg = await message.answer("📥 Загружаю файл...")

    try:
        tg_file = await message.bot.get_file(doc.file_id)
        file_path = os.path.join(settings.uploads_dir, filename)
        await message.bot.download_file(tg_file.file_path, destination=file_path)

        await status_msg.edit_text("🔍 Парсю посты...")

        async with aiofiles.open(file_path, encoding="utf-8", errors="ignore") as f:
            content = await f.read()

        posts = parse_file(filename, content)

        if not posts:
            await status_msg.edit_text(
                "❌ Не удалось извлечь посты из файла.\n"
                "Убедись, что это экспорт Telegram-канала в формате JSON."
            )
            return

        # Detect document type: structured ToV doc vs raw posts
        if _is_tov_document(content):
            await status_msg.edit_text("📖 Вижу документ Tone of Voice. Читаю напрямую...")
            style_profile = await run_style_analyst_from_doc(content)
            source_label = "ToV-документ"
            count_line = ""
        else:
            if not posts:
                await status_msg.edit_text(
                    "❌ Не удалось извлечь посты из файла.\n"
                    "Убедись, что это экспорт Telegram-канала в формате JSON."
                )
                return
            await status_msg.edit_text(f"📊 Найдено {len(posts)} постов. Анализирую стиль...")
            await save_style_examples(user_id, posts, filename)
            style_profile = await run_style_analyst(posts)
            total = await get_style_examples_count(user_id)
            source_label = "посты канала"
            count_line = f"📝 Постов: {len(posts)} (всего в базе: {total})\n"

        profile_path = _style_profile_path(user_id)
        async with aiofiles.open(profile_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(style_profile, ensure_ascii=False, indent=2))

        tone = style_profile.get("tone", {}).get("primary", "не определён")
        main_topics = style_profile.get("content_patterns", {}).get("main_topics", [])
        topics_str = ", ".join(main_topics[:3]) if main_topics else "не определены"

        await status_msg.edit_text(
            f"✅ Стиль загружен ({source_label})!\n\n"
            f"{count_line}"
            f"🎭 Тональность: {tone}\n"
            f"📌 Темы: {topics_str}\n\n"
            "Теперь напиши тему — и я напишу пост в твоём стиле."
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")
