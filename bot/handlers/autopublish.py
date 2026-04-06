"""Auto-publish posts to a Telegram channel.

User sets their channel username once (e.g. @mychannel or -100xxxxxxxxx).
After connecting the channel the bot asks for timezone and schedule slots.
"""
import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from bot.database import (
    get_preference, set_preference,
    add_schedule_slot, get_schedule_slots,
)

router = Router()

# Popular timezones for Russian-speaking audience
_TIMEZONES = [
    ("UTC+0",  0,  "UTC"),
    ("UTC+1",  1,  "Центральная Европа"),
    ("UTC+2",  2,  "Восточная Европа"),
    ("UTC+3",  3,  "Москва (МСК)"),
    ("UTC+5",  5,  "Екатеринбург"),
    ("UTC+6",  6,  "Омск"),
    ("UTC+7",  7,  "Красноярск"),
    ("UTC+8",  8,  "Иркутск"),
    ("UTC+10", 10, "Владивосток"),
    ("UTC+12", 12, "Камчатка"),
]


class PublishStates(StatesGroup):
    waiting_channel        = State()
    waiting_timezone       = State()
    waiting_schedule_slots = State()


def _timezone_kb():
    b = InlineKeyboardBuilder()
    for label, offset, city in _TIMEZONES:
        b.row(InlineKeyboardButton(
            text=f"{label} — {city}",
            callback_data=f"tz:set:{offset}",
        ))
    b.row(InlineKeyboardButton(text="✍️ Ввести вручную (UTC±N)", callback_data="tz:manual"))
    b.row(InlineKeyboardButton(text="⏭ Пропустить", callback_data="tz:skip"))
    return b.as_markup()


def _local_to_utc(time_str: str, offset: int) -> str | None:
    """Convert HH:MM local time to HH:MM UTC using offset (hours)."""
    m = re.match(r"(\d{1,2}):(\d{2})", time_str.strip())
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mn <= 59):
        return None
    h_utc = (h - offset) % 24
    return f"{h_utc:02d}:{mn:02d}"


async def get_channel(user_id: int) -> str | None:
    return await get_preference(user_id, "publish_channel")


async def get_timezone_offset(user_id: int) -> int:
    """Return stored UTC offset (hours), default 0."""
    val = await get_preference(user_id, "timezone_offset")
    try:
        return int(val) if val is not None else 0
    except ValueError:
        return 0


# ── Entry points ──────────────────────────────────────────────────────────────

@router.message(Command("channel"))
async def cmd_channel(message: Message, state: FSMContext) -> None:
    await _ask_channel(message, state)


@router.callback_query(F.data == "settings:setup_channel")
async def cb_setup_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _ask_channel(callback.message, state, user_id=callback.from_user.id)


async def _ask_channel(message: Message, state: FSMContext, user_id: int | None = None) -> None:
    from bot.database import get_preference
    uid = user_id or message.from_user.id if hasattr(message, 'from_user') and message.from_user else message.chat.id
    channel = await get_preference(uid, "publish_channel")
    current = f"Текущий канал: `{channel}`\n\n" if channel else ""
    await message.answer(
        f"{current}"
        "Шаг 1/3 — Отправь username канала:\n\n"
        "Формат: `@mychannel` или `-1001234567890`\n\n"
        "⚠️ Бот должен быть **администратором** канала с правом публикации.",
        parse_mode="Markdown",
    )
    await state.set_state(PublishStates.waiting_channel)


# ── Step 1: channel ───────────────────────────────────────────────────────────

@router.message(PublishStates.waiting_channel)
async def handle_channel_input(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    user_id = message.from_user.id
    try:
        test = await message.bot.send_message(text, "✅ Канал подключён к Copy-Bot!")
        await test.delete()
        await set_preference(user_id, "publish_channel", text)
        await state.update_data(channel=text)
        await message.answer(
            f"✅ Канал *{text}* подключён!\n\n"
            "Шаг 2/3 — Выбери свой часовой пояс:",
            parse_mode="Markdown",
            reply_markup=_timezone_kb(),
        )
        await state.set_state(PublishStates.waiting_timezone)
    except TelegramForbiddenError:
        await message.answer(
            "❌ Бот не может отправить сообщение в этот канал.\n\n"
            "Добавь бота как администратора канала с правом публикации постов."
        )
    except TelegramBadRequest as e:
        await message.answer(f"❌ Неверный chat ID: {e}\n\nПроверь username канала.")


# ── Step 2: timezone ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tz:set:"))
async def cb_tz_set(callback: CallbackQuery, state: FSMContext) -> None:
    offset = int(callback.data.split("tz:set:")[1])
    user_id = callback.from_user.id
    await set_preference(user_id, "timezone_offset", str(offset))
    await state.update_data(tz_offset=offset)
    sign = "+" if offset >= 0 else ""
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Часовой пояс UTC{sign}{offset} сохранён.\n\n"
        "Шаг 3/3 — В какое время публиковать?\n"
        "Введи одно или несколько значений через запятую:\n"
        "`10:00, 18:00`\n\n"
        "Или /skip чтобы пропустить.",
        parse_mode="Markdown",
    )
    await state.set_state(PublishStates.waiting_schedule_slots)
    await callback.answer()


