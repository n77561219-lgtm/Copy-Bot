"""Telegram Stars payment handler."""
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery,
    SuccessfulPayment,
)

from bot.database import activate_subscription, get_subscription, log_usage
from bot.keyboards import main_menu, subscribe_kb

router = Router()

# Price in Telegram Stars
STARS_PRICE = 490
SUBSCRIPTION_MONTHS = 1


@router.callback_query(F.data == "subscribe")
async def cb_subscribe(callback: CallbackQuery) -> None:
    await callback.message.answer_invoice(
        title="Подписка на Copy-Bot",
        description="Полный доступ ко всем функциям на 1 месяц",
        payload="subscription_1month",
        currency="XTR",
        prices=[LabeledPrice(label="1 месяц", amount=STARS_PRICE)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id

    await activate_subscription(
        user_id,
        months=SUBSCRIPTION_MONTHS,
        payment_id=payment.telegram_payment_charge_id,
    )
    await log_usage(user_id, "payment")

    sub = await get_subscription(user_id)
    expires = sub["expires_at"].strftime("%d.%m.%Y") if sub else "—"

    await message.answer(
        f"✅ *Подписка активирована!*\n\n"
        f"Действует до: *{expires}*\n\n"
        f"Спасибо — теперь все функции доступны.",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


