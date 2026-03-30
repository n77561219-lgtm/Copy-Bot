import json
import os
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.config import settings
from bot.database import save_post, save_content_plan, get_content_plan
from bot.content_plan_reader import (
    get_upcoming, get_all, format_upcoming, format_all, mark_done,
)
from bot.handlers.settings import get_setting
from bot.agents.dispatcher import run_dispatcher
from bot.agents.researcher import run_researcher
from bot.agents.copywriter import run_copywriter
from bot.agents.critic import run_critic
from bot.agents.editor import run_editor, EditMode
from bot.agents.planner import run_planner
from bot.agents.image_gen import generate_image
from bot.keyboards import (
    post_actions_keyboard, edit_actions_keyboard, plan_keyboard, plan_actions_keyboard,
    style_keyboard, main_menu,
    MENU_WRITE, MENU_PLAN, MENU_STYLE, MENU_HELP,
)

router = Router()


class S(StatesGroup):
    post_shown = State()
    waiting_post_topic = State()
    waiting_custom_edit = State()
    trends_shown = State()
    topic_search_waiting = State()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _style_profile_path(user_id: int) -> str:
    return os.path.join(settings.style_profiles_dir, f"{user_id}.json")


def _load_style_profile(user_id: int) -> dict:
    path = _style_profile_path(user_id)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _no_style_msg() -> str:
    return "⚠️ Стиль не загружен. Отправь файл с постами канала.\nИспользуй /upload для инструкции."


async def _generate_post(
    message: Message,
    state: FSMContext,
    topic: str,
    post_type: str = "мнение",
    previous_draft: str = "",
    feedback: str = "",
    user_id: int | None = None,
) -> None:
    if user_id is None:
        user_id = message.from_user.id

    style_profile = _load_style_profile(user_id)
    if not style_profile:
        await message.answer(_no_style_msg())
        return

    # Load user settings
    post_length  = await get_setting(user_id, "post_length")
    show_score   = await get_setting(user_id, "show_score")
    critic_iters = int(await get_setting(user_id, "critic_iters"))

    status = await message.answer("🔍 Исследую тему...")
    try:
        research = await run_researcher(topic)

        await status.edit_text("✍️ Пишу пост...")
        draft = await run_copywriter(
            topic=topic,
            style_profile=style_profile,
            research=research,
            post_type=post_type,
            previous_draft=previous_draft,
            feedback=feedback,
            length=post_length,
        )

        await status.edit_text("🔎 Проверяю качество...")

        # Critic → Editor loop (controlled by settings)
        result = await run_critic(draft, style_profile)
        if result["verdict"] == "REVISE" and critic_iters >= 2:
            draft = await run_editor(
                post=draft,
                style_profile=style_profile,
                mode="custom",
                custom_instruction="Улучши пост",
                issues=result["issues"],
            )
            result = await run_critic(draft, style_profile)

    except Exception as e:
        err = str(e)
        if "402" in err or "credits" in err.lower():
            await status.edit_text(
                "💳 Недостаточно кредитов на OpenRouter.\n\n"
                "Пополни баланс: openrouter.ai/settings/credits"
            )
        elif "400" in err or "model" in err.lower():
            await status.edit_text("❌ Неверный ID модели. Проверь MODEL_HAIKU и MODEL_SONNET в .env")
        else:
            await status.edit_text(f"❌ Ошибка API: {err[:200]}")
        return

    score = result.get("score", 0.0)
    s = result.get("score_style", 0)
    c = result.get("score_content", 0)
    e = result.get("score_engagement", 0)
    tip = result.get("tip", "")
    score_emoji = "🟢" if score >= 8 else "🟡" if score >= 6 else "🔴"

    score_line = f"{score_emoji} Оценка: {score}/10  (стиль: {s}, контент: {c}, вовлечение: {e})"
    tip_line = f"💡 {tip}" if tip else ""
    footer = (
        "\n".join(filter(None, ["─────────────", score_line, tip_line]))
        if show_score == "yes" else ""
    )

    await status.delete()
    await message.answer(
        f"{draft}\n\n{footer}",
        reply_markup=post_actions_keyboard(),
    )
    await state.set_state(S.post_shown)
    await state.update_data(current_post=draft, current_topic=topic, post_type=post_type)


