"""Integration tests for DB schema — run with TEST_DATABASE_URL env var."""
import asyncio
import os
import pytest
import asyncpg

TEST_DB = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def pool():
    from bot.database import init_db, get_pool
    await init_db(TEST_DB)
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
    user_id = 999_004
    await activate_subscription(user_id=user_id, plan="basic", months=1, payment_id="yp_test_003")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE subscriptions SET next_renewal_at = NOW() - interval '1 hour' WHERE user_id=$1",
            user_id
        )
    subs = await get_subscriptions_due_for_renewal()
    assert any(s["user_id"] == user_id for s in subs)
