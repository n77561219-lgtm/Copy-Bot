"""Тесты webhook-обработчика. Все внешние зависимости мокаются."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_request(body: dict, ip: str = "185.71.76.11") -> MagicMock:
    req = MagicMock()
    req.transport.get_extra_info.return_value = (ip, 12345)
    req.headers = {}
    req.read = AsyncMock(return_value=json.dumps(body).encode())
    return req


def _payment_succeeded_body(
    payment_id="yp_001",
    method_id="pm_001",
    user_id=123,
    plan="basic",
    period="month",
    is_renewal="false",
    amount="390.00",
):
    return {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": payment_id,
            "status": "succeeded",
            "amount": {"value": amount, "currency": "RUB"},
            "payment_method": {
                "id": method_id,
                "type": "bank_card",
                "saved": True,
                "card": {"last4": "4242", "card_type": "Visa"},
            },
            "metadata": {
                "user_id": str(user_id),
                "plan": plan,
                "period": period,
                "is_renewal": is_renewal,
            },
        },
    }


@pytest.mark.asyncio
async def test_webhook_rejects_unknown_ip():
    from bot.webhook_server import handle_webhook
    req = _make_request(_payment_succeeded_body(), ip="1.2.3.4")
    with patch("bot.webhook_server.SecurityHelper") as MockSH:
        MockSH.return_value.is_ip_trusted.return_value = False
        response = await handle_webhook(req, bot=MagicMock())
    assert response.status == 403


@pytest.mark.asyncio
async def test_webhook_payment_succeeded_activates_subscription():
    from bot.webhook_server import handle_webhook
    req = _make_request(_payment_succeeded_body())
    mock_bot = AsyncMock()

    with (
        patch("bot.webhook_server.SecurityHelper") as MockSH,
        patch("bot.webhook_server.get_payment_by_yookassa_id", new_callable=AsyncMock, return_value={"status": "pending", "user_id": 123, "plan": "basic", "period": "month", "is_renewal": False}),
        patch("bot.webhook_server.update_payment_status", new_callable=AsyncMock),
        patch("bot.webhook_server.upsert_payment_method", new_callable=AsyncMock, return_value=1),
        patch("bot.webhook_server.activate_subscription", new_callable=AsyncMock),
        patch("bot.webhook_server.get_subscription", new_callable=AsyncMock, return_value={"expires_at": __import__("datetime").datetime(2026, 5, 20, tzinfo=__import__("datetime").timezone.utc)}),
    ):
        MockSH.return_value.is_ip_trusted.return_value = True
        response = await handle_webhook(req, bot=mock_bot)

    assert response.status == 200
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_idempotency_skips_already_succeeded():
    from bot.webhook_server import handle_webhook
    req = _make_request(_payment_succeeded_body())
    mock_bot = AsyncMock()

    with (
        patch("bot.webhook_server.SecurityHelper") as MockSH,
        patch("bot.webhook_server.get_payment_by_yookassa_id", new_callable=AsyncMock, return_value={"status": "succeeded"}),
        patch("bot.webhook_server.activate_subscription", new_callable=AsyncMock) as mock_activate,
        patch("bot.webhook_server.update_payment_status", new_callable=AsyncMock),
    ):
        MockSH.return_value.is_ip_trusted.return_value = True
        response = await handle_webhook(req, bot=mock_bot)

    assert response.status == 200
    mock_activate.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_payment_canceled_renewal_expires_subscription():
    from bot.webhook_server import handle_webhook
    body = {
        "type": "notification",
        "event": "payment.canceled",
        "object": {
            "id": "yp_002",
            "status": "canceled",
            "amount": {"value": "390.00", "currency": "RUB"},
            "payment_method": {"id": "pm_001", "type": "bank_card", "saved": True},
            "cancellation_details": {"reason": "insufficient_funds"},
            "metadata": {
                "user_id": "123",
                "plan": "basic",
                "period": "month",
                "is_renewal": "true",
            },
        },
    }
    req = _make_request(body)
    mock_bot = AsyncMock()

    with (
        patch("bot.webhook_server.SecurityHelper") as MockSH,
        patch("bot.webhook_server.get_payment_by_yookassa_id", new_callable=AsyncMock, return_value={"status": "pending", "is_renewal": True}),
        patch("bot.webhook_server.update_payment_status", new_callable=AsyncMock),
        patch("bot.webhook_server.set_renewal_status", new_callable=AsyncMock),
        patch("bot.webhook_server.expire_subscription", new_callable=AsyncMock) as mock_expire,
        patch("bot.webhook_server.plans_kb", return_value=MagicMock()),
    ):
        MockSH.return_value.is_ip_trusted.return_value = True
        await handle_webhook(req, bot=mock_bot)

    mock_expire.assert_called_once_with(123)
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_payment_canceled_marks_card_inactive_on_card_expired():
    from bot.webhook_server import handle_webhook
    body = {
        "type": "notification",
        "event": "payment.canceled",
        "object": {
            "id": "yp_003",
            "status": "canceled",
            "amount": {"value": "390.00", "currency": "RUB"},
            "payment_method": {"id": "pm_expired", "type": "bank_card", "saved": True},
            "cancellation_details": {"reason": "card_expired"},
            "metadata": {
                "user_id": "123",
                "plan": "basic",
                "period": "month",
                "is_renewal": "false",
            },
        },
    }
    req = _make_request(body)
    mock_bot = AsyncMock()

    with (
        patch("bot.webhook_server.SecurityHelper") as MockSH,
        patch("bot.webhook_server.get_payment_by_yookassa_id", new_callable=AsyncMock, return_value={"status": "pending", "is_renewal": False}),
        patch("bot.webhook_server.update_payment_status", new_callable=AsyncMock),
        patch("bot.webhook_server.mark_payment_method_inactive", new_callable=AsyncMock) as mock_mark,
        patch("bot.webhook_server.plans_kb", return_value=MagicMock()),
    ):
        MockSH.return_value.is_ip_trusted.return_value = True
        await handle_webhook(req, bot=mock_bot)

    mock_mark.assert_called_once_with("pm_expired")
