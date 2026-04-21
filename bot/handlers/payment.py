"""ЮКасса payment handler — monthly/annual plans with auto-renew consent."""
import uuid
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
)

from aiogram.filters import Command

from bot.yookassa_client import create_payment as yk_create_payment
from bot.database import activate_subscription, get_subscription, log_usage, set_preference, get_preference, record_payment
from bot.keyboards import main_menu, plans_kb, checkout_kb, cancel_confirm_kb, refund_kb, payment_link_kb, MENU_PLANS
from bot.plans import PLANS, PAID_PLANS
from bot.config import settings

logger = logging.getLogger(__name__)

router = Router()


# ── 💎 Тарифы (reply-keyboard button) ────────────────────────────────────────

@router.message(F.text == MENU_PLANS)
async def menu_plans(message: Message) -> None:
    """Show plan comparison and subscribe button."""
    from datetime import datetime, timezone
    user_id = message.from_user.id
    sub = await get_subscription(user_id)
    current_plan = sub["plan"] if sub and sub["expires_at"] > datetime.now(timezone.utc) else ""

    lines = ["💎 *Тарифы Контент-мейкера*\n"]
    for plan_id in ["free"] + PAID_PLANS:
        p = PLANS[plan_id]
        price = "бесплатно" if p["price_rub"] == 0 else f"{p['price_rub']}₽/мес · {p['price_rub_year']}₽/год"
        mark = " ✅ *текущий*" if plan_id == current_plan else ""
        lines.append(f"{p['emoji']} *{p['name']}*{mark} — {price}\n{p['description']}\n")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=plans_kb(current_plan=current_plan, period="month"),
    )


# ── /refund ───────────────────────────────────────────────────────────────────

@router.message(Command("refund"))
async def cmd_refund(message: Message) -> None:
    """Show refund instructions with support link and policy."""
    await message.answer(
        "💰 *Возврат средств*\n\n"
        "Мы вернём деньги за неиспользованные дни подписки.\n\n"
        "*Стандартные случаи* — решение за 5 рабочих дней\n"
        "*Спорные ситуации* — до 10 рабочих дней\n"
        "*Двойное списание* — до 3 рабочих дней\n\n"
        "Напишите в поддержку и укажите:\n"
        "• Telegram-профиль\n"
        "• Дату и сумму платежа\n"
        "• Причину возврата\n\n"
        "Деньги возвращаются на ту же карту, с которой была оплата.",
        parse_mode="Markdown",
        reply_markup=refund_kb(),
    )


# ── /cancel ───────────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    """Show subscription status with cancel/refund options."""
    from datetime import datetime, timezone
    user_id = message.from_user.id
    sub = await get_subscription(user_id)

    if not sub or sub["expires_at"] <= datetime.now(timezone.utc):
        await message.answer(
            "ℹ️ У тебя нет активной платной подписки.\n\n"
            "Для возврата или других вопросов — напиши в поддержку.",
            reply_markup=refund_kb(),
        )
        return

    plan = PLANS.get(sub["plan"], PLANS["free"])
    expires = sub["expires_at"].strftime("%d.%m.%Y")
    auto_renew = await get_preference(user_id, "auto_renew") == "1"
    renew_status = "🔄 включено" if auto_renew else "⏸ отключено"

    await message.answer(
        f"📋 *Твоя подписка*\n\n"
        f"{plan['emoji']} Тариф: *{plan['name']}*\n"
        f"📅 Действует до: *{expires}*\n"
        f"Автопродление: {renew_status}\n\n"
        f"После отмены автопродления доступ сохраняется до *{expires}*.",
        parse_mode="Markdown",
        reply_markup=cancel_confirm_kb(has_auto_renew=auto_renew),
    )


