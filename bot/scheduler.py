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
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_MINUTES = 5
POLL_INTERVAL = 60  # seconds


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
