"""Referral system handler.

Invite link format: https://t.me/BotUsername?start=ref_<user_id>
When a new user clicks the link, /start is called with payload "ref_<user_id>".

Rewards:
- Inviter:  +5 days per referral  (BONUS_DAYS)
- Invited:  +3 days to trial      (INVITED_BONUS_DAYS, applied in start.py)
- Milestone 3 refs  → +14 extra days
- Milestone 5 refs  → +30 extra days
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database import (
    register_referral, give_referral_bonus, get_referral_stats, get_subscription,
    extend_subscription_days, count_successful_referrals,
)
from bot.config import settings

router = Router()

BONUS_DAYS = 5
INVITED_BONUS_DAYS = 3

# milestone: {ref_count: bonus_days}
MILESTONES = {3: 14, 5: 30}
_MILESTONE_ORDER = sorted(MILESTONES)


def _progress_bar(current: int, target: int, width: int = 6) -> str:
    filled = min(int(current / target * width), width)
    return "█" * filled + "░" * (width - filled)


def _milestone_lines(refs_done: int) -> list[str]:
    lines = []
    for m in _MILESTONE_ORDER:
        bonus = MILESTONES[m]
        if refs_done >= m:
            lines.append(f"✅ {m} реферала → +{bonus} дней — *получено!*")
        else:
            bar = _progress_bar(refs_done, m)
            left = m - refs_done
            lines.append(f"⬜ {m} реферала → +{bonus} дней\n   [{bar}] осталось {left}")
    return lines


async def process_referral_start(inviter_id: int, new_user_id: int, bot) -> None:
    """Called from start handler when payload starts with 'ref_'.
    Registers the referral and gives the inviter their per-ref bonus + milestone if earned.
    The +3 days for the invited user is applied in start.py after create_trial().
    """
    is_new = await register_referral(inviter_id, new_user_id)
    if not is_new:
        return

    sub = await get_subscription(new_user_id)
    if not sub:
        return

    given = await give_referral_bonus(inviter_id, new_user_id)
    if not given:
        return

    count = await count_successful_referrals(inviter_id)

    milestone_msg = ""
    if count in MILESTONES:
        bonus = MILESTONES[count]
        await extend_subscription_days(inviter_id, bonus)
        milestone_msg = (
            f"\n\n🏆 *Рубеж {count} рефералов!*\n"
            f"Дополнительно +{bonus} дней к подписке — уже начислено!"
        )

    try:
        await bot.send_message(
            inviter_id,
            f"🎉 По твоей ссылке зарегистрировался новый пользователь!\n"
            f"+{BONUS_DAYS} дней к подписке — уже начислено."
            + milestone_msg,
            parse_mode="Markdown",
        )
    except Exception:
        pass


@router.message(Command("referral"))
async def cmd_referral(message: Message) -> None:
    await _show_referral(message)


@router.message(F.text == "👥 Рефералы")
async def menu_referral(message: Message) -> None:
    await _show_referral(message)


async def _show_referral(message: Message) -> None:
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username

    stats = await get_referral_stats(user_id)
    refs_done = stats["bonuses_earned"]
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    total_days = refs_done * BONUS_DAYS + sum(
        MILESTONES[m] for m in _MILESTONE_ORDER if refs_done >= m
    )

    milestone_block = "\n".join(_milestone_lines(refs_done))

    text = (
        f"👥 *Реферальная программа*\n\n"
        f"Приглашай друзей — и ты, и они получат бонусные дни!\n\n"
        f"Твоя ссылка:\n`{link}`\n\n"
        f"📊 *Статистика:*\n"
        f"Приглашено: {stats['total']}\n"
        f"Начислено бонусов: {refs_done} × {BONUS_DAYS} дн."
        + (f" + milestone = *{total_days} дн. итого*" if total_days else "") +
        f"\n\n🏆 *Рубежи:*\n"
        f"{milestone_block}\n\n"
        f"За каждого друга:\n"
        f"├ Тебе: *+{BONUS_DAYS} дней* к подписке\n"
        f"└ Другу: *+{INVITED_BONUS_DAYS} дня* к пробному периоду "
        f"({5 + INVITED_BONUS_DAYS} вместо 5)"
    )

    share_text = (
        f"Попробуй КопиБОТ — пишет посты в твоём стиле за 30 секунд. "
        f"По моей ссылке получишь расширенный пробный период:"
    )
    import urllib.parse
    share_url = (
        f"https://t.me/share/url"
        f"?url={urllib.parse.quote(link, safe='')}"
        f"&text={urllib.parse.quote(share_text, safe='')}"
    )

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 Поделиться", url=share_url))

    await message.answer(text, parse_mode="Markdown", reply_markup=b.as_markup())
