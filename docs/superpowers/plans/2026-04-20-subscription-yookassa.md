# ЮКасса Subscription System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить Telegram Stars на ЮКасса — добавить настоящее автосписание с сохранённой картой, webhook-подтверждение, контроль доступа по расписанию.

**Architecture:** Встроенный aiohttp-сервер принимает ЮКасса-вебхуки в том же процессе, что и бот. Первый платёж сохраняет карту (`save_payment_method=True`), последующие продления бот инициирует сам через `payment_method_id`. Два новых фоновых цикла: один запускает автосписание за 3 дня до истечения, второй принудительно переводит просроченные подписки на Free каждые 5 минут.

**Tech Stack:** Python 3.11, aiogram 3.x, asyncpg, aiohttp, yookassa SDK 3.x, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-20-subscription-yookassa-design.md`

---

## File Map

| Действие | Файл | Ответственность |
|---|---|---|
| Изменить | `requirements.txt` | Добавить yookassa, aiohttp, pytest-зависимости |
| Изменить | `bot/config.py` | Новые env-переменные ЮКасса |
| Изменить | `bot/database.py` | Новые таблицы, новые/обновлённые функции |
| Создать | `bot/yookassa_client.py` | Обёртка ЮКасса SDK: create_payment, create_renewal, create_refund |
| Создать | `bot/webhook_server.py` | aiohttp: приём и обработка webhook-событий |
| Изменить | `bot/handlers/payment.py` | Заменить Stars-инвойс на ЮКасса-ссылку |
| Изменить | `bot/scheduler.py` | Добавить auto_renewal_loop и expiry_loop |
| Изменить | `bot/main.py` | Запустить aiohttp рядом с polling |
| Создать | `tests/__init__.py` | Пустой файл |
| Создать | `tests/test_yookassa_client.py` | Юнит-тесты клиента |
| Создать | `tests/test_webhook.py` | Юнит-тесты webhook-обработчика |
| Создать | `tests/test_scheduler.py` | Юнит-тесты циклов планировщика |

---

## Task 1: Зависимости и конфигурация

**Files:**
- Modify: `requirements.txt`
- Modify: `bot/config.py`

- [ ] **Шаг 1: Добавить зависимости**

Заменить содержимое `requirements.txt`:

```
aiogram==3.14.0
openai==1.58.0
pydantic-settings==2.7.0
asyncpg==0.30.0
aiofiles==24.1.0
python-dotenv==1.0.1
pytrends==4.9.2
httpx==0.28.1
aiohttp==3.11.11
yookassa==3.10.0
pytest==8.3.5
pytest-asyncio==0.25.3
```

- [ ] **Шаг 2: Добавить переменные конфига**

В `bot/config.py` добавить поля в класс `Settings` (после `apify_token`):

```python
# ЮКасса
yookassa_shop_id: str = ""
yookassa_secret_key: str = ""
webhook_secret: str = ""      # случайный UUID, часть URL вебхука
bot_url: str = "https://t.me/Copy_plan_bot"  # return_url после оплаты
webhook_port: int = 8080
```

- [ ] **Шаг 3: Добавить переменные в `.env`**

Открыть `.env` и добавить:

```
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
WEBHOOK_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
BOT_URL=https://t.me/Copy_plan_bot
WEBHOOK_PORT=8080
```

- [ ] **Шаг 4: Установить зависимости**

```bash
pip install --upgrade yookassa aiohttp pytest pytest-asyncio
```

Ожидаемый вывод: `Successfully installed yookassa-3.x.x ...`

- [ ] **Шаг 5: Коммит**

```bash
git add requirements.txt bot/config.py
git commit -m "feat: add yookassa + aiohttp deps and config vars"
```

---

## Task 2: Схема БД и функции

**Files:**
- Modify: `bot/database.py` (строка `_SCHEMA`, функции `activate_subscription`, `get_monthly_usage`, `log_payment`, плюс новые функции)

### 2a: Обновить схему

- [ ] **Шаг 1: Написать тест для новых таблиц/колонок**

Создать `tests/__init__.py` (пустой файл).

Создать `tests/test_db_schema.py`:

```python
"""Smoke-тест: проверяет что нужные колонки существуют после init_db."""
import asyncio
import os
import pytest
import asyncpg

DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://copybot_user:copybot_pass_2026@localhost:5432/copybot_test")

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def pool():
    from bot.database import init_db, get_pool
    await init_db(DB_URL)
    yield get_pool()

@pytest.mark.asyncio
async def test_payment_methods_table_exists(pool):
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='payment_methods')"
        )
    assert exists

