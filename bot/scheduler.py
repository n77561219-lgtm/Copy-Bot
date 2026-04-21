"""Background scheduler: publishes queued posts when their time comes."""
import asyncio
import logging

from aiogram import Bot

from bot.database import (
    get_due_scheduled_posts,
    mark_scheduled_published,
    mark_scheduled_failed,
    increment_scheduled_attempts,
    reschedule_post,
    is_queue_paused,
    get_expiring_subscriptions,
    mark_renewal_notified,
    get_preference,
)
from bot.plans import get_plan, PLANS

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_MINUTES = 5
POLL_INTERVAL = 60        # seconds
RENEWAL_INTERVAL = 3600   # check renewals every hour
RENEWAL_DAYS = [3, 1, 0]  # notify 3 days, 1 day, and day-of expiry


async def scheduler_loop(bot: Bot) -> None:
    """Runs forever, checks for due posts every POLL_INTERVAL seconds."""
    logger.info("Scheduler started")
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            await _process_due_posts(bot)
        except Exception as e:
            logger.error("Scheduler loop error: %s", e)


async def _process_due_posts(bot: Bot) -> None:
    posts = await get_due_scheduled_posts()
    for post in posts:
        if await is_queue_paused(post["user_id"]):
            continue
        try:
            await bot.send_message(post["channel_id"], post["content"])
            await mark_scheduled_published(post["id"])
            logger.info("Published scheduled post %s for user %s", post["id"], post["user_id"])
        except Exception as e:
            attempts = post["attempts"] + 1
            err_text = str(e)[:500]
            if attempts >= MAX_ATTEMPTS:
                await mark_scheduled_failed(post["id"], err_text)
                logger.warning("Post %s failed after %s attempts: %s", post["id"], attempts, err_text)
                try:
                    topic = post.get("topic") or "без темы"
                    await bot.send_message(
                        post["user_id"],
                        f"❌ Не удалось опубликовать пост «{topic}»\n"
                        f"Ошибка: {err_text[:200]}\n\n"
                        "Пост перенесён в статус «failed». Удали его из очереди и попробуй снова.",
                    )
                except Exception:
                    pass
            else:
                await increment_scheduled_attempts(post["id"], attempts, err_text)
                await reschedule_post(post["id"], RETRY_MINUTES)
                logger.warning("Post %s attempt %s failed, retry in %sm", post["id"], attempts, RETRY_MINUTES)


async def renewal_notification_loop(bot: Bot) -> None:
    """Runs forever, sends subscription renewal reminders at 3d / 1d / 0d before expiry."""
    logger.info("Renewal notification loop started")
    while True:
        await asyncio.sleep(RENEWAL_INTERVAL)
        try:
            await _send_renewal_notifications(bot)
        except Exception as e:
            logger.error("Renewal notification loop error: %s", e)


async def _send_renewal_notifications(bot: Bot) -> None:
    for days in RENEWAL_DAYS:
        subs = await get_expiring_subscriptions(days)
        for sub in subs:
            user_id = sub["user_id"]
            plan = get_plan(sub["plan"])
            expires = _as_utc(sub["expires_at"]).strftime("%d.%m.%Y")

            if days == 0:
                text = (
                    f"🔴 *Подписка истекает сегодня!*\n\n"
                    f"Тариф {plan['emoji']} *{plan['name']}* заканчивается {expires}.\n"
                    f"После истечения доступ перейдёт на бесплатный тариф (5 постов/мес).\n\n"
                    f"Продли подписку, чтобы не терять доступ:"
                )
            elif days == 1:
                text = (
                    f"🟡 *Подписка заканчивается завтра*\n\n"
                    f"Тариф {plan['emoji']} *{plan['name']}* действует до {expires}.\n\n"
                    f"Продли сейчас — это займёт 10 секунд:"
                )
            else:
                text = (
                    f"🟢 *Напоминание о подписке*\n\n"
                    f"Тариф {plan['emoji']} *{plan['name']}* действует до {expires} (осталось {days} дня).\n\n"
                    f"Продли заранее, чтобы не прерывать работу:"
                )

            try:
                auto_renew = await get_preference(user_id, "auto_renew") == "1"

                if auto_renew and days <= 1:
                    # Автосписание запустится в auto_renewal_loop — просто напоминаем
                    await bot.send_message(user_id, text, parse_mode="Markdown")
                else:
                    from bot.keyboards import plans_kb
                    await bot.send_message(
                        user_id, text,
                        parse_mode="Markdown",
                        reply_markup=plans_kb(sub["plan"]),
                    )

                await mark_renewal_notified(user_id, days)
                logger.info("Sent renewal notice (%dd, auto_renew=%s) to user %s", days, auto_renew, user_id)
            except Exception as e:
                logger.warning("Failed to send renewal notice to %s: %s", user_id, e)


def _as_utc(dt):
    from datetime import timezone
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
