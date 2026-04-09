"""Telegram Stars payment handler — monthly and annual plans."""
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery,
    SuccessfulPayment,
)

from bot.database import activate_subscription, get_subscription, log_usage
from bot.keyboards import main_menu, plans_kb
from bot.plans import PLANS, PAID_PLANS

router = Router()


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
    period = callback.data.split("plans:period:")[1]  # "month" or "year"
    await callback.message.edit_reply_markup(reply_markup=plans_kb(period=period))
    await callback.answer()


@router.callback_query(F.data.startswith("subscribe:"))
async def cb_subscribe_plan(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    plan_id = parts[1]
    period = parts[2] if len(parts) >= 3 else "month"

    if plan_id not in PAID_PLANS:
        await callback.answer("Неверный тариф", show_alert=True)
        return

    plan = PLANS[plan_id]
    is_annual = period == "year"

    if is_annual:
        amount = plan["stars_year"]
        label = "12 месяцев (−17%)"
        payload = f"subscription_{plan_id}_12month"
        price_str = f"{plan['price_rub_year']}₽/год"
    else:
        amount = plan["stars"]
        label = "1 месяц"
        payload = f"subscription_{plan_id}_1month"
        price_str = f"{plan['price_rub']}₽/мес"

    await callback.message.answer_invoice(
        title=f"КопиБОТ {plan['emoji']} {plan['name']}",
        description=f"{plan['description']} • {price_str}",
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=amount)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id

    # Parse plan and period from payload: subscription_{plan_id}_{N}month
    payload = payment.invoice_payload
    parts = payload.split("_")
    plan_id = parts[1] if len(parts) >= 2 else "basic"
    period_part = parts[2] if len(parts) >= 3 else "1month"  # "1month" or "12month"
    months = 12 if period_part.startswith("12") else 1

    if plan_id not in PAID_PLANS:
        plan_id = "basic"

    await activate_subscription(user_id, plan=plan_id, months=months,
                                 payment_id=payment.telegram_payment_charge_id)
    await log_usage(user_id, "payment")

    sub = await get_subscription(user_id)
    expires = sub["expires_at"].strftime("%d.%m.%Y") if sub else "—"
    plan = PLANS[plan_id]
    period_label = "12 месяцев" if months == 12 else "1 месяц"

    await message.answer(
        f"✅ *Подписка активирована!*\n\n"
        f"{plan['emoji']} Тариф: *{plan['name']}*\n"
        f"📅 Период: *{period_label}*\n"
        f"📅 Действует до: *{expires}*\n\n"
        f"Спасибо — все функции тарифа доступны.",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