@pytest.mark.asyncio
async def test_subscriptions_has_new_columns(pool):
    async with pool.acquire() as conn:
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='subscriptions'"
        )
    col_names = {r["column_name"] for r in cols}
    assert "billing_period_start" in col_names
    assert "next_renewal_at" in col_names
    assert "renewal_status" in col_names
    assert "payment_method_id" in col_names

@pytest.mark.asyncio
async def test_payments_has_yookassa_id(pool):
    async with pool.acquire() as conn:
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='payments'"
        )
    col_names = {r["column_name"] for r in cols}
    assert "yookassa_payment_id" in col_names
    assert "is_renewal" in col_names
    assert "idempotence_key" in col_names
```

- [ ] **Шаг 2: Запустить тест — убедиться что падает**

```bash
TEST_DATABASE_URL=postgresql://copybot_user:copybot_pass_2026@localhost:5432/copybot pytest tests/test_db_schema.py -v
```

Ожидаемый результат: FAIL — колонки не существуют.

- [ ] **Шаг 3: Обновить `_SCHEMA` в `bot/database.py`**

Найти строку `_SCHEMA = """` и заменить секцию про `payments` + добавить новую таблицу и ALTER-ы. Вставить **после** блока `renewal_notifications` и **перед** блоком с индексами:

```python
# В _SCHEMA добавить новую таблицу (после renewal_notifications):
CREATE TABLE IF NOT EXISTS payment_methods (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL,
    yookassa_method_id  TEXT NOT NULL UNIQUE,
    type                TEXT NOT NULL,
    brand               TEXT,
    last4               TEXT,
    is_default          BOOLEAN DEFAULT TRUE,
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS payment_method_id  BIGINT REFERENCES payment_methods(id);
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS next_renewal_at    TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS renewal_status     TEXT DEFAULT 'ok';
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS billing_period_start TIMESTAMPTZ;

-- Мигрировать старую payments таблицу: если нет yookassa_payment_id — удалить и пересоздать
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables WHERE table_name='payments'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='payments' AND column_name='yookassa_payment_id'
  ) THEN
    DROP TABLE payments CASCADE;
  END IF;
END
$$;
```

И заменить существующий блок `CREATE TABLE IF NOT EXISTS payments` на:

```sql
CREATE TABLE IF NOT EXISTS payments (
    id                   BIGSERIAL PRIMARY KEY,
    user_id              BIGINT NOT NULL,
    yookassa_payment_id  TEXT NOT NULL UNIQUE,
    plan                 TEXT NOT NULL,
    period               TEXT NOT NULL,
    amount_rub           NUMERIC(10,2) NOT NULL,
    status               TEXT NOT NULL DEFAULT 'pending',
    payment_method_id    BIGINT REFERENCES payment_methods(id),
    is_renewal           BOOLEAN DEFAULT FALSE,
    idempotence_key      TEXT NOT NULL UNIQUE,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);
```

Добавить индексы в конец секции индексов:

```sql
CREATE INDEX IF NOT EXISTS idx_payment_methods_user ON payment_methods(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_renewal ON subscriptions(next_renewal_at, renewal_status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires_status ON subscriptions(expires_at, status);
```

- [ ] **Шаг 4: Запустить тест — убедиться что проходит**

```bash
TEST_DATABASE_URL=postgresql://copybot_user:copybot_pass_2026@localhost:5432/copybot pytest tests/test_db_schema.py -v
```

Ожидаемый результат: 3 теста PASS.

### 2b: Новые и обновлённые функции БД

- [ ] **Шаг 5: Написать тесты для функций**

Добавить в `tests/test_db_schema.py`:

```python
@pytest.mark.asyncio
async def test_upsert_payment_method(pool):
    from bot.database import upsert_payment_method, get_default_payment_method
    user_id = 999_001
    method_id = await upsert_payment_method(
        user_id=user_id,
        yookassa_method_id="pm_test_001",
        type="bank_card",
        brand="Visa",
        last4="4242",
    )
    assert method_id is not None
    method = await get_default_payment_method(user_id)
    assert method["last4"] == "4242"
    assert method["is_active"] is True

@pytest.mark.asyncio
async def test_record_and_get_payment(pool):
    from bot.database import record_payment, get_payment_by_yookassa_id, update_payment_status
    user_id = 999_002
    await record_payment(
        user_id=user_id,
        yookassa_payment_id="yp_test_001",
        plan="basic",
        period="month",
        amount_rub=390,
        is_renewal=False,
        idempotence_key="idem_001",
    )
    p = await get_payment_by_yookassa_id("yp_test_001")
    assert p is not None
    assert p["status"] == "pending"
    await update_payment_status("yp_test_001", "succeeded")
    p2 = await get_payment_by_yookassa_id("yp_test_001")
    assert p2["status"] == "succeeded"

@pytest.mark.asyncio
async def test_activate_subscription_resets_billing_period(pool):
    from bot.database import activate_subscription, get_subscription
    user_id = 999_003
    await activate_subscription(user_id=user_id, plan="basic", months=1, payment_id="yp_test_002")
    sub = await get_subscription(user_id)
    assert sub["billing_period_start"] is not None
    assert sub["next_renewal_at"] is not None
    assert sub["renewal_status"] == "ok"

@pytest.mark.asyncio
async def test_get_subscriptions_due_for_renewal(pool):
    from bot.database import get_subscriptions_due_for_renewal, activate_subscription
    from datetime import datetime, timedelta, timezone
    user_id = 999_004
    await activate_subscription(user_id=user_id, plan="basic", months=1, payment_id="yp_test_003")
    # Искусственно сдвинуть next_renewal_at в прошлое
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE subscriptions SET next_renewal_at = NOW() - interval '1 hour' WHERE user_id=$1",
            user_id
        )
    subs = await get_subscriptions_due_for_renewal()
    assert any(s["user_id"] == user_id for s in subs)
```

- [ ] **Шаг 6: Запустить тесты — убедиться что падают**

```bash
TEST_DATABASE_URL=... pytest tests/test_db_schema.py -v -k "test_upsert or test_record or test_activate or test_get_sub"
```

Ожидаемый результат: ImportError / AttributeError — функций не существует.

- [ ] **Шаг 7: Реализовать новые функции в `bot/database.py`**

Добавить после блока `# ── Payments ──────`:

```python
# ── Payment methods ───────────────────────────────────────────────────────────

async def upsert_payment_method(
    user_id: int,
    yookassa_method_id: str,
    type: str,
    brand: Optional[str],
    last4: Optional[str],
) -> int:
    """Save or update a payment method. Returns internal id."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO payment_methods (user_id, yookassa_method_id, type, brand, last4, is_default, is_active)
            VALUES ($1, $2, $3, $4, $5, TRUE, TRUE)
            ON CONFLICT (yookassa_method_id) DO UPDATE
              SET brand=$4, last4=$5, is_active=TRUE, is_default=TRUE
            RETURNING id
            """,
            user_id, yookassa_method_id, type, brand, last4,
        )
        method_id = row["id"]
        # Сбросить is_default у других карт этого пользователя
        await conn.execute(
            "UPDATE payment_methods SET is_default=FALSE WHERE user_id=$1 AND id != $2",
            user_id, method_id,
        )
    return method_id


async def get_default_payment_method(user_id: int) -> Optional[dict]:
    """Return the active default payment method for a user, or None."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, yookassa_method_id, type, brand, last4
            FROM payment_methods
            WHERE user_id=$1 AND is_default=TRUE AND is_active=TRUE
            """,
            user_id,
        )
    return dict(row) if row else None


async def mark_payment_method_inactive(yookassa_method_id: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE payment_methods SET is_active=FALSE WHERE yookassa_method_id=$1",
            yookassa_method_id,
        )


async def record_payment(
    user_id: int,
    yookassa_payment_id: str,
    plan: str,
    period: str,
    amount_rub: float,
    is_renewal: bool,
    idempotence_key: str,
    payment_method_id: Optional[int] = None,
) -> None:
    """Record a new pending payment."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payments
              (user_id, yookassa_payment_id, plan, period, amount_rub, status, is_renewal, idempotence_key, payment_method_id)
            VALUES ($1, $2, $3, $4, $5, 'pending', $6, $7, $8)
            ON CONFLICT (yookassa_payment_id) DO NOTHING
            """,
            user_id, yookassa_payment_id, plan, period, float(amount_rub), is_renewal, idempotence_key, payment_method_id,
        )


async def get_payment_by_yookassa_id(yookassa_payment_id: str) -> Optional[dict]:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM payments WHERE yookassa_payment_id=$1",
            yookassa_payment_id,
        )
    return dict(row) if row else None


async def update_payment_status(
    yookassa_payment_id: str,
    status: str,
    payment_method_id: Optional[int] = None,
) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE payments
            SET status=$2, payment_method_id=COALESCE($3, payment_method_id), updated_at=NOW()
            WHERE yookassa_payment_id=$1
            """,
            yookassa_payment_id, status, payment_method_id,
        )


