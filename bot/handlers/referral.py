"""Referral system handler.

Invite link format: https://t.me/BotUsername?start=ref_<user_id>
When a new user clicks the link, /start is called with payload "ref_<user_id>".
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from bot.database import register_referral, give_referral_bonus, get_referral_stats, create_trial, get_subscription
from bot.config import settings

router = Router()

BONUS_DAYS = 7


async def process_referral_start(inviter_id: int, new_user_id: int, bot) -> None:
    """Called from start handler when payload starts with 'ref_'."""
    is_new = await register_referral(inviter_id, new_user_id)
    if not is_new:
        return

    # Check if new user already has active sub — if so, give bonus immediately
    sub = await get_subscription(new_user_id)
    if sub:
        given = await give_referral_bonus(inviter_id, new_user_id)
        if given:
            try:
                await bot.send_message(
                    inviter_id,
                    f"🎉 По твоей ссылке зарегистрировался новый пользователь!\n"
                    f"+{BONUS_DAYS} дней к подписке — уже начислено.",
                )
            except Exception:
                pass


@router.message(Command("referral"))
async def cmd_referral(message: Message) -> None:
    user_id = message.from_user.id
    bot = message.bot
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    stats = await get_referral_stats(user_id)
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        f"👥 *Реферальная программа*\n\n"
        f"Приглашай друзей — получай +{BONUS_DAYS} дней к подписке за каждого.\n\n"
        f"Твоя ссылка:\n`{link}`\n\n"
        f"📊 Приглашено: {stats['total']}\n"
        f"🎁 Бонусов получено: {stats['bonuses_earned']} × {BONUS_DAYS} дн."
    )

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📋 Скопировать ссылку", switch_inline_query=link))

    await message.answer(text, parse_mode="Markdown", reply_markup=b.as_markup())


@router.message(F.text == "👥 Рефералы")
async def menu_referral(message: Message) -> None:
    await cmd_referral(message)
