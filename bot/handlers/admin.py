"""Admin commands — only for bot owner."""
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import settings
from bot.database import get_pool, get_admin_stats, get_token_stats, get_user_refund_summary

router = Router()

PAID_PLANS = ("basic", "standard", "pro")


class AdminRefundState(StatesGroup):
    waiting_user_id = State()


def _admin_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔢 Токены", callback_data="adm:tokens"),
        InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users"),
    )
    b.row(
        InlineKeyboardButton(text="💰 Возврат", callback_data="adm:refund"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:refresh"),
    )
    return b.as_markup()


def _is_admin(user_id: int) -> bool:
    allowed = settings.allowed_user_ids
    if allowed:
        return user_id in allowed
    return str(user_id) == str(getattr(settings, "admin_user_id", ""))


async def _admin_stats_text() -> str:
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
    return text.replace(",", " ")


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    text = await _admin_stats_text()
    await message.answer(text, parse_mode="Markdown", reply_markup=_admin_kb())


@router.callback_query(F.data == "adm:refresh")
async def cb_adm_refresh(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    text = await _admin_stats_text()
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=_admin_kb())
    await callback.answer("Обновлено")


@router.callback_query(F.data == "adm:tokens")
async def cb_adm_tokens(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    text = await _tokens_text()
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "adm:users")
async def cb_adm_users(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    text = await _users_text()
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "adm:refund")
async def cb_adm_refund(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await state.set_state(AdminRefundState.waiting_user_id)
    await callback.message.answer("Введи user_id пользователя для расчёта возврата:")
    await callback.answer()


@router.message(AdminRefundState.waiting_user_id)
async def adm_refund_user_id(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not message.text or not message.text.lstrip("-").isdigit():
        await message.answer("Неверный user_id")
        return
    target_id = int(message.text.strip())
    text = await _refund_text(target_id)
    await message.answer(text, parse_mode="Markdown")


def _as_utc_str(dt) -> str:
    from bot.database import _as_utc
    if dt is None:
        return "—"
    return _as_utc(dt).strftime("%d.%m.%Y %H:%M")


async def _tokens_text() -> str:
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

    return (
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


async def _refund_text(target_id: int) -> str:
    s = await get_user_refund_summary(target_id)
    if not s["sub"]:
        return f"❌ Пользователь `{target_id}` не найден в базе."

    sub = s["sub"]
    payment = s["payment"]
    counts = s["counts"]
    plan_label = sub["plan"].capitalize()
    expires_str = _as_utc_str(sub["expires_at"])
    paid_str = _as_utc_str(payment["created_at"]) if payment else "—"
    price_str = f"{payment['amount_rub']} ₽" if payment else "—"

    action_labels = {
        "post_generated": "Постов", "plan_generated": "Контент-планов",
        "style_analyzed": "Анализов стиля", "post_edited": "Правок",
        "image_generated": "Изображений",
    }
    usage_lines = []
    for action, label in action_labels.items():
        cnt = counts.get(action, 0)
        if cnt:
            from bot.database import _REFUND_RATES
            price = _REFUND_RATES.get(action, 0)
            cost_str = f" × {price} ₽ = {cnt * price} ₽" if price else ""
            usage_lines.append(f"  {label}: {cnt}{cost_str}")
    if not usage_lines:
        usage_lines = ["  нет использования"]

    return (
        f"🧾 *Расчёт возврата — user `{target_id}`*\n\n"
        f"Тариф: *{plan_label}*\n"
        f"Оплата: {paid_str} — {price_str}\n"
        f"Действует до: {expires_str}\n\n"
        f"*Использование с момента оплаты:*\n"
        + "\n".join(usage_lines) + "\n\n"
        f"Использовано: *{s['used_rub']} ₽*\n\n"
        f"💰 *К возврату: {s['refund']} ₽*"
    )


async def _users_text() -> str:
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
        return "Нет пользователей."

    from bot.database import _as_utc
    now = datetime.now(timezone.utc)
    plan_emoji = {"free": "🆓", "trial": "⏳", "basic": "⭐", "standard": "💎", "pro": "🔥"}
    lines = ["👥 *Пользователи* (последние 20)\n"]
    for r in rows:
        expires = r["expires_at"]
        if expires:
            expires = _as_utc(expires)
            days = (expires - now).days
            days_str = f"{max(days, 0)}д"
            active = expires > now and r["status"] == "active"
        else:
            days_str = "—"
            active = False
        status = "✅" if active else "❌"
        emoji = plan_emoji.get(r["plan"], "❓")
        lines.append(f"{status} `{r['user_id']}` {emoji}{r['plan']} {days_str} · {r['post_count']} постов")
    return "\n".join(lines)


@router.message(Command("admin_tokens"))
async def cmd_admin_tokens(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer(await _tokens_text(), parse_mode="Markdown")


@router.message(Command("admin_refund"))
async def cmd_admin_refund(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /admin_refund <user_id>")
        return
    await message.answer(await _refund_text(int(parts[1])), parse_mode="Markdown")


@router.message(Command("admin_users"))
async def cmd_admin_users(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer(await _users_text(), parse_mode="Markdown")