async def get_subscriptions_due_for_renewal() -> list[dict]:
    """Paid subscriptions where next_renewal_at is due and renewal_status=ok."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.user_id, s.plan, s.expires_at, s.payment_method_id,
                   pm.yookassa_method_id
            FROM subscriptions s
            LEFT JOIN payment_methods pm ON pm.id = s.payment_method_id AND pm.is_active=TRUE
            WHERE s.plan NOT IN ('free', 'trial')
              AND s.status = 'active'
              AND s.renewal_status = 'ok'
              AND s.next_renewal_at <= NOW()
              AND s.expires_at != 'infinity'
            """,
        )
    return [dict(r) for r in rows]


async def get_expired_paid_subscriptions() -> list[dict]:
    """Active paid subscriptions that have passed their expires_at."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id, plan
            FROM subscriptions
            WHERE plan NOT IN ('free', 'trial')
              AND status = 'active'
              AND expires_at < NOW()
              AND expires_at != 'infinity'
            """,
        )
    return [dict(r) for r in rows]


async def set_renewal_status(user_id: int, status: str) -> None:
    """Update renewal_status for a subscription: 'ok' | 'failed' | 'cancelled'."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE subscriptions SET renewal_status=$2 WHERE user_id=$1",
            user_id, status,
        )


async def expire_subscription(user_id: int) -> None:
    """Downgrade a paid subscription to free immediately."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE subscriptions
            SET plan='free', status='active', expires_at='infinity',
                payment_method_id=NULL, next_renewal_at=NULL, renewal_status='ok',
                billing_period_start=NULL
            WHERE user_id=$1
            """,
            user_id,
        )
```

- [ ] **Шаг 8: Обновить `activate_subscription`**

Заменить существующую функцию `activate_subscription` в `bot/database.py`:

```python
async def activate_subscription(
    user_id: int,
    plan: str = "basic",
    months: int = 1,
    payment_id: str = "",
    payment_method_id: Optional[int] = None,
) -> None:
    """Activate or extend a paid subscription. Resets billing period and schedules next renewal."""
    from datetime import datetime, timedelta, timezone
    async with get_pool().acquire() as conn:
        current = await conn.fetchval(
            "SELECT expires_at FROM subscriptions WHERE user_id=$1 AND status='active' AND plan NOT IN ('free','trial')",
            user_id,
        )
        now = datetime.now(timezone.utc)
        base = (current if current and str(current) != "infinity" and _as_utc(current) > now
                else now)
        new_expires = base + timedelta(days=30 * months)
        next_renewal = new_expires - timedelta(days=3)

        await conn.execute(
            """
            INSERT INTO subscriptions
              (user_id, plan, status, expires_at, payment_id, billing_period_start,
               next_renewal_at, renewal_status, payment_method_id)
            VALUES ($1, $2, 'active', $3, $4, NOW(), $5, 'ok', $6)
            ON CONFLICT (user_id) DO UPDATE
              SET plan=$2, status='active', expires_at=$3, payment_id=$4,
                  billing_period_start=NOW(), next_renewal_at=$5,
                  renewal_status='ok',
                  payment_method_id=COALESCE($6, subscriptions.payment_method_id)
            """,
            user_id, plan, new_expires, payment_id, next_renewal, payment_method_id,
        )
```

- [ ] **Шаг 9: Обновить `get_monthly_usage`**

Заменить существующую функцию:

```python
async def get_monthly_usage(user_id: int, action: str) -> int:
    """Count usage for this month. For paid plans counts from billing_period_start."""
    async with get_pool().acquire() as conn:
        plan_row = await conn.fetchrow(
            "SELECT plan, billing_period_start FROM subscriptions WHERE user_id=$1",
            user_id,
        )
        if plan_row and plan_row["plan"] not in ("free", "trial") and plan_row["billing_period_start"]:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM usage_log
                WHERE user_id=$1 AND action=$2 AND created_at >= $3
                """,
                user_id, action, _as_utc(plan_row["billing_period_start"]),
            )
        else:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM usage_log
                WHERE user_id=$1 AND action=$2
                  AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())
                """,
                user_id, action,
            )
    return count or 0
```

- [ ] **Шаг 10: Удалить старую функцию `log_payment`**

Удалить весь блок `async def log_payment(...)` — она заменена на `record_payment` + `update_payment_status`.

- [ ] **Шаг 11: Запустить тесты — убедиться что проходят**

```bash
TEST_DATABASE_URL=... pytest tests/test_db_schema.py -v
```

Ожидаемый результат: все тесты PASS.

- [ ] **Шаг 12: Коммит**

```bash
git add bot/database.py tests/
git commit -m "feat: db schema — payment_methods, updated payments, billing_period_start"
```

---

## Task 3: ЮКасса клиент

**Files:**
- Create: `bot/yookassa_client.py`
- Create: `tests/test_yookassa_client.py`

- [ ] **Шаг 1: Написать тесты**

Создать `tests/test_yookassa_client.py`:

```python
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
```

- [ ] **Шаг 2: Запустить тесты — убедиться что падают**

```bash
pytest tests/test_yookassa_client.py -v
```

Ожидаемый результат: ImportError — модуль не существует.

- [ ] **Шаг 3: Реализовать `bot/yookassa_client.py`**

```python
"""ЮКасса API wrapper.

