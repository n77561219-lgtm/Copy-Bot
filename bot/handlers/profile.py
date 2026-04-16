"""User profile: subscription status, plan limits, monthly usage."""
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database import get_subscription, get_style_examples_count, get_monthly_usage, get_active_plan
from bot.keyboards import plans_kb
from bot.plans import get_plan, PAID_PLANS

router = Router()


def _profile_kb(plan_id: str) -> InlineKeyboardButton:
    b = InlineKeyboardBuilder()
    if plan_id in PAID_PLANS:
        b.row(InlineKeyboardButton(text="🔄 Продлить / сменить тариф", callback_data="subscribe"))
    else:
        b.row(InlineKeyboardButton(text="⬆️ Улучшить тариф", callback_data="subscribe"))
    b.row(InlineKeyboardButton(text="✕ Закрыть", callback_data="profile:close"))
    return b.as_markup()


async def _profile_text(user_id: int) -> tuple[str, str]:
    sub = await get_subscription(user_id)
    plan_id = await get_active_plan(user_id)
    plan = get_plan(plan_id)
    style_count = await get_style_examples_count(user_id)
    now = datetime.now(timezone.utc)

    # Plan line
    plan_line = f"📋 Тариф: {plan['emoji']} *{plan['name']}*"

    # Status + expiry
    if not sub or plan_id == "free":
        if sub and sub["plan"] == "trial":
            status_line = "❌ Пробный период истёк"
            expires_line = ""
        else:
            status_line = "✅ Активен (бесплатный)"
            expires_line = ""
    else:
        is_active = sub["status"] == "active" and (
            str(sub["expires_at"]) == "infinity" or sub["expires_at"] > now
        )
        days_left = max((sub["expires_at"] - now).days, 0) if str(sub["expires_at"]) != "infinity" else "∞"
        status_line = "✅ Активна" if is_active else "❌ Истекла"
        expires_line = f"\n📅 До: {sub['expires_at'].strftime('%d.%m.%Y')} ({days_left} дн.)" if is_active else ""

    # Usage this month
    posts_used = await get_monthly_usage(user_id, "post_generated")
    images_used = await get_monthly_usage(user_id, "image_generated")
    posts_limit = plan["posts_per_month"]
    images_limit = plan["images_per_month"]

    posts_str = f"{posts_used}/{posts_limit}" if posts_limit else f"{posts_used}/∞"
    images_str = f"{images_used}/{images_limit}" if images_limit else f"{images_used}/∞"

    style_line = f"🎨 Примеров стиля: {style_count}" if style_count else "🎨 Стиль не загружен"

    text = (
        f"👤 *Твой профиль*\n\n"
        f"{plan_line}\n"
        f"Статус: {status_line}"
        f"{expires_line}\n\n"
        f"📊 Использовано в этом месяце:\n"
        f"  • Постов: {posts_str}\n"
        f"  • Картинок: {images_str}\n\n"
        f"{style_line}"
    )
    return text, plan_id


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    text, plan_id = await _profile_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=_profile_kb(plan_id))


@router.message(F.text == "👤 Профиль")
async def menu_profile(message: Message) -> None:
    text, plan_id = await _profile_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=_profile_kb(plan_id))


@router.callback_query(F.data == "profile:close")
async def cb_profile_close(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "subscription_info")
async def cb_subscription_info(callback: CallbackQuery) -> None:
    text, plan_id = await _profile_text(callback.from_user.id)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=_profile_kb(plan_id))
    await callback.answer()