# ─────────────────────────────────────────────
# Reply-keyboard menu handlers
# ─────────────────────────────────────────────

@router.message(F.text == MENU_WRITE)
async def menu_write(message: Message, state: FSMContext) -> None:
    await message.answer("Напиши тему поста:")
    await state.set_state(S.waiting_post_topic)


async def _show_upcoming(target: Message) -> None:
    """Send next 3 planned posts with action keyboard."""
    upcoming = get_upcoming(3)
    text = format_upcoming(upcoming)
    dates = [p.date.isoformat() for p in upcoming]
    await target.answer(text, reply_markup=plan_actions_keyboard(dates), parse_mode="Markdown")


@router.message(F.text == MENU_PLAN)
async def menu_plan(message: Message, state: FSMContext) -> None:
    await _show_upcoming(message)


@router.message(F.text == MENU_STYLE)
async def menu_style(message: Message) -> None:
    user_id = message.from_user.id
    path = _style_profile_path(user_id)
    if not os.path.exists(path):
        await message.answer(
            "🎨 Стиль не загружен.\n\n"
            "Отправь сюда файл:\n"
            "• result.json — экспорт Telegram-канала\n"
            "• tone-of-voice.md — документ стиля",
            reply_markup=main_menu(),
        )
        return
    with open(path, encoding="utf-8") as f:
        profile = json.load(f)
    tone = profile.get("tone", {}).get("primary", "—")
    topics = profile.get("content_patterns", {}).get("main_topics", [])
    forbidden = profile.get("vocabulary", {}).get("forbidden_words", [])
    await message.answer(
        f"🎨 Текущий стиль:\n\n"
        f"Тональность: {tone}\n"
        f"Темы: {', '.join(topics[:3]) if topics else '—'}\n"
        f"Запрещённые слова: {', '.join(forbidden[:4]) if forbidden else '—'}\n\n"
        "Чтобы обновить — отправь новый файл.",
        reply_markup=style_keyboard(),
    )


@router.message(F.text == MENU_HELP)
async def menu_help(message: Message) -> None:
    from bot.handlers.start import cmd_help
    await cmd_help(message)


