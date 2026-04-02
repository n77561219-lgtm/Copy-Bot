"""Admin commands — only for bot owner."""
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.database import get_pool

router = Router()


def _is_admin(user_id: int) -> bool:
    allowed = settings.allowed_user_ids
    if allowed:
        return user_id in allowed
    # if no whitelist, check ADMIN_USER_ID env
    return str(user_id) == str(getattr(settings, "admin_user_id", ""))


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    async with get_pool().acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM subscriptions")
        trial_users = await conn.fetchval("SELECT COUNT(*) FROM subscriptions WHERE plan='trial' AND status='active'")
        paid_users  = await conn.fetchval("SELECT COUNT(*) FROM subscriptions WHERE plan='paid' AND status='active'")
        expired     = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE expires_at < $1", datetime.now(timezone.utc)
        )
        posts_today = await conn.fetchval(
            "SELECT COUNT(*) FROM posts WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )
        posts_week  = await conn.fetchval(
            "SELECT COUNT(*) FROM posts WHERE created_at >= NOW() - INTERVAL '7 days'"
        )

    text = (
        f"🛠 *Статистика бота*\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"⏳ На пробном периоде: {trial_users}\n"
        f"💳 Платных подписок: {paid_users}\n"
        f"❌ Истёкших: {expired}\n\n"
        f"📝 Постов за 24 часа: {posts_today}\n"
        f"📝 Постов за 7 дней: {posts_week}"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("admin_users"))
async def cmd_admin_users(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.user_id, s.plan, s.status, s.expires_at,
                   COUNT(p.id) AS post_count
            FROM subscriptions s
            LEFT JOIN posts p ON p.user_id = s.user_id
            GROUP BY s.user_id, s.plan, s.status, s.expires_at
            ORDER BY s.expires_at DESC
            LIMIT 20
            """
        )

    if not rows:
        await message.answer("Нет пользователей.")
        return

    now = datetime.now(timezone.utc)
    lines = ["👥 *Пользователи* (последние 20)\n"]
    for r in rows:
        days = (r["expires_at"] - now).days
        status = "✅" if r["status"] == "active" and r["expires_at"] > now else "❌"
        plan = "trial" if r["plan"] == "trial" else "paid"
        lines.append(f"{status} `{r['user_id']}` — {plan}, {max(days,0)}д, {r['post_count']} постов")

    await message.answer("\n".join(lines), parse_mode="Markdown")
