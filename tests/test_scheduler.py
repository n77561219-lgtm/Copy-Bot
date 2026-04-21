"""Тесты фоновых циклов автосписания и истечения подписок."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


def _sub(user_id=123, plan="basic", period="month", yookassa_method_id="pm_001"):
    return {
        "user_id": user_id,
        "plan": plan,
        "expires_at": datetime(2026, 5, 20, tzinfo=timezone.utc),
        "yookassa_method_id": yookassa_method_id,
    }


@pytest.mark.asyncio
async def test_auto_renewal_creates_payment_for_due_subs():
    from bot.scheduler import _process_due_renewals
    mock_bot = AsyncMock()

    with (
        patch("bot.scheduler.get_subscriptions_due_for_renewal", new_callable=AsyncMock, return_value=[_sub()]),
        patch("bot.scheduler.get_preference", new_callable=AsyncMock, return_value="month"),
        patch("bot.scheduler.set_renewal_status", new_callable=AsyncMock),
        patch("bot.scheduler.record_payment", new_callable=AsyncMock),
        patch("bot.scheduler.create_renewal_payment", return_value={"payment_id": "yp_renewal_001"}),
    ):
        await _process_due_renewals(mock_bot)


@pytest.mark.asyncio
async def test_auto_renewal_skips_sub_without_payment_method():
    from bot.scheduler import _process_due_renewals
    mock_bot = AsyncMock()
    sub_no_method = _sub()
    sub_no_method["yookassa_method_id"] = None

    with (
        patch("bot.scheduler.get_subscriptions_due_for_renewal", new_callable=AsyncMock, return_value=[sub_no_method]),
        patch("bot.scheduler.create_renewal_payment") as mock_create,
    ):
        await _process_due_renewals(mock_bot)

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_expiry_loop_expires_and_notifies():
    from bot.scheduler import _process_expired_subscriptions
    mock_bot = AsyncMock()

    with (
        patch("bot.scheduler.get_expired_paid_subscriptions", new_callable=AsyncMock, return_value=[{"user_id": 123, "plan": "basic"}]),
        patch("bot.scheduler.expire_subscription", new_callable=AsyncMock) as mock_expire,
        patch("bot.scheduler.get_preference", new_callable=AsyncMock, return_value="0"),
        patch("bot.scheduler.plans_kb", return_value=MagicMock()),
    ):
        await _process_expired_subscriptions(mock_bot)

    mock_expire.assert_called_once_with(123)
    mock_bot.send_message.assert_called_once()