Инициализация через init_yookassa() при старте бота.
Все функции синхронные — SDK ЮКасса не поддерживает async.
"""
from yookassa import Configuration, Payment, Refund


def init_yookassa(shop_id: str, secret_key: str) -> None:
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
        payment_method_id: str | None  (None пока пользователь не заплатил)
    """
    payment = Payment.create(
        {
            "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "save_payment_method": True,
            "description": f"КопиБОТ {plan_id} — {period}",
            "metadata": {
                "user_id": user_id,
                "plan": plan_id,
                "period": period,
                "is_renewal": "false",
            },
        },
        idempotence_key,
    )
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
    payment = Payment.create(
        {
            "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
            "payment_method_id": yookassa_method_id,
            "capture": True,
            "description": f"КопиБОТ {plan_id} — автопродление {period}",
            "metadata": {
                "user_id": user_id,
                "plan": plan_id,
                "period": period,
                "is_renewal": "true",
            },
        },
        idempotence_key,
    )
    return {"payment_id": payment.id}


def create_refund(
    yookassa_payment_id: str,
    amount_rub: float,
    description: str = "Возврат по запросу пользователя",
) -> str:
    """Создать возврат. Возвращает refund_id."""
    refund = Refund.create({
        "payment_id": yookassa_payment_id,
        "description": description,
        "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
    })
    return refund.id