@router.message(S.waiting_post_topic)
async def handle_post_topic(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _generate_post(message, state, topic=message.text)


# ─────────────────────────────────────────────
# Main text handler
# ─────────────────────────────────────────────

@router.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    current = await state.get_state()

    # User is sending a custom edit instruction
    if current == S.waiting_custom_edit.state:
        data = await state.get_data()
        post = data.get("current_post", "")
        if not post:
            await state.clear()
            return
        style_profile = _load_style_profile(user_id)
        status = await message.answer("✏️ Редактирую...")
        edited = await run_editor(
            post=post,
            style_profile=style_profile,
            mode="custom",
            custom_instruction=message.text,
        )
        await status.delete()
        await message.answer(edited, reply_markup=edit_actions_keyboard())
        await state.update_data(current_post=edited)
        await state.set_state(S.post_shown)
        return

    # Classify intent
    dispatch = await run_dispatcher(message.text)
    intent = dispatch["intent"]

    if intent == "WRITE_POST":
        await _generate_post(message, state, dispatch["topic"] or message.text)

    elif intent == "EDIT_POST":
        style_profile = _load_style_profile(user_id)
        if not style_profile:
            await message.answer(_no_style_msg())
            return
        text = dispatch["text"] or message.text
        status = await message.answer("✏️ Редактирую...")
        edited = await run_editor(post=text, style_profile=style_profile, mode="human")
        await status.delete()
        await message.answer(edited, reply_markup=edit_actions_keyboard())
        await state.set_state(S.post_shown)
        await state.update_data(current_post=edited, current_topic="", post_type="")

    elif intent in ("CONTENT_PLAN", "SHOW_PLAN"):
        if intent == "CONTENT_PLAN":
            await _create_plan(message, state, dispatch["days"])
        else:
            await _show_plan(message)

    elif intent == "HELP":
        from bot.handlers.start import cmd_help
        await cmd_help(message)

    else:
        await message.answer(
            "🤔 Не совсем понял. Попробуй:\n"
            "• «Напиши пост про [тему]»\n"
            "• «Отредактируй: [текст]»\n"
            "• /plan — контент-план\n"
            "• /help — справка"
        )


# ─────────────────────────────────────────────
# Content plan
# ─────────────────────────────────────────────

async def _create_plan(message: Message, state: FSMContext, days: int, user_id: int | None = None) -> None:
    if user_id is None:
        user_id = message.from_user.id
    style_profile = _load_style_profile(user_id)
    if not style_profile:
        await message.answer(_no_style_msg())
        return

    status = await message.answer(f"📅 Создаю контент-план на {days} дней...")
    plan = await run_planner(days=days, style_profile=style_profile)

    if not plan:
        await status.edit_text("❌ Не удалось создать план. Попробуй ещё раз.")
        return

    lines = [f"📅 Контент-план на {days} дней:\n"]
    for item in plan:
        lines.append(
            f"📌 {item.get('date', '')} — {item.get('format', '').upper()}\n"
            f"{item.get('topic', '')}\n"
            f"↳ {item.get('angle', '')}\n"
        )

    await status.delete()
    await message.answer("\n".join(lines).strip(), reply_markup=plan_keyboard())
    await state.update_data(pending_plan=plan)


@router.message(Command("plan"))
async def cmd_plan(message: Message, state: FSMContext) -> None:
    args = message.text.split()
    days = 7
    if len(args) > 1 and args[1].isdigit():
        days = max(1, min(int(args[1]), 30))
    await _create_plan(message, state, days)


@router.message(Command("show_plan"))
async def cmd_show_plan(message: Message) -> None:
    await _show_plan(message)


async def _show_plan(message: Message) -> None:
    user_id = message.from_user.id
    plan = await get_content_plan(user_id)
    if not plan:
        await message.answer("📅 Контент-план пуст.\nИспользуй /plan чтобы создать его.")
        return
    status_icons = {"planned": "⬜", "writing": "🔄", "done": "✅"}
    lines = ["📅 Текущий контент-план:\n"]
    for item in plan:
        icon = status_icons.get(item["status"], "⬜")
        lines.append(f"{icon} {item['date']} — {item['topic']}")
    await message.answer("\n".join(lines))


# ─────────────────────────────────────────────
# Inline button callbacks
# ─────────────────────────────────────────────

@router.callback_query(F.data == "post:save")
async def cb_save(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    if data.get("current_post"):
        await save_post(user_id, data["current_post"], data.get("current_topic", ""))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Пост сохранён!")
    await state.clear()
    await callback.message.answer("Готово! Что дальше?", reply_markup=main_menu())


@router.callback_query(F.data == "post:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("❌ Отменено")
    await state.clear()
    await callback.message.answer("Отменено.", reply_markup=main_menu())


@router.callback_query(F.data == "post:edit")
async def cb_edit(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Выбери тип правки или напиши свою инструкцию:",
        reply_markup=edit_actions_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "post:regenerate")
async def cb_regenerate(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    topic = data.get("current_topic", "")
    if not topic:
        await callback.answer("❌ Нет темы для перегенерации")
        return
    await callback.answer("🔄 Генерирую...")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _generate_post(
        callback.message, state, topic, data.get("post_type", "мнение"),
        user_id=callback.from_user.id,
    )


@router.callback_query(F.data == "post:add_to_plan")
async def cb_add_to_plan(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    if data.get("current_post"):
        await save_post(user_id, data["current_post"], data.get("current_topic", ""))
    await callback.answer("📅 Сохранено!")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.in_({"edit:shorter", "edit:longer", "edit:punchier", "edit:human", "edit:grammar"}))
async def cb_edit_mode(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    post = data.get("current_post", "")
    if not post:
        await callback.answer("❌ Нет текста")
        return

    mode_map: dict[str, EditMode] = {
        "edit:shorter":  "shorter",
        "edit:longer":   "longer",
        "edit:punchier": "punchier",
        "edit:human":    "human",
        "edit:grammar":  "grammar",
    }
    mode = mode_map[callback.data]
    style_profile = _load_style_profile(user_id)

    await callback.answer("✏️ Редактирую...")
    await callback.message.edit_reply_markup(reply_markup=None)

    status = await callback.message.answer("✏️ Редактирую...")
    try:
        edited = await run_editor(post=post, style_profile=style_profile, mode=mode)
    except Exception as e:
        err = str(e)
        if "402" in err or "credits" in err.lower():
            await status.edit_text("💳 Недостаточно кредитов на OpenRouter.\nopenrouter.ai/settings/credits")
        else:
            await status.edit_text(f"❌ Ошибка: {err[:200]}")
        return
    await status.delete()

    await callback.message.answer(edited, reply_markup=edit_actions_keyboard())
    await state.update_data(current_post=edited)
    await state.set_state(S.post_shown)


@router.callback_query(F.data == "edit:custom")
async def cb_edit_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("✍️ Напиши инструкцию для правки:")
    await state.set_state(S.waiting_custom_edit)
    await callback.answer()


@router.callback_query(F.data == "plan:save")
async def cb_plan_save(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    plan = data.get("pending_plan", [])
    if plan:
        await save_content_plan(user_id, plan)
        await callback.answer("✅ План сохранён!")
    else:
        await callback.answer("❌ Нет плана")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await callback.message.answer("План сохранён!", reply_markup=main_menu())


@router.callback_query(F.data == "style:upload_hint")
async def cb_style_upload(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Отправь файл прямо сюда:\n"
        "• result.json — экспорт Telegram\n"
        "• tone-of-voice.md — документ стиля"
    )
    await callback.answer()


@router.callback_query(F.data == "plan:regenerate")
async def cb_plan_regenerate(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("🔄 Пересоздаю...")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _create_plan(callback.message, state, 7, user_id=callback.from_user.id)


@router.callback_query(F.data == "plan:ai_generate")
async def cb_plan_ai(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("🤖 Генерирую...")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _create_plan(callback.message, state, 7, user_id=callback.from_user.id)


@router.callback_query(F.data == "plan:show_all")
async def cb_plan_all(callback: CallbackQuery) -> None:
    await callback.answer()
    all_posts = get_all(include_done=True)
    if not all_posts:
        await callback.message.answer("📋 Плановых постов нет. Редактируй content-plan.md")
        return
    await callback.message.answer(format_all(all_posts))


@router.callback_query(F.data.startswith("plan:write:"))
async def cb_plan_write(callback: CallbackQuery, state: FSMContext) -> None:
    date_str = callback.data.split("plan:write:")[1]
    all_posts = get_all()
    post = next((p for p in all_posts if p.date.isoformat() == date_str), None)
    if not post:
        await callback.answer("❌ Пост не найден")
        return
    await callback.answer("✏️ Генерирую пост...")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _generate_post(
        callback.message, state,
        topic=post.topic,
        post_type=post.fmt or "мнение",
        feedback=post.angle,
        user_id=callback.from_user.id,
    )


@router.callback_query(F.data == "image:generate")
async def cb_image_generate(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    post = data.get("current_post", "")
    if not post:
        await callback.answer("❌ Нет текста для картинки")
        return

    await callback.answer("🖼 Генерирую картинку...")
    status = await callback.message.answer("🖼 Создаю картинку (16:9)...")
    try:
        image_data, prompt = await generate_image(post)
    except Exception as e:
        err = str(e)
        if "402" in err or "credits" in err.lower():
            await status.edit_text("💳 Недостаточно кредитов.\nopenrouter.ai/settings/credits")
        else:
            await status.edit_text(f"❌ Ошибка генерации: {err[:200]}")
        return

    await status.delete()
    from aiogram.types import BufferedInputFile
    if isinstance(image_data, bytes):
        photo = BufferedInputFile(image_data, filename="image.jpg")
    else:
        photo = image_data  # URL string
    await callback.message.answer_photo(
        photo=photo,
        caption="🖼 Картинка к посту",
    )


@router.callback_query(F.data.startswith("plan:done:"))
async def cb_plan_done(callback: CallbackQuery) -> None:
    from datetime import datetime
    date_str = callback.data.split("plan:done:")[1]
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        await callback.answer("❌ Неверная дата")
        return
    marked = mark_done(d)
    if marked:
        await callback.answer("✅ Отмечено как готово!")
    else:
        await callback.answer("⚠️ Не удалось найти пост в файле")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_upcoming(callback.message)
