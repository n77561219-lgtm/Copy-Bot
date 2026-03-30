"""Topic search handler — user enters a query, bot searches YouTube via Apify and suggests 3 post topics."""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.keyboards import MENU_SEARCH, topic_search_kb
from bot.agents.topic_search import run_topic_search
from bot.handlers.generate import S, _generate_post

router = Router()


@router.message(F.text == MENU_SEARCH)
async def menu_topic_search(message: Message, state: FSMContext) -> None:
    await state.set_state(S.topic_search_waiting)
    await message.answer("🔍 Введи тему или ключевые слова:")


@router.callback_query(F.data == "trend:by_query")
async def cb_trend_by_query(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(S.topic_search_waiting)
    await callback.message.answer("🔍 Введи тему или ключевые слова:")


@router.message(S.topic_search_waiting)
async def handle_topic_query(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    await state.clear()

    status = await message.answer(
        f"🔍 Ищу тренды по теме: *{query}*\n_Это займёт ~30 секунд..._",
        parse_mode="Markdown",
    )
    try:
        topics = await run_topic_search(query)
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        return

    lines = [f"🔍 *Тренды по теме: {query}*\n"]
    for i, t in enumerate(topics, 1):
        lines.append(f"{i}. *{t['title']}*\n↳ _{t['angle']}_\n")

    await status.delete()
    await message.answer(
        "\n".join(lines),
        reply_markup=topic_search_kb(topics),
        parse_mode="Markdown",
    )
    await state.set_state(S.trends_shown)
    await state.update_data(current_trends=topics)


@router.callback_query(F.data.startswith("topicsearch:write:"))
async def cb_topicsearch_write(callback: CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.split("topicsearch:write:")[1])
    data = await state.get_data()
    topics = data.get("current_trends", [])
    if not topics or idx >= len(topics):
        await callback.answer("❌ Тема не найдена, попробуй поиск снова")
        return
    topic = topics[idx]
    await callback.answer("✏️ Генерирую пост...")
    await callback.message.edit_reply_markup(reply_markup=None)
    await _generate_post(
        callback.message,
        state,
        topic=topic["title"],
        post_type="мнение",
        feedback=topic.get("angle", ""),
    )
