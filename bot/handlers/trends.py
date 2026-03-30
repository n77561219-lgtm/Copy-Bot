"""Trends handler — real web search via Perplexity Sonar + inline post generation."""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.keyboards import trend_topics_kb, trends_entry_kb, MENU_TRENDS
from bot.agents.trends import run_trends
from bot.handlers.generate import S, _generate_post, _load_style_profile

router = Router()


async def _fetch_and_show_trends(target: Message, state: FSMContext) -> None:
    style_profile = _load_style_profile()
    main_topics = (
        style_profile.get("content_patterns", {}).get("main_topics", [])
        if style_profile else []
    )

    status = await target.answer("🔥 Ищу актуальные тренды в интернете...")
    try:
        trends = await run_trends(main_topics)
    except ValueError as e:
        await status.edit_text(f"❌ Ошибка парсинга: {e}")
        return
    except Exception as e:
        err = str(e)
        if "402" in err or "credits" in err.lower():
            await status.edit_text("💳 Недостаточно кредитов.\nopenrouter.ai/settings/credits")
        elif "400" in err or "model" in err.lower():
            await status.edit_text("❌ Неверный ID модели. Проверь MODEL_TRENDS в .env")
        else:
            await status.edit_text(f"❌ Ошибка API: {err[:200]}")
        return

    if not trends:
        await status.edit_text("😕 Не удалось найти тренды. Попробуй позже.")
        return

    lines = ["🔥 *Актуальные тренды прямо сейчас:*\n"]
    for i, t in enumerate(trends, 1):
        lines.append(f"{i}. *{t['title']}*\n↳ _{t['angle']}_\n")
    text = "\n".join(lines)

    await status.delete()
    await target.answer(text, reply_markup=trend_topics_kb(trends), parse_mode="Markdown")
    await state.set_state(S.trends_shown)
    await state.update_data(current_trends=trends)


@router.message(F.text == MENU_TRENDS)
async def menu_trends(message: Message, state: FSMContext) -> None:
    style_profile = _load_style_profile()
    topics = (
        style_profile.get("content_patterns", {}).get("main_topics", [])
        if style_profile else []
    )
    niche_label = ", ".join(topics[:2]) if topics else ""
    await message.answer(
        "🔍 *Поиск трендов*\n\nВыбери тип поиска:",
        reply_markup=trends_entry_kb(niche_label),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "trend:by_niche")
async def cb_trend_by_niche(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _fetch_and_show_trends(callback.message, state)


@router.callback_query(F.data == "trend:refresh")
async def cb_trend_refresh(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("🔄 Обновляю...")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _fetch_and_show_trends(callback.message, state)


@router.callback_query(F.data.startswith("trend:write:"))
async def cb_trend_write(callback: CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.split("trend:write:")[1])
    data = await state.get_data()
    trends = data.get("current_trends", [])
    if not trends or idx >= len(trends):
        await callback.answer("❌ Тренд не найден, обнови список")
        return
    trend = trends[idx]
    await callback.answer("✏️ Генерирую пост...")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _generate_post(
        callback.message,
        state,
        topic=trend["title"],
        post_type="мнение",
        feedback=trend.get("angle", ""),
    )