```

- [ ] **Шаг 4: Запустить тесты — убедиться что проходят**

```bash
pytest tests/test_yookassa_client.py -v
```

Ожидаемый результат: 5 тестов PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add bot/yookassa_client.py tests/test_yookassa_client.py
git commit -m "feat: yookassa client — create_payment, create_renewal, create_refund"
```

---

## Task 4: Webhook-сервер

**Files:**
- Create: `bot/webhook_server.py`
- Create: `tests/test_webhook.py`

- [ ] **Шаг 1: Написать тесты**

Создать `tests/test_webhook.py`:

```python
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
```

- [ ] **Шаг 2: Запустить тесты — убедиться что падают**

```bash
pytest tests/test_webhook.py -v
```

Ожидаемый результат: ImportError.

- [ ] **Шаг 3: Реализовать `bot/webhook_server.py`**

```python
"""aiohttp webhook server for ЮКасса payment notifications.

Регистрируется в main.py рядом с polling-ом бота.
"""
import json
import logging
from datetime import timezone

import aiohttp.web
from aiogram import Bot
from yookassa.domain.notification import WebhookNotificationFactory
from yookassa.infrastructure.secure_helper import SecurityHelper

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
    ip = request.transport.get_extra_info("peername")[0]
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
        # Вернуть 200 чтобы ЮКасса не повторяла — ошибка на нашей стороне, не на их
        return aiohttp.web.Response(status=200, text="OK")

    return aiohttp.web.Response(status=200, text="OK")


async def _handle_payment_succeeded(obj, bot: Bot) -> None:
    payment_id = obj.id
    metadata = obj.metadata or {}
    user_id = int(metadata.get("user_id", 0))
    plan_id = metadata.get("plan", "basic")
    period = metadata.get("period", "month")
    is_renewal = metadata.get("is_renewal", "false") == "true"
    months = 12 if period == "year" else 1

    # Идемпотентность: проверить уже ли обработан
    existing = await get_payment_by_yookassa_id(payment_id)
    if existing and existing["status"] == "succeeded":
        logger.info("Payment %s already processed, skipping", payment_id)
        return

    # Сохранить карту если она есть
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

    # Активировать подписку
    await activate_subscription(
        user_id=user_id,
        plan=plan_id,
        months=months,
        payment_id=payment_id,
        payment_method_id=db_method_id,
    )

    # Обновить запись платежа
    await update_payment_status(payment_id, "succeeded", db_method_id)

    # Уведомить пользователя
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
    is_renewal = metadata.get("is_renewal", "false") == "true"

    existing = await get_payment_by_yookassa_id(payment_id)
    if not existing or existing["status"] in ("succeeded", "cancelled", "failed"):
        return

    await update_payment_status(payment_id, "failed")

    # Пометить карту как неактивную если отклонена банком
    pm = obj.payment_method
    if pm:
        reason = getattr(getattr(obj, "cancellation_details", None), "reason", "")
        if reason in ("card_expired", "payment_method_rejected", "permission_revoked"):
            await mark_payment_method_inactive(pm.id)

    if is_renewal:
        # Автосписание не прошло — немедленно перевести на Free
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
        # Первый платёж не прошёл — подписка не меняется
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
```

