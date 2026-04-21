"""aiohttp webhook server for ЮКасса payment notifications."""
import json
import logging

import aiohttp.web
from aiogram import Bot
from yookassa.domain.notification import WebhookNotificationFactory
from yookassa.domain.common.security_helper import SecurityHelper

from bot.database import (
    activate_subscription,
    expire_subscription,
    get_payment_by_yookassa_id,
    get_subscription,
    mark_payment_method_inactive,
    set_renewal_status,
    update_payment_status,
    upsert_payment_method,
)
from bot.keyboards import plans_kb
from bot.plans import PLANS

logger = logging.getLogger(__name__)


async def handle_webhook(request: aiohttp.web.Request, bot: Bot) -> aiohttp.web.Response:
    # 1. Проверить IP
    transport = request.transport
    peername = transport.get_extra_info("peername") if transport else None
    ip = peername[0] if peername else ""
    if not SecurityHelper().is_ip_trusted(ip):
        logger.warning("Webhook rejected from untrusted IP: %s", ip)
        return aiohttp.web.Response(status=403, text="Forbidden")

    # 2. Распарсить тело
    try:
        body = await request.read()
        event_json = json.loads(body)
        notification = WebhookNotificationFactory().create(event_json)
    except Exception as e:
        logger.error("Failed to parse webhook: %s", e)
        return aiohttp.web.Response(status=400, text="Bad Request")

    event = notification.event
    obj = notification.object

    try:
        if event == "payment.succeeded":
            await _handle_payment_succeeded(obj, bot)
        elif event == "payment.canceled":
            await _handle_payment_canceled(obj, bot)
        elif event == "refund.succeeded":
            await _handle_refund_succeeded(obj, bot)
        else:
            logger.info("Unhandled webhook event: %s", event)
    except Exception as e:
        logger.error("Error handling webhook event %s: %s", event, e, exc_info=True)

    return aiohttp.web.Response(status=200, text="OK")


async def _handle_payment_succeeded(obj, bot: Bot) -> None:
    payment_id = obj.id
    metadata = obj.metadata or {}
    user_id = int(metadata.get("user_id", 0))
    if not user_id:
        logger.error("Webhook payment.succeeded has no user_id in metadata: %s", payment_id)
        return
    plan_id = metadata.get("plan", "basic")
    period = metadata.get("period", "month")
    is_renewal = metadata.get("is_renewal", "false") == "true"
    months = 12 if period == "year" else 1

    existing = await get_payment_by_yookassa_id(payment_id)
    if existing and existing["status"] == "succeeded":
        logger.info("Payment %s already processed, skipping", payment_id)
        return

    pm = obj.payment_method
    db_method_id = None
    if pm and getattr(pm, "saved", False):
        brand = getattr(getattr(pm, "card", None), "card_type", None)
        last4 = getattr(getattr(pm, "card", None), "last4", None)
        db_method_id = await upsert_payment_method(
            user_id=user_id,
            yookassa_method_id=pm.id,
            type=pm.type,
            brand=brand,
            last4=last4,
        )

    await activate_subscription(
        user_id=user_id,
        plan=plan_id,
        months=months,
        payment_id=payment_id,
        payment_method_id=db_method_id,
    )

    await update_payment_status(payment_id, "succeeded", db_method_id)

    sub = await get_subscription(user_id)
    expires = sub["expires_at"].strftime("%d.%m.%Y") if sub else "—"
    plan = PLANS.get(plan_id, PLANS["basic"])
    period_label = "12 месяцев" if months == 12 else "1 месяц"
    action = "продлена" if is_renewal else "активирована"

    await bot.send_message(
        user_id,
        f"✅ *Подписка {action}!*\n\n"
        f"{plan['emoji']} Тариф: *{plan['name']}*\n"
        f"📅 Период: *{period_label}*\n"
        f"📅 Действует до: *{expires}*\n\n"
        f"Все функции тарифа доступны.",
        parse_mode="Markdown",
    )
    logger.info("Subscription %s for user %s (plan=%s, renewal=%s)", action, user_id, plan_id, is_renewal)


async def _handle_payment_canceled(obj, bot: Bot) -> None:
    payment_id = obj.id
    metadata = obj.metadata or {}
    user_id = int(metadata.get("user_id", 0))
    if not user_id:
        logger.error("Webhook payment.canceled has no user_id in metadata: %s", payment_id)
        return
    is_renewal = metadata.get("is_renewal", "false") == "true"

    existing = await get_payment_by_yookassa_id(payment_id)
    if not existing or existing["status"] in ("succeeded", "cancelled", "failed"):
        return

    await update_payment_status(payment_id, "failed")

    pm = obj.payment_method
    if pm:
        reason = getattr(getattr(obj, "cancellation_details", None), "reason", "")
        if reason in ("card_expired", "payment_method_rejected", "permission_revoked"):
            await mark_payment_method_inactive(pm.id)

    if is_renewal:
        await set_renewal_status(user_id, "failed")
        await expire_subscription(user_id)
        await bot.send_message(
            user_id,
            "🔴 *Не удалось продлить подписку*\n\n"
            "Автосписание не прошло — возможно, карта заблокирована или недостаточно средств.\n"
            "Доступ переведён на бесплатный тариф.\n\n"
            "Чтобы восстановить подписку — оплати вручную:",
            parse_mode="Markdown",
            reply_markup=plans_kb(),
        )
    else:
        await bot.send_message(
            user_id,
            "❌ *Оплата не прошла*\n\n"
            "Попробуй снова или используй другую карту.",
            parse_mode="Markdown",
            reply_markup=plans_kb(),
        )
    logger.info("Payment canceled for user %s (renewal=%s)", user_id, is_renewal)


async def _handle_refund_succeeded(obj, bot: Bot) -> None:
    payment_id = getattr(obj, "payment_id", None)
    user_id = 0

    if payment_id:
        existing = await get_payment_by_yookassa_id(payment_id)
        if existing:
            await update_payment_status(payment_id, "refunded")
            user_id = existing["user_id"]
            amount_paid = float(existing["amount_rub"])
            amount_refunded = float(obj.amount.value)

            if amount_refunded >= amount_paid:
                await expire_subscription(user_id)
                await bot.send_message(
                    user_id,
                    "💰 *Возврат выполнен*\n\n"
                    f"Сумма: *{amount_refunded:.0f} ₽*\n"
                    "Подписка отменена. Деньги вернутся на карту в течение нескольких дней.",
                    parse_mode="Markdown",
                )
            else:
                await bot.send_message(
                    user_id,
                    f"💰 *Частичный возврат выполнен*\n\nСумма: *{amount_refunded:.0f} ₽*",
                    parse_mode="Markdown",
                )
    logger.info("Refund succeeded for payment %s, user %s", payment_id, user_id)


def create_webhook_app(bot: Bot, webhook_secret: str) -> aiohttp.web.Application:
    """Create aiohttp app with ЮКасса webhook route."""
    app = aiohttp.web.Application()

    async def _handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return await handle_webhook(request, bot)

    app.router.add_post(f"/yookassa/webhook/{webhook_secret}", _handler)
    return app
