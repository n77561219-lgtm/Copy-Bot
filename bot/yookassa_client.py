"""ЮКасса API wrapper.

Инициализация через init_yookassa() при старте бота.
Все функции синхронные — SDK ЮКасса не поддерживает async.
"""
from yookassa import Configuration, Payment, Refund


class YookassaError(Exception):
    """Raised when the ЮКасса API returns an error."""


def init_yookassa(shop_id: str, secret_key: str) -> None:
    if not shop_id or not secret_key:
        raise ValueError("ЮКасса: shop_id и secret_key обязательны")
    Configuration.configure(shop_id, secret_key)


def create_payment(
    user_id: int,
    plan_id: str,
    period: str,
    amount_rub: float,
    return_url: str,
    idempotence_key: str,
) -> dict:
    """Создать платёж с redirect-подтверждением и сохранением карты.

    Возвращает dict с ключами:
        payment_id: str
        confirmation_url: str
    """
    try:
        payment = Payment.create(
            {
                "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": return_url},
                "capture": True,
                "save_payment_method": True,
                "description": f"КопиБОТ {plan_id} — {period}",
                "metadata": {
                    "user_id": str(user_id),
                    "plan": plan_id,
                    "period": period,
                    "is_renewal": "false",
                },
            },
            idempotence_key,
        )
    except Exception as exc:
        raise YookassaError(str(exc)) from exc
    return {
        "payment_id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
    }


def create_renewal_payment(
    user_id: int,
    plan_id: str,
    period: str,
    amount_rub: float,
    yookassa_method_id: str,
    idempotence_key: str,
) -> dict:
    """Автосписание по сохранённой карте — без участия пользователя.

    Возвращает dict с ключом payment_id: str.
    """
    try:
        payment = Payment.create(
            {
                "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
                "payment_method_id": yookassa_method_id,
                "capture": True,
                "description": f"КопиБОТ {plan_id} — автопродление {period}",
                "metadata": {
                    "user_id": str(user_id),
                    "plan": plan_id,
                    "period": period,
                    "is_renewal": "true",
                },
            },
            idempotence_key,
        )
    except Exception as exc:
        raise YookassaError(str(exc)) from exc
    return {"payment_id": payment.id}


def create_refund(
    yookassa_payment_id: str,
    amount_rub: float,
    description: str = "Возврат по запросу пользователя",
) -> str:
    """Создать возврат. Возвращает refund_id."""
    try:
        refund = Refund.create({
            "payment_id": yookassa_payment_id,
            "description": description,
            "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
        })
    except Exception as exc:
        raise YookassaError(str(exc)) from exc
    return refund.id