- [ ] **Шаг 4: Запустить тесты — убедиться что проходят**

```bash
pytest tests/test_webhook.py -v
```

Ожидаемый результат: 4 теста PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add bot/webhook_server.py tests/test_webhook.py
git commit -m "feat: aiohttp webhook server for yookassa payment events"
```

---

## Task 5: Обновить payment handler

**Files:**
- Modify: `bot/handlers/payment.py`

- [ ] **Шаг 1: Удалить Stars-специфичный код**

В `bot/handlers/payment.py` удалить:
- импорты `LabeledPrice`, `PreCheckoutQuery`, `SuccessfulPayment`
- обработчик `@router.pre_checkout_query()`
- обработчик `@router.message(F.successful_payment)`

Также удалить `log_payment` из импортов `bot.database` (функция удалена в Task 2).

- [ ] **Шаг 2: Заменить `cb_checkout_pay` на ЮКасса**

Заменить обработчик `cb_checkout_pay` (сейчас отправляет Stars-инвойс):

```python
import uuid
import asyncio
from bot.yookassa_client import create_payment
from bot.database import record_payment

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

    # Цена берётся с сервера — из PLANS, не из запроса клиента
    idempotence_key = str(uuid.uuid4())

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: create_payment(
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

    # Записать pending платёж до перехода к оплате
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
```

- [ ] **Шаг 3: Добавить импорты и клавиатуру**

В начало `bot/handlers/payment.py` добавить:
```python
import uuid
import asyncio
import logging
from bot.yookassa_client import create_payment as yk_create_payment
from bot.database import record_payment
from bot.config import settings

logger = logging.getLogger(__name__)
```

В `bot/keyboards.py` добавить функцию:

```python
def payment_link_kb(url: str) -> InlineKeyboardMarkup:
    """Кнопка перехода на страницу оплаты ЮКасса."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=url)],
    ])
```

И добавить `payment_link_kb` в импорт `keyboards.py` в `handlers/payment.py`.

- [ ] **Шаг 4: Обновить renewal_notification_loop в scheduler.py**

В `bot/scheduler.py` функция `_send_renewal_notifications` сейчас отправляет Stars-инвойс. Заменить ветку `if auto_renew and days <= 1:` на:

```python
if auto_renew and days <= 1:
    # Не отправляем инвойс вручную — автосписание запустится в auto_renewal_loop
    # Просто напомнить что списание будет
    await bot.send_message(user_id, text, parse_mode="Markdown")
else:
    from bot.keyboards import plans_kb
    await bot.send_message(
        user_id, text,
        parse_mode="Markdown",
        reply_markup=plans_kb(sub["plan"]),
    )
```

- [ ] **Шаг 5: Коммит**

```bash
git add bot/handlers/payment.py bot/keyboards.py bot/scheduler.py
git commit -m "feat: replace telegram stars invoice with yookassa payment link"
```

---

## Task 6: Фоновые циклы автосписания и истечения

**Files:**
- Modify: `bot/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Шаг 1: Написать тесты**

Создать `tests/test_scheduler.py`:

```python
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
```

- [ ] **Шаг 2: Запустить тесты — убедиться что падают**

```bash
pytest tests/test_scheduler.py -v
```

Ожидаемый результат: ImportError — функций не существует.

- [ ] **Шаг 3: Добавить циклы в `bot/scheduler.py`**

Добавить в начало файла новые импорты:

```python
import uuid
from bot.database import (
    get_subscriptions_due_for_renewal,
    get_expired_paid_subscriptions,
    expire_subscription,
    record_payment,
    set_renewal_status,
)
from bot.yookassa_client import create_renewal_payment
```

Добавить в конец файла:

```python
AUTO_RENEWAL_INTERVAL = 3600   # проверять каждый час
EXPIRY_INTERVAL = 300          # проверять каждые 5 минут


async def auto_renewal_loop(bot: Bot) -> None:
    """Инициирует автосписание для подписок, у которых подошёл next_renewal_at."""
    logger.info("Auto-renewal loop started")
    while True:
        await asyncio.sleep(AUTO_RENEWAL_INTERVAL)
        try:
            await _process_due_renewals(bot)
        except Exception as e:
            logger.error("Auto-renewal loop error: %s", e)


async def _process_due_renewals(bot: Bot) -> None:
    subs = await get_subscriptions_due_for_renewal()
    for sub in subs:
        user_id = sub["user_id"]
        yookassa_method_id = sub.get("yookassa_method_id")

        if not yookassa_method_id:
            logger.warning("No payment method for user %s, skipping renewal", user_id)
            continue

        plan_id = sub["plan"]
        plan_data = PLANS[plan_id]
        period = await get_preference(user_id, "last_period") or "month"
        is_annual = period == "year"
        amount_rub = plan_data["price_rub_year"] if is_annual else plan_data["price_rub"]
        idempotence_key = str(uuid.uuid4())

        try:
            import asyncio as _asyncio
            result = await _asyncio.get_event_loop().run_in_executor(
                None,
                lambda: create_renewal_payment(
                    user_id=user_id,
                    plan_id=plan_id,
                    period=period,
                    amount_rub=amount_rub,
                    yookassa_method_id=yookassa_method_id,
                    idempotence_key=idempotence_key,
                ),
            )
            await record_payment(
                user_id=user_id,
                yookassa_payment_id=result["payment_id"],
                plan=plan_id,
                period=period,
                amount_rub=amount_rub,
                is_renewal=True,
                idempotence_key=idempotence_key,
            )
            # Пометить что renewal инициирован — не запускать повторно
            await set_renewal_status(user_id, "pending")
            logger.info("Renewal payment initiated for user %s: %s", user_id, result["payment_id"])
        except Exception as e:
            logger.error("Failed to initiate renewal for user %s: %s", user_id, e)


async def expiry_loop(bot: Bot) -> None:
    """Переводит просроченные платные подписки на Free каждые 5 минут."""
    logger.info("Expiry loop started")
    while True:
        await asyncio.sleep(EXPIRY_INTERVAL)
        try:
            await _process_expired_subscriptions(bot)
        except Exception as e:
            logger.error("Expiry loop error: %s", e)


async def _process_expired_subscriptions(bot: Bot) -> None:
    expired = await get_expired_paid_subscriptions()
    for row in expired:
        user_id = row["user_id"]
        plan_id = row["plan"]
        plan_data = PLANS.get(plan_id, PLANS["basic"])

        await expire_subscription(user_id)
        logger.info("Expired subscription for user %s (was %s)", user_id, plan_id)

        auto_renew = await get_preference(user_id, "auto_renew") == "1"
        if not auto_renew:
            try:
                from bot.keyboards import plans_kb
                await bot.send_message(
                    user_id,
                    f"📅 *Подписка закончилась*\n\n"
                    f"Тариф {plan_data['emoji']} *{plan_data['name']}* истёк.\n"
                    f"Доступ переведён на бесплатный тариф (5 постов/мес).\n\n"
                    f"Оформить снова:",
                    parse_mode="Markdown",
                    reply_markup=plans_kb(),
                )
            except Exception as e:
                logger.warning("Failed to notify user %s about expiry: %s", user_id, e)
```

- [ ] **Шаг 4: Запустить тесты — убедиться что проходят**

```bash
pytest tests/test_scheduler.py -v
```

Ожидаемый результат: 3 теста PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add bot/scheduler.py tests/test_scheduler.py
git commit -m "feat: auto_renewal_loop and expiry_loop for subscription lifecycle"
```

---

## Task 7: Запуск aiohttp в main.py и инициализация ЮКасса

**Files:**
- Modify: `bot/main.py`

- [ ] **Шаг 1: Обновить `bot/main.py`**

Добавить импорты:

```python
import aiohttp.web
from bot.yookassa_client import init_yookassa
from bot.webhook_server import create_webhook_app
from bot.scheduler import auto_renewal_loop, expiry_loop
```

Заменить функцию `main()`:

```python
async def main() -> None:
    await init_db(settings.database_url)

    # Инициализировать ЮКасса SDK
    init_yookassa(settings.yookassa_shop_id, settings.yookassa_secret_key)
    logger.info("ЮКасса configured for shop %s", settings.yookassa_shop_id)

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    allowed = settings.allowed_user_ids
    if allowed:
        mw = AuthMiddleware(allowed)
        dp.message.middleware(mw)
        dp.callback_query.middleware(mw)
        logger.info("Auth enabled for user IDs: %s", allowed)
    else:
        logger.info("Auth disabled — all users allowed")

    sub_mw = SubscriptionMiddleware()
    dp.message.middleware(sub_mw)
    dp.callback_query.middleware(sub_mw)

    dp.include_router(start.router)
    dp.include_router(admin_handler.router)
    dp.include_router(payment_handler.router)
    dp.include_router(profile_handler.router)
    dp.include_router(referral_handler.router)
    dp.include_router(autopublish_handler.router)
    dp.include_router(schedule_handler.router)
    dp.include_router(upload.router)
    dp.include_router(settings_handler.router)
    dp.include_router(trends_handler.router)
    dp.include_router(topic_search_handler.router)
    dp.include_router(generate.router)

    # Запустить aiohttp webhook-сервер
    webhook_app = create_webhook_app(bot, settings.webhook_secret)
    runner = aiohttp.web.AppRunner(webhook_app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", settings.webhook_port)
    await site.start()
    logger.info("Webhook server started on :%s", settings.webhook_port)

    # Фоновые задачи
    asyncio.create_task(scheduler_loop(bot))
    asyncio.create_task(renewal_notification_loop(bot))
    asyncio.create_task(auto_renewal_loop(bot))
    asyncio.create_task(expiry_loop(bot))

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
```

- [ ] **Шаг 2: Проверить что бот запускается без ошибок**

```bash
python -m bot.main
```

Ожидаемый вывод в логах:
```
ЮКасса configured for shop ...
Webhook server started on :8080
Scheduler started
Auto-renewal loop started
Expiry loop started
Bot started
```

Если ЮКасса-кредов нет в `.env` — бот запустится, но вебхук ЮКасса вернёт 401 при попытке создать платёж.

- [ ] **Шаг 3: Запустить все тесты**

```bash
pytest tests/ -v --ignore=tests/test_db_schema.py
```

Ожидаемый результат: все тесты PASS.

- [ ] **Шаг 4: Добавить nginx-конфиг (документация)**

Создать `docs/nginx-webhook.conf`:

```nginx
location /yookassa/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Этот блок добавить в существующий server{} блок nginx на VPS.

- [ ] **Шаг 5: Зарегистрировать webhook в ЮКасса**

В личном кабинете ЮКасса (https://yookassa.ru/my/http-notifications-settings) добавить:
- URL: `https://yourdomain.com/yookassa/webhook/{WEBHOOK_SECRET}`
- События: `payment.succeeded`, `payment.canceled`, `refund.succeeded`

- [ ] **Шаг 6: Финальный коммит**

```bash
git add bot/main.py docs/nginx-webhook.conf
git commit -m "feat: wire aiohttp webhook server and yookassa init in main.py"
```

---

## Самопроверка плана против спека

### Покрытие требований

| Требование из спека | Задача |
|---|---|
| Webhook не активирует дважды | Task 4: idempotency check в `_handle_payment_succeeded` |
| Цена на сервере | Task 5: `amount_rub` берётся из `PLANS[plan_id]` |
| Сброс счётчика при продлении | Task 2: `billing_period_start=NOW()` в `activate_subscription` |
| Раздельный учёт free/paid | Task 2: `get_monthly_usage` с ветвлением по `billing_period_start` |
| Фантомный остаток | Task 2: после `expire_subscription` план='free', счётчик идёт по календарному месяцу |
| Сохранение карты | Task 4: `upsert_payment_method` в `_handle_payment_succeeded` |
| Автосписание | Task 3: `create_renewal_payment` + Task 6: `auto_renewal_loop` |
| Немедленная блокировка при неуспехе | Task 4: `expire_subscription` в `_handle_payment_canceled` |
| Уведомление при неуспехе | Task 4: `bot.send_message` в `_handle_payment_canceled` |
| Возврат → Free | Task 4: `expire_subscription` в `_handle_refund_succeeded` |
| IP-верификация webhook | Task 4: `SecurityHelper().is_ip_trusted(ip)` |
| Апгрейд плана начинается сегодня | Task 2: `activate_subscription` использует `now` если нет активной |
| Уведомление при истечении без auto_renew | Task 6: `_process_expired_subscriptions` |

### Типовая согласованность

- `expire_subscription(user_id: int)` — определена в DB Task 2, используется в Task 4 и Task 6 ✓
- `set_renewal_status(user_id, status)` — определена в Task 2, используется в Task 4 и Task 6 ✓
- `create_renewal_payment(...)` — определена в Task 3, используется в Task 6 ✓
- `record_payment(...)` — определена в Task 2, используется в Task 5 и Task 6 ✓
- `payment_link_kb(url)` — определена в Task 5 (keyboards.py), используется там же ✓