@router.callback_query(F.data == "tz:manual")
async def cb_tz_manual(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Введи смещение UTC вручную.\nПример: `3` для UTC+3, `-5` для UTC-5",
        parse_mode="Markdown",
    )
    await state.set_state(PublishStates.waiting_timezone)


@router.message(PublishStates.waiting_timezone)
async def handle_timezone_input(message: Message, state: FSMContext) -> None:
    text = message.text.strip().lstrip("+")
    try:
        offset = int(text)
        if not (-12 <= offset <= 14):
            raise ValueError
    except ValueError:
        await message.answer("❌ Неверный формат. Введи число от -12 до 14, например `3`")
        return
    await set_preference(message.from_user.id, "timezone_offset", str(offset))
    await state.update_data(tz_offset=offset)
    sign = "+" if offset >= 0 else ""
    await message.answer(
        f"✅ Часовой пояс UTC{sign}{offset} сохранён.\n\n"
        "Шаг 3/3 — В какое время публиковать?\n"
        "Введи время через запятую: `10:00, 18:00`\n\n"
        "Или /skip чтобы пропустить.",
        parse_mode="Markdown",
    )
    await state.set_state(PublishStates.waiting_schedule_slots)


@router.callback_query(F.data == "tz:skip")
async def cb_tz_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _finish_setup(callback.message, callback.from_user.id, state, skipped_tz=True)


# ── Step 3: schedule slots ────────────────────────────────────────────────────

@router.message(PublishStates.waiting_schedule_slots)
async def handle_slots_input(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() in ("/skip", "skip", "пропустить"):
        await _finish_setup(message, message.from_user.id, state)
        return

    user_id = message.from_user.id
    data = await state.get_data()
    offset = data.get("tz_offset", await get_timezone_offset(user_id))

    parts = re.split(r"[,\s]+", message.text.strip())
    saved, skipped = [], []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        utc_time = _local_to_utc(part, offset)
        if utc_time:
            await add_schedule_slot(user_id, utc_time)
            saved.append(part)
        else:
            skipped.append(part)

    if not saved:
        await message.answer(
            "❌ Не удалось распознать время. Введи в формате HH:MM, например `10:00, 18:00`"
        )
        return

    await _finish_setup(message, user_id, state, slots_added=saved, slots_skipped=skipped)


async def _finish_setup(
    message: Message,
    user_id: int,
    state: FSMContext,
    slots_added: list[str] | None = None,
    slots_skipped: list[str] | None = None,
    skipped_tz: bool = False,
) -> None:
    from bot.keyboards import main_menu
    data = await state.get_data()
    channel = data.get("channel") or await get_preference(user_id, "publish_channel") or "—"
    offset = data.get("tz_offset", await get_timezone_offset(user_id))
    slots = await get_schedule_slots(user_id)
    sign = "+" if offset >= 0 else ""

    lines = [
        "🎉 *Канал настроен!*\n",
        f"📢 Канал: `{channel}`",
        f"🕐 Часовой пояс: UTC{sign}{offset}" + (" (по умолчанию)" if skipped_tz else ""),
        f"⏰ Слоты публикации (UTC): {', '.join(slots) if slots else 'не настроены'}",
    ]
    if slots_added:
        lines.append(f"\n✅ Добавлены слоты: {', '.join(slots_added)}")
    if slots_skipped:
        lines.append(f"⚠️ Не распознаны: {', '.join(slots_skipped)}")

    lines.append("\nТеперь после генерации поста можно нажать «⏰ В очередь» или «📢 Опубликовать сейчас».")

    await state.clear()
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=main_menu())


@router.callback_query(F.data.startswith("publish:channel:"))
async def cb_publish_to_channel(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    post_text = callback.data[len("publish:channel:"):]

    # post_text is stored in FSM data, not callback (too long)
    # We use state data via a workaround: store in preferences temporarily
    channel = await get_channel(user_id)
    if not channel:
        await callback.answer("Канал не настроен. Используй /channel", show_alert=True)
        return

    stored = await get_preference(user_id, "pending_publish_text")
    if not stored:
        await callback.answer("Текст поста не найден.", show_alert=True)
        return

    try:
        await callback.bot.send_message(channel, stored, parse_mode="Markdown")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Опубликовано в {channel}!")
    except Exception as e:
        await callback.answer(f"Ошибка публикации: {e}", show_alert=True)

    await callback.answer()


def publish_kb(has_channel: bool) -> InlineKeyboardBuilder | None:
    if not has_channel:
        return None
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📢 Опубликовать в канал", callback_data="publish:channel:go"))
    return b.as_markup()