@router.callback_query(F.data == "cancel:disable_renew")
async def cb_cancel_disable_renew(callback: CallbackQuery) -> None:
    """Disable auto-renewal — access continues until expiry."""
    await set_preference(callback.from_user.id, "auto_renew", "0")
    sub = await get_subscription(callback.from_user.id)
    expires = sub["expires_at"].strftime("%d.%m.%Y") if sub else "—"
    await callback.message.edit_text(
        f"✅ *Автопродление отключено*\n\n"
        f"Доступ к сервису сохраняется до *{expires}*.\n"
        f"Новых списаний не будет.\n\n"
        f"Если хочешь вернуть деньги за неиспользованный период — напиши в поддержку.",
        parse_mode="Markdown",
        reply_markup=refund_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel:refund")
async def cb_cancel_refund(callback: CallbackQuery) -> None:
    """Redirect to refund flow."""
    await callback.message.edit_text(
        "💰 *Запрос возврата*\n\n"
        "Напишите в поддержку — рассмотрим в течение 5 рабочих дней.\n\n"
        "Укажите: Telegram-профиль, дату платежа, причину возврата.",
        parse_mode="Markdown",
        reply_markup=refund_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel:abort")
async def cb_cancel_abort(callback: CallbackQuery) -> None:
    """User changed mind — dismiss."""
    await callback.message.delete()
    await callback.answer("Отмена подписки не выполнена")


# ── Plan selection screen ─────────────────────────────────────────────────────

@router.callback_query(F.data == "subscribe")
async def cb_subscribe_menu(callback: CallbackQuery) -> None:
    """Show plan selection screen (monthly by default)."""
    lines = ["💎 *Выбери тариф КопиБОТа:*\n"]
    for plan_id in ["free"] + PAID_PLANS:
        p = PLANS[plan_id]
        price = "бесплатно" if p["price_rub"] == 0 else f"{p['price_rub']}₽/мес"
        lines.append(f"{p['emoji']} *{p['name']}* — {price}\n{p['description']}\n")
    await callback.message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=plans_kb(period="month"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plans:period:"))
async def cb_period_toggle(callback: CallbackQuery) -> None:
    """Switch between monthly and annual view."""
    period = callback.data.split("plans:period:")[1]
    await callback.message.edit_reply_markup(reply_markup=plans_kb(period=period))
    await callback.answer()


# ── Checkout confirmation screen ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("subscribe:"))
async def cb_subscribe_plan(callback: CallbackQuery) -> None:
    """Show checkout screen with auto-renew toggle."""
    parts = callback.data.split(":")
    plan_id = parts[1]
    period = parts[2] if len(parts) >= 3 else "month"

    if plan_id not in PAID_PLANS:
        await callback.answer("Неверный тариф", show_alert=True)
        return

    plan = PLANS[plan_id]
    is_annual = period == "year"
    price_str = f"{plan['price_rub_year']}₽/год" if is_annual else f"{plan['price_rub']}₽/мес"
    period_label = "12 месяцев (−17%)" if is_annual else "1 месяц"

    text = (
        f"🧾 *Оформление подписки*\n\n"
        f"{plan['emoji']} *{plan['name']}* — {price_str}\n"
        f"📅 Период: {period_label}\n\n"
        f"{plan['description']}\n\n"
        f"☑️ *Автопродление* — за 3 дня до конца подписки бот пришлёт счёт.\n"
        f"Деньги списываются только после того, как ты сам нажмёшь «Оплатить»."
    )
    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=checkout_kb(plan_id, period, auto_renew=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("checkout:toggle:"))
async def cb_checkout_toggle(callback: CallbackQuery) -> None:
    """Toggle auto-renew checkbox on checkout screen."""
    # checkout:toggle:{plan_id}:{period}
    parts = callback.data.split(":")
    plan_id = parts[2]
    period = parts[3]

    # Read current state from the Pay button's callback_data
    # Find current auto_renew from keyboard
    current_kb = callback.message.reply_markup
    pay_data = ""
    for row in current_kb.inline_keyboard:
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith("checkout:pay:"):
                pay_data = btn.callback_data
    current_renew = pay_data.endswith(":1") if pay_data else False
    new_renew = not current_renew

    await callback.message.edit_reply_markup(
        reply_markup=checkout_kb(plan_id, period, auto_renew=new_renew)
    )
    await callback.answer("✅ Автопродление включено" if new_renew else "☐ Автопродление отключено")


@router.callback_query(F.data.startswith("checkout:pay:"))
async def cb_checkout_pay(callback: CallbackQuery) -> None:
    """Create ЮКасса payment and send link to user."""
    # checkout:pay:{plan_id}:{period}:{auto_renew}
    parts = callback.data.split(":")
    plan_id = parts[2]
    period = parts[3]
    auto_renew = parts[4] == "1" if len(parts) >= 5 else False

    if plan_id not in PAID_PLANS:
        await callback.answer("Неверный тариф", show_alert=True)
        return

    user_id = callback.from_user.id
    plan = PLANS[plan_id]
    is_annual = period == "year"
    months = 12 if is_annual else 1
    amount_rub = plan["price_rub_year"] if is_annual else plan["price_rub"]

    await set_preference(user_id, "auto_renew", "1" if auto_renew else "0")
    await set_preference(user_id, "last_period", period)

    idempotence_key = str(uuid.uuid4())

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: yk_create_payment(
                user_id=user_id,
                plan_id=plan_id,
                period=period,
                amount_rub=amount_rub,
                return_url=settings.bot_url,
                idempotence_key=idempotence_key,
            ),
        )
    except Exception as e:
        logger.error("ЮКасса create_payment error for user %s: %s", user_id, e)
        await callback.message.answer(
            "❌ Не удалось создать счёт. Попробуй позже или напиши в поддержку.",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    await record_payment(
        user_id=user_id,
        yookassa_payment_id=result["payment_id"],
        plan=plan_id,
        period=period,
        amount_rub=amount_rub,
        is_renewal=False,
        idempotence_key=idempotence_key,
    )

    period_label = "12 месяцев (−17%)" if is_annual else "1 месяц"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"💳 *Оплата {plan['emoji']} {plan['name']}*\n\n"
        f"Сумма: *{amount_rub} ₽* · {period_label}\n\n"
        f"После оплаты карта будет сохранена для автопродления.\n"
        f"Нажми кнопку ниже для перехода на страницу оплаты:",
        parse_mode="Markdown",
        reply_markup=payment_link_kb(result["confirmation_url"]),
    )
    await callback.answer()
