"""Telegram Stars payment handler — supports 3 paid plans."""
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
    """Show plan selection screen."""
    lines = ["💎 *Выбери тариф КопиБОТа:*\n"]
    for plan_id in ["free"] + PAID_PLANS:
        p = PLANS[plan_id]
        price = "бесплатно" if p["stars"] == 0 else f"{p['stars']} Stars/мес"
        lines.append(f"{p['emoji']} *{p['name']}* — {price}\n{p['description']}\n")
    await callback.message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=plans_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subscribe:"))
async def cb_subscribe_plan(callback: CallbackQuery) -> None:
    plan_id = callback.data.split("subscribe:")[1]
    if plan_id not in PAID_PLANS:
        await callback.answer("Неверный тариф", show_alert=True)
        return

    plan = PLANS[plan_id]
    await callback.message.answer_invoice(
        title=f"КопиБОТ {plan['emoji']} {plan['name']}",
        description=plan["description"],
        payload=f"subscription_{plan_id}_1month",
        currency="XTR",
        prices=[LabeledPrice(label="1 месяц", amount=plan["stars"])],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id

    # Parse plan from payload: subscription_{plan_id}_1month
    payload = payment.invoice_payload
    parts = payload.split("_")
    plan_id = parts[1] if len(parts) >= 2 else "basic"
    if plan_id not in PAID_PLANS:
        plan_id = "basic"

    await activate_subscription(user_id, plan=plan_id, months=1,
                                 payment_id=payment.telegram_payment_charge_id)
    await log_usage(user_id, "payment")

    sub = await get_subscription(user_id)
    expires = sub["expires_at"].strftime("%d.%m.%Y") if sub else "—"
    plan = PLANS[plan_id]

    await message.answer(
        f"✅ *Подписка активирована!*\n\n"
        f"{plan['emoji']} Тариф: *{plan['name']}*\n"
        f"📅 Действует до: *{expires}*\n\n"
        f"Спасибо — все функции тарифа доступны.",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
