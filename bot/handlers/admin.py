"""Admin commands — only for bot owner."""
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.database import get_pool, get_admin_stats, get_token_stats

router = Router()

PAID_PLANS = ("basic", "standard", "pro")


def _is_admin(user_id: int) -> bool:
    allowed = settings.allowed_user_ids
    if allowed:
        return user_id in allowed
    return str(user_id) == str(getattr(settings, "admin_user_id", ""))


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    s = await get_admin_stats()

    text = (
        f"🛠 *Статистика бота*\n"
        f"_{datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC_\n\n"

        f"👥 *Пользователи*\n"
        f"Всего зарегистрировано: {s['total']}\n"
        f"⏳ Пробный период: {s['trial']}\n"
        f"🆓 Free (истёк пробный): {s['free']}\n"
        f"💳 Платных активных: *{s['paid_total']}*"
        f"  (⭐{s['p_basic']} / 💎{s['p_std']} / 🔥{s['p_pro']})\n"
        f"❌ Истёкших платных: {s['expired_paid']}\n\n"

        f"💰 *Выручка (₽)*\n"
        f"Сегодня: {s['rev_today']:,}₽\n"
        f"7 дней: {s['rev_week']:,}₽\n"
        f"30 дней: {s['rev_month']:,}₽\n"
        f"Всего: *{s['rev_total']:,}₽*\n\n"

        f"📊 *Конверсия trial→paid*\n"
        f"За 30 дней: {s['converted_30d']} из {s['registered_30d']} → *{s['conv_30d_rate']}%*\n"
        f"За всё время: {s['converted_total']} из {s['total']} → *{s['conv_total_rate']}%*\n\n"

        f"📝 *Активность*\n"
        f"Постов за 24ч: {s['posts_24h']}\n"
        f"Постов за 7 дней: {s['posts_7d']}\n"
        f"Изображений за 7 дней: {s['images_7d']}"
    )
    await message.answer(text.replace(",", " "), parse_mode="Markdown")


@router.message(Command("admin_tokens"))
async def cmd_admin_tokens(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    s = await get_token_stats()

    def _fmt(inp, out):
        return f"{(inp + out):,}  (in: {inp:,} / out: {out:,})".replace(",", " ")

    agent_lines = []
    for a in s["agents"]:
        short_model = a["model"].split("/")[-1] if "/" in a["model"] else a["model"]
        agent_lines.append(
            f"  `{a['agent']}` ({short_model}) — {a['calls']} вызовов, "
            f"{a['inp']+a['out']:,} токенов, ~{a['cost']:.2f}₽".replace(",", " ")
        )

    text = (
        f"🔢 *Токены и расходы*\n"
        f"_{datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC_\n\n"
        f"*За 24ч:*  {_fmt(s['in_24h'], s['out_24h'])}\n"
        f"Стоимость: ~*{s['cost_24h']:.2f}₽*\n\n"
        f"*За 7 дней:*  {_fmt(s['in_7d'], s['out_7d'])}\n"
        f"Стоимость: ~*{s['cost_7d']:.2f}₽*\n\n"
        f"*За всё время:*  {_fmt(s['in_all'], s['out_all'])}\n"
        f"Стоимость: ~*{s['cost_all']:.2f}₽*\n\n"
        f"*По агентам (7 дней):*\n"
        + ("\n".join(agent_lines) if agent_lines else "  нет данных")
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
            ORDER BY s.expires_at DESC NULLS LAST
            LIMIT 20
            """
        )

    if not rows:
        await message.answer("Нет пользователей.")
        return

    now = datetime.now(timezone.utc)
    plan_emoji = {"free": "🆓", "trial": "⏳", "basic": "⭐", "standard": "💎", "pro": "🔥"}
    lines = ["👥 *Пользователи* (последние 20)\n"]
    for r in rows:
        expires = r["expires_at"]
        if expires:
            from bot.database import _as_utc
            expires = _as_utc(expires)
            days = (expires - now).days
            days_str = f"{max(days, 0)}д"
            active = expires > now and r["status"] == "active"
        else:
            days_str = "—"
            active = False
        status = "✅" if active else "❌"
        emoji = plan_emoji.get(r["plan"], "❓")
        lines.append(
            f"{status} `{r['user_id']}` {emoji}{r['plan']} {days_str} · {r['post_count']} постов"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")
