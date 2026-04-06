from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database import get_preference, set_preference
from bot.keyboards import main_menu

router = Router()

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULTS = {
    "post_length":   "medium",   # short | medium | long
    "show_score":    "yes",      # yes | no
    "critic_iters":  "2",        # 1 | 2
}

_LENGTH_LABELS  = {"short": "Короткий (50-80 сл.)", "medium": "Стандартный (100-200 сл.)", "long": "Длинный (200-350 сл.)"}
_SCORE_LABELS   = {"yes": "Показывать ✅", "no": "Скрыть ❌"}
_ITERS_LABELS   = {"1": "1 проход", "2": "2 прохода"}


async def get_setting(user_id: int, key: str) -> str:
    val = await get_preference(user_id, key)
    return val if val is not None else DEFAULTS[key]


# ── Keyboard ───────────────────────────────────────────────────────────────────

async def settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    length  = await get_setting(user_id, "post_length")
    score   = await get_setting(user_id, "show_score")
    iters   = await get_setting(user_id, "critic_iters")

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text=f"📏 Длина поста: {_LENGTH_LABELS[length]}",
        callback_data="settings:length:cycle"
    ))
    b.row(InlineKeyboardButton(
        text=f"📊 Оценка качества: {_SCORE_LABELS[score]}",
        callback_data="settings:score:cycle"
    ))
    b.row(InlineKeyboardButton(
        text=f"🔄 Итерации правки: {_ITERS_LABELS[iters]}",
        callback_data="settings:iters:cycle"
    ))
    channel = await get_preference(user_id, "publish_channel")
    channel_label = f"🔗 Канал: {channel}" if channel else "🔗 Подключить канал"
    b.row(InlineKeyboardButton(text=channel_label, callback_data="settings:setup_channel"))
    b.row(InlineKeyboardButton(text="↩️ Назад", callback_data="settings:close"))
    return b.as_markup()


async def _show_settings(message: Message) -> None:
    user_id = message.from_user.id
    await message.answer(
        "⚙️ Настройки\n\nНажми на параметр чтобы изменить:",
        reply_markup=await settings_keyboard(user_id),
    )


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(F.text == "⚙️ Настройки")
async def menu_settings(message: Message) -> None:
    await _show_settings(message)


@router.callback_query(F.data == "settings:length:cycle")
async def cb_length(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    order = ["short", "medium", "long"]
    current = await get_setting(user_id, "post_length")
    next_val = order[(order.index(current) + 1) % len(order)]
    await set_preference(user_id, "post_length", next_val)
    await callback.message.edit_reply_markup(reply_markup=await settings_keyboard(user_id))
    await callback.answer(f"Длина: {_LENGTH_LABELS[next_val]}")


@router.callback_query(F.data == "settings:score:cycle")
async def cb_score(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    order = ["yes", "no"]
    current = await get_setting(user_id, "show_score")
    next_val = order[(order.index(current) + 1) % len(order)]
    await set_preference(user_id, "show_score", next_val)
    await callback.message.edit_reply_markup(reply_markup=await settings_keyboard(user_id))
    await callback.answer(f"Оценка: {_SCORE_LABELS[next_val]}")


@router.callback_query(F.data == "settings:iters:cycle")
async def cb_iters(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    order = ["1", "2"]
    current = await get_setting(user_id, "critic_iters")
    next_val = order[(order.index(current) + 1) % len(order)]
    await set_preference(user_id, "critic_iters", next_val)
    await callback.message.edit_reply_markup(reply_markup=await settings_keyboard(user_id))
    await callback.answer(f"Итерации: {_ITERS_LABELS[next_val]}")


@router.callback_query(F.data == "settings:close")
async def cb_close(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()
    await callback.message.answer("Настройки сохранены.", reply_markup=main_menu())
