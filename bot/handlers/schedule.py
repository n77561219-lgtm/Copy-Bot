"""Handlers for post scheduling: queue management and schedule slots."""
import re
import logging
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.database import (
    get_user_queue, get_schedule_slots, get_queue_stats,
    add_to_queue, delete_scheduled_post,
    add_schedule_slot, delete_schedule_slot,
    next_free_slot, is_queue_paused, toggle_queue_pause,
    get_preference, get_active_plan,
)
from bot.plans import get_plan, slots_limit
from bot.keyboards import (
    schedule_main_kb, schedule_queue_kb, schedule_confirm_kb,
    sched_del_confirm_kb, main_menu, MENU_SCHEDULE,
)

router = Router()
logger = logging.getLogger(__name__)


class SchedS(StatesGroup):
    waiting_slot_time    = State()
    waiting_del_slot     = State()
    waiting_manual_time  = State()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_time(text: str) -> str | None:
    """Parse 'HH:MM' or 'H:MM' from user input. Returns 'HH:MM' or None."""
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return f"{h:02d}:{mn:02d}"
    return None


def _parse_datetime(text: str) -> datetime | None:
    """Parse datetime from user input. Supports:
    - 'DD.MM HH:MM' or 'DD.MM.YYYY HH:MM'
    - 'завтра в HH:MM', 'сегодня в HH:MM'
    Returns UTC datetime or None.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    text = text.strip().lower()

    # relative: today/tomorrow
    for word, delta in [("сегодня", 0), ("завтра", 1)]:
        if word in text:
            m = re.search(r"(\d{1,2}):(\d{2})", text)
            if m:
                h, mn = int(m.group(1)), int(m.group(2))
                day = now.date() + timedelta(days=delta)
                return datetime(day.year, day.month, day.day, h, mn, tzinfo=timezone.utc)

    # DD.MM HH:MM
    m = re.search(r"(\d{1,2})\.(\d{2})(?:\.(\d{4}))?\s+(\d{1,2}):(\d{2})", text)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        h, mn = int(m.group(4)), int(m.group(5))
        try:
            return datetime(year, mon, day, h, mn, tzinfo=timezone.utc)
        except ValueError:
            return None

    return None


async def _schedule_screen(target: Message | CallbackQuery, user_id: int) -> None:
    slots = await get_schedule_slots(user_id)
    queue = await get_user_queue(user_id)
    stats = await get_queue_stats(user_id)
    paused = await is_queue_paused(user_id)

    slots_text = ", ".join(slots) if slots else "не настроены"
    pause_icon = "⏸ на паузе" if paused else "▶️ активна"

    lines = [
        "⏰ *Расписание публикаций*\n",
        f"🕐 Слоты (UTC): {slots_text}",
        f"📊 Очередь: {stats['pending']} ждёт · {stats['published']} опубликовано",
        f"Статус: {pause_icon}",
    ]

    msg = target if isinstance(target, Message) else target.message
    await msg.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=schedule_main_kb(paused, stats["pending"]),
    )

    if queue:
        await msg.answer(
            "📋 Посты в очереди (нажми чтобы удалить):",
            reply_markup=schedule_queue_kb(queue),
        )


# ── Menu entry ────────────────────────────────────────────────────────────────

@router.message(F.text == MENU_SCHEDULE)
async def menu_schedule(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _schedule_screen(message, message.from_user.id)


# ── Add / delete slots ────────────────────────────────────────────────────────

@router.callback_query(F.data == "sched:add_slot")
async def cb_add_slot(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer(
        "Введи время слота в формате HH:MM (UTC).\nНапример: `09:00` или `18:30`",
        parse_mode="Markdown",
    )
    await state.set_state(SchedS.waiting_slot_time)


@router.message(SchedS.waiting_slot_time)
async def handle_slot_time(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    t = _parse_time(message.text)
    if not t:
        await message.answer("❌ Не понял время. Введи в формате HH:MM, например `10:00`", parse_mode="Markdown")
        return

    # Check slot limit for plan
    plan_name = await get_active_plan(user_id)
    plan = get_plan(plan_name)
    limit = slots_limit(plan_name)
    if limit is not None:
        current_slots = await get_schedule_slots(user_id)
        if len(current_slots) >= limit:
            from bot.keyboards import plans_kb
            await state.clear()
            await message.answer(
                f"🔒 На тарифе *{plan['emoji']} {plan['name']}* доступно не более *{limit}* слот(а) расписания.\n\n"
                f"Улучши тариф чтобы добавить больше:",
                parse_mode="Markdown",
                reply_markup=plans_kb(),
            )
            return

    added = await add_schedule_slot(user_id, t)
    await state.clear()
    if added:
        await message.answer(f"✅ Слот {t} UTC добавлен.")
    else:
        await message.answer(f"⚠️ Слот {t} уже существует.")
    await _schedule_screen(message, message.from_user.id)


@router.callback_query(F.data == "sched:del_slot")
async def cb_del_slot(callback: CallbackQuery, state: FSMContext) -> None:
    slots = await get_schedule_slots(callback.from_user.id)
    if not slots:
        await callback.answer("Слотов нет", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "Введи время слота для удаления (HH:MM):\nТекущие слоты: " + ", ".join(slots),
    )
    await state.set_state(SchedS.waiting_del_slot)


@router.message(SchedS.waiting_del_slot)
async def handle_del_slot(message: Message, state: FSMContext) -> None:
    t = _parse_time(message.text)
    if not t:
        await message.answer("❌ Не понял время. Введи HH:MM")
        return
    deleted = await delete_schedule_slot(message.from_user.id, t)
    await state.clear()
    if deleted:
        await message.answer(f"✅ Слот {t} удалён.")
    else:
        await message.answer(f"⚠️ Слот {t} не найден.")
    await _schedule_screen(message, message.from_user.id)


# ── Pause / resume ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sched:toggle_pause")
async def cb_toggle_pause(callback: CallbackQuery) -> None:
    paused = await toggle_queue_pause(callback.from_user.id)
    status = "поставлена на паузу ⏸" if paused else "возобновлена ▶️"
    await callback.answer(f"Очередь {status}")
    await _schedule_screen(callback, callback.from_user.id)


# ── Delete post from queue ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sched:del_post:"))
async def cb_del_post(callback: CallbackQuery) -> None:
    raw = callback.data.split("sched:del_post:")[1]
    if not raw.lstrip("-").isdigit():
        await callback.answer("❌ Неверный ID поста", show_alert=True)
        return
    post_id = int(raw)
    await callback.message.answer(
        "🗑 Удалить этот пост из очереди?",
        reply_markup=sched_del_confirm_kb(post_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sched:del_confirm:"))
async def cb_del_confirm(callback: CallbackQuery) -> None:
    post_id = int(callback.data.split("sched:del_confirm:")[1])
    deleted = await delete_scheduled_post(post_id, callback.from_user.id)
    if deleted:
        await callback.answer("🗑 Пост удалён из очереди")
    else:
        await callback.answer("⚠️ Не удалось удалить", show_alert=True)
    await callback.message.delete()
    await _schedule_screen(callback, callback.from_user.id)


@router.callback_query(F.data == "sched:del_cancel")
async def cb_del_cancel(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer("Отмена")


# ── Enqueue post (called from generate.py via "⏰ В очередь") ─────────────────

@router.callback_query(F.data == "schedule:enqueue")
async def cb_enqueue(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    post_text = data.get("current_post", "")
    if not post_text:
        await callback.answer("❌ Нет текста поста", show_alert=True)
        return

    channel = await get_preference(user_id, "publish_channel")
    if not channel:
        await callback.answer("❌ Сначала настрой канал в ⚙️ Настройках", show_alert=True)
        return

    slot_dt = await next_free_slot(user_id)
    if slot_dt:
        dt_str = slot_dt.strftime("%Y-%m-%d %H:%M")
        display = slot_dt.strftime("%d %b %H:%M UTC")
        await callback.answer()
        await callback.message.answer(
            f"📅 Следующий свободный слот: *{display}*\nДобавить пост в очередь?",
            parse_mode="Markdown",
            reply_markup=schedule_confirm_kb(dt_str),
        )
        await state.update_data(pending_schedule_channel=channel)
    else:
        await callback.answer()
        await callback.message.answer(
            "⏰ Слоты не настроены или все заняты.\nВведи дату и время вручную:\n"
            "Примеры: `завтра в 10:00`, `08.04 15:30`",
            parse_mode="Markdown",
        )
        await state.set_state(SchedS.waiting_manual_time)
        await state.update_data(pending_schedule_channel=channel)


@router.callback_query(F.data.startswith("sched:confirm:"))
async def cb_confirm_enqueue(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    dt_str = callback.data.split("sched:confirm:")[1]
    try:
        scheduled_at = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        await callback.answer("❌ Ошибка даты", show_alert=True)
        return

    data = await state.get_data()
    post_text = data.get("current_post", "")
    topic = data.get("current_topic", "")
    channel = data.get("pending_schedule_channel", "")

    if not post_text or not channel:
        await callback.answer("❌ Нет данных для планирования", show_alert=True)
        return

    await add_to_queue(user_id, post_text, channel, scheduled_at, topic)
    display = scheduled_at.strftime("%d %b %H:%M UTC")
    await callback.answer(f"✅ Запланировано на {display}")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"⏰ Пост добавлен в очередь на *{display}*",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    await state.clear()


@router.callback_query(F.data == "sched:manual_time")
async def cb_manual_time(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer(
        "Введи дату и время:\nПримеры: `завтра в 10:00`, `08.04 15:30`, `09.04.2026 09:00`",
        parse_mode="Markdown",
    )
    await state.set_state(SchedS.waiting_manual_time)


@router.message(SchedS.waiting_manual_time)
async def handle_manual_time(message: Message, state: FSMContext) -> None:
    dt = _parse_datetime(message.text)
    if not dt:
        await message.answer(
            "❌ Не понял дату. Попробуй: `завтра в 10:00` или `08.04 15:30`",
            parse_mode="Markdown",
        )
        return
    if dt <= datetime.now(timezone.utc):
        await message.answer("❌ Это время уже прошло. Введи время в будущем.")
        return

    data = await state.get_data()
    post_text = data.get("current_post", "")
    topic = data.get("current_topic", "")
    channel = data.get("pending_schedule_channel", "")

    if not post_text or not channel:
        await message.answer("❌ Нет данных для планирования. Сгенерируй пост заново.")
        await state.clear()
        return

    await add_to_queue(message.from_user.id, post_text, channel, dt, topic)
    display = dt.strftime("%d %b %H:%M UTC")
    await message.answer(
        f"⏰ Пост добавлен в очередь на *{display}*",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    await state.clear()


@router.callback_query(F.data == "sched:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Отменено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(pending_schedule_channel=None)
