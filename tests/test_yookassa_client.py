"""Юнит-тесты клиента ЮКасса — SDK вызовы мокаются."""
import pytest
from unittest.mock import patch, MagicMock


def _make_payment(payment_id="yp_001", conf_url="https://yookassa.ru/pay/123",
                  method_id="pm_001", last4="4242", card_type="Visa",
                  method_type="bank_card", saved=True):
    p = MagicMock()
    p.id = payment_id
    p.confirmation.confirmation_url = conf_url
    p.payment_method.id = method_id
    p.payment_method.saved = saved
    p.payment_method.type = method_type
    p.payment_method.card.last4 = last4
    p.payment_method.card.card_type = card_type
    return p


def test_create_payment_returns_id_and_url():
    from bot.yookassa_client import create_payment
    with patch("bot.yookassa_client.Payment.create", return_value=_make_payment()) as mock_create:
        result = create_payment(
            user_id=123,
            plan_id="basic",
            period="month",
            amount_rub=390,
            return_url="https://t.me/bot",
            idempotence_key="idem_001",
        )
    assert result["payment_id"] == "yp_001"
    assert result["confirmation_url"] == "https://yookassa.ru/pay/123"
    called_with = mock_create.call_args[0][0]
    assert called_with["save_payment_method"] is True
    assert called_with["amount"]["value"] == "390.00"
    assert called_with["metadata"]["user_id"] == 123
    assert called_with["metadata"]["is_renewal"] == "false"


def test_create_payment_uses_correct_currency():
    from bot.yookassa_client import create_payment
    with patch("bot.yookassa_client.Payment.create", return_value=_make_payment()):
        result = create_payment(123, "pro", "year", 12890, "https://t.me/bot", "idem_002")
    assert result["payment_id"] is not None


def test_create_renewal_payment_no_confirmation():
    from bot.yookassa_client import create_renewal_payment
    with patch("bot.yookassa_client.Payment.create", return_value=_make_payment()) as mock_create:
        result = create_renewal_payment(
            user_id=123,
            plan_id="basic",
            period="month",
            amount_rub=390,
            yookassa_method_id="pm_001",
            idempotence_key="idem_003",
        )
    assert result["payment_id"] == "yp_001"
    called_with = mock_create.call_args[0][0]
    assert "confirmation" not in called_with
    assert called_with["payment_method_id"] == "pm_001"
    assert called_with["metadata"]["is_renewal"] == "true"


def test_create_refund_returns_id():
    from bot.yookassa_client import create_refund
    mock_refund = MagicMock()
    mock_refund.id = "rf_001"
    with patch("bot.yookassa_client.Refund.create", return_value=mock_refund):
        refund_id = create_refund(
            yookassa_payment_id="yp_001",
            amount_rub=390,
            description="Возврат по запросу",
        )
    assert refund_id == "rf_001"


def test_create_payment_amount_formatted_with_two_decimals():
    from bot.yookassa_client import create_payment
    with patch("bot.yookassa_client.Payment.create", return_value=_make_payment()) as mock_create:
        create_payment(123, "standard", "month", 690, "https://t.me/bot", "idem_004")
    called = mock_create.call_args[0][0]
    assert called["amount"]["value"] == "690.00"
    assert called["amount"]["currency"] == "RUB"
