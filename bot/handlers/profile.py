"""User profile and subscription status handler."""
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from bot.database import get_subscription, get_style_examples_count
from bot.keyboards import subscribe_kb

router = Router()


def _profile_kb(has_active_sub: bool) -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    if not has_active_sub:
        b.row(InlineKeyboardButton(text="💳 Оформить подписку — 490 Stars", callback_data="subscribe"))
    else:
        b.row(InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="subscribe"))
    return b.as_markup()


async def _profile_text(user_id: int) -> tuple[str, bool]:
    sub = await get_subscription(user_id)
    style_count = await get_style_examples_count(user_id)
    now = datetime.now(timezone.utc)

    if not sub:
        plan_line = "📋 Подписка: не оформлена"
        status_line = "❌ Нет доступа"
        expires_line = ""
        active = False
    else:
        is_active = sub["status"] == "active" and sub["expires_at"] > now
        days_left = max((sub["expires_at"] - now).days, 0)

        plan_name = "Пробный период" if sub["plan"] == "trial" else "Платная подписка"
        plan_line = f"📋 Тариф: {plan_name}"
        status_line = f"{'✅ Активна' if is_active else '❌ Истекла'}"
        expires_line = f"\n📅 До: {sub['expires_at'].strftime('%d.%m.%Y')} ({days_left} дн.)"
        active = is_active

    style_line = f"🎨 Примеров стиля: {style_count}" if style_count else "🎨 Стиль не загружен"

    text = (
        f"👤 *Твой профиль*\n\n"
        f"{plan_line}\n"
        f"Статус: {status_line}"
        f"{expires_line}\n\n"
        f"{style_line}"
    )
    return text, active


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    text, active = await _profile_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=_profile_kb(active))


@router.message(F.text == "👤 Профиль")
async def menu_profile(message: Message) -> None:
    text, active = await _profile_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=_profile_kb(active))


@router.callback_query(F.data == "subscription_info")
async def cb_subscription_info(callback: CallbackQuery) -> None:
    text, active = await _profile_text(callback.from_user.id)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=_profile_kb(active))
    await callback.answer()
