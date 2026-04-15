import os
import json
import aiofiles
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, Document, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import settings
from bot.database import save_style_examples, get_style_examples_count, get_preference, set_preference, get_active_plan, log_usage
from bot.plans import profiles_limit, get_plan
from bot.parsers import parse_file
from bot.agents.style_analyst import run_style_analyst, run_style_analyst_from_doc, _is_tov_document

router = Router()

_ALLOWED_EXTENSIONS = {".json", ".md", ".txt"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_PROFILES = 5  # absolute hard cap; per-plan limit enforced dynamically
_DEFAULT_PROFILE = "main"


class UploadStates(StatesGroup):
    waiting_profile_name = State()


def style_profile_path(user_id: int, profile: str = _DEFAULT_PROFILE) -> str:
    safe = "".join(c for c in profile if c.isalnum() or c in "-_")[:20] or _DEFAULT_PROFILE
    return os.path.join(settings.style_profiles_dir, f"{user_id}_{safe}.json")


def list_user_profiles(user_id: int) -> list[str]:
    """Return list of profile names for user."""
    prefix = f"{user_id}_"
    profiles = []
    try:
        for fname in os.listdir(settings.style_profiles_dir):
            if fname.startswith(prefix) and fname.endswith(".json"):
                name = fname[len(prefix):-5]
                profiles.append(name)
    except FileNotFoundError:
        pass
    return sorted(profiles)


async def get_active_profile(user_id: int) -> str:
    val = await get_preference(user_id, "active_profile")
    return val or _DEFAULT_PROFILE


def _profile_choice_kb(user_id: int, pending_file: str) -> InlineKeyboardMarkup:
    profiles = list_user_profiles(user_id)
    b = InlineKeyboardBuilder()
    for p in profiles:
        b.row(InlineKeyboardButton(text=f"📁 {p}", callback_data=f"upload:profile:{p}"))
    if len(profiles) < _MAX_PROFILES:
        b.row(InlineKeyboardButton(text="➕ Создать новый профиль", callback_data="upload:profile:new"))
    return b.as_markup()


# legacy path for backwards compat (generate.py still uses it)
def _style_profile_path(user_id: int) -> str:
    return style_profile_path(user_id, _DEFAULT_PROFILE)


@router.message(F.document)
async def handle_document(message: Message, state: FSMContext) -> None:
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

    profiles = list_user_profiles(user_id)

    if not profiles:
        # First upload — go straight to main profile
        await _process_upload(message, state, doc, filename, _DEFAULT_PROFILE)
        return

    # Has existing profiles — ask which one to save to
    plan_name = await get_active_plan(user_id)
    max_profiles = profiles_limit(plan_name)
    await state.update_data(pending_doc_id=doc.file_id, pending_filename=filename)
    b = InlineKeyboardBuilder()
    for p in profiles:
        b.row(InlineKeyboardButton(text=f"📁 Обновить «{p}»", callback_data=f"upload:profile:{p}"))
    if len(profiles) < max_profiles:
        b.row(InlineKeyboardButton(text="➕ Новый профиль", callback_data="upload:profile:new"))
    else:
        plan = get_plan(plan_name)
        b.row(InlineKeyboardButton(
            text=f"🔒 Лимит профилей ({max_profiles}) • Улучшить тариф",
            callback_data="subscribe",
        ))
    await message.answer(
        "В какой профиль стиля сохранить?",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("upload:profile:"))
async def cb_upload_profile(callback: CallbackQuery, state: FSMContext) -> None:
    profile_name = callback.data.split(":", 2)[2]
    data = await state.get_data()
    doc_id = data.get("pending_doc_id")
    filename = data.get("pending_filename", "export.json")

    if not doc_id:
        await callback.answer("Файл не найден, загрузи снова.", show_alert=True)
        return

    await callback.message.delete()

    if profile_name == "new":
        await state.set_state(UploadStates.waiting_profile_name)
        await callback.message.answer("Введи название нового профиля (например: канал, бизнес, личный):")
        await callback.answer()
        return

    # Create fake document object to reuse _process_upload
    class _FakeDoc:
        file_id = doc_id
    await _process_upload(callback.message, state, _FakeDoc(), filename, profile_name)
    await callback.answer()


@router.message(UploadStates.waiting_profile_name)
async def handle_profile_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:20]
    if not name:
        await message.answer("Название не может быть пустым.")
        return
    data = await state.get_data()
    doc_id = data.get("pending_doc_id")
    filename = data.get("pending_filename", "export.json")

    class _FakeDoc:
        file_id = doc_id
    await _process_upload(message, state, _FakeDoc(), filename, name)


async def _process_upload(message: Message, state: FSMContext, doc, filename: str, profile_name: str) -> None:
    user_id = message.from_user.id
    status_msg = await message.answer("📥 Загружаю файл...")

    try:
        tg_file = await message.bot.get_file(doc.file_id)
        file_path = os.path.join(settings.uploads_dir, filename)
        await message.bot.download_file(tg_file.file_path, destination=file_path)

        await status_msg.edit_text("🔍 Парсю посты...")

        async with aiofiles.open(file_path, encoding="utf-8", errors="ignore") as f:
            content = await f.read()

        posts = parse_file(filename, content)

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

        await log_usage(user_id, "style_analyzed")

        profile_path = style_profile_path(user_id, profile_name)
        async with aiofiles.open(profile_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(style_profile, ensure_ascii=False, indent=2))

        # Set as active profile
        await set_preference(user_id, "active_profile", profile_name)
        await state.clear()

        tone = style_profile.get("tone", {}).get("primary", "не определён")
        main_topics = style_profile.get("content_patterns", {}).get("main_topics", [])
        topics_str = ", ".join(main_topics[:3]) if main_topics else "не определены"

        await status_msg.edit_text(
            f"✅ Стиль загружен в профиль *«{profile_name}»* ({source_label})!\n\n"
            f"{count_line}"
            f"🎭 Тональность: {tone}\n"
            f"📌 Темы: {topics_str}\n\n"
            "Теперь напиши тему — и я напишу пост в твоём стиле.",
            parse_mode="Markdown",
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "style:switch")
async def cb_style_switch(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    profiles = list_user_profiles(user_id)
    active = await get_active_profile(user_id)

    if not profiles:
        await callback.answer("Нет сохранённых профилей.", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for p in profiles:
        mark = "✅ " if p == active else ""
        b.row(InlineKeyboardButton(text=f"{mark}📁 {p}", callback_data=f"style:activate:{p}"))
    await callback.message.answer("Выбери профиль стиля:", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("style:activate:"))
async def cb_style_activate(callback: CallbackQuery) -> None:
    profile_name = callback.data.split(":", 2)[2]
    user_id = callback.from_user.id
    profiles = list_user_profiles(user_id)
    if profile_name not in profiles:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await set_preference(user_id, "active_profile", profile_name)
    await callback.message.edit_text(f"✅ Активный профиль: *«{profile_name}»*", parse_mode="Markdown")
    await callback.answer()
