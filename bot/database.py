"""PostgreSQL database layer via asyncpg connection pool.

All tables are scoped by user_id (Telegram user ID as BIGINT).
"""
import asyncpg
from datetime import datetime, timezone
from typing import Optional

_pool: asyncpg.Pool | None = None


def _as_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC). asyncpg may return naive datetimes for TIMESTAMP columns."""
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def init_db(dsn: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(_SCHEMA)


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_db() first")
    return _pool


_SCHEMA = """
CREATE TABLE IF NOT EXISTS style_examples (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT    NOT NULL,
    content     TEXT      NOT NULL,
    source_file TEXT,
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS posts (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT    NOT NULL,
    content    TEXT      NOT NULL,
    topic      TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    published  BOOLEAN   DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS content_plan (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT    NOT NULL,
    date       TEXT      NOT NULL,
    topic      TEXT      NOT NULL,
    format     TEXT,
    angle      TEXT,
    status     TEXT      DEFAULT 'planned',
    post_id    BIGINT    REFERENCES posts(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    BIGINT NOT NULL,
    key        TEXT   NOT NULL,
    value      TEXT   NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id       BIGINT PRIMARY KEY,
    plan          TEXT        NOT NULL DEFAULT 'trial',
    status        TEXT        NOT NULL DEFAULT 'active',
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,
    payment_id    TEXT
);

CREATE TABLE IF NOT EXISTS usage_log (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT      NOT NULL,
    action     TEXT        NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS referrals (
    id           BIGSERIAL PRIMARY KEY,
    referrer_id  BIGINT NOT NULL,
    invited_id   BIGINT NOT NULL UNIQUE,
    bonus_given  BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduled_posts (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT       NOT NULL,
    content      TEXT         NOT NULL,
    topic        TEXT,
    channel_id   TEXT         NOT NULL,
    scheduled_at TIMESTAMPTZ  NOT NULL,
    status       TEXT         NOT NULL DEFAULT 'pending',
    attempts     INT          NOT NULL DEFAULT 0,
    last_error   TEXT,
    post_id      BIGINT       REFERENCES posts(id),
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schedule_slots (
    id       BIGSERIAL PRIMARY KEY,
    user_id  BIGINT  NOT NULL,
    time_utc TIME    NOT NULL,
    UNIQUE(user_id, time_utc)
);

CREATE TABLE IF NOT EXISTS renewal_notifications (
    user_id    BIGINT NOT NULL,
    days_left  INT    NOT NULL,
    sent_at    TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, days_left)
);

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

CREATE INDEX IF NOT EXISTS idx_style_examples_user ON style_examples(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_content_plan_user ON content_plan(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires ON subscriptions(expires_at);
CREATE INDEX IF NOT EXISTS idx_usage_log_user ON usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_posts_due ON scheduled_posts(scheduled_at, status);
CREATE INDEX IF NOT EXISTS idx_scheduled_posts_user ON scheduled_posts(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_created ON payments(created_at);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_methods_user ON payment_methods(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_renewal ON subscriptions(next_renewal_at, renewal_status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires_status ON subscriptions(expires_at, status);

CREATE TABLE IF NOT EXISTS token_log (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT,
    agent         TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INT  NOT NULL DEFAULT 0,
    output_tokens INT  NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_token_log_created ON token_log(created_at);
CREATE INDEX IF NOT EXISTS idx_token_log_user ON token_log(user_id);
"""


# ── Style examples ────────────────────────────────────────────────────────────

async def save_style_examples(user_id: int, examples: list[str], source_file: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.executemany(
            "INSERT INTO style_examples (user_id, content, source_file) VALUES ($1, $2, $3)",
            [(user_id, text, source_file) for text in examples],
        )


async def get_style_examples(user_id: int, limit: int = 100) -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT content FROM style_examples WHERE user_id=$1 ORDER BY imported_at DESC LIMIT $2",
            user_id, limit,
        )
    return [r["content"] for r in rows]


async def get_style_examples_count(user_id: int) -> int:
    async with get_pool().acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM style_examples WHERE user_id=$1", user_id
        ) or 0


# ── Posts ─────────────────────────────────────────────────────────────────────

async def save_post(user_id: int, content: str, topic: str = "") -> int:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO posts (user_id, content, topic) VALUES ($1, $2, $3) RETURNING id",
            user_id, content, topic,
        )
    return row["id"]


# ── Content plan ──────────────────────────────────────────────────────────────

async def save_content_plan(user_id: int, plan: list[dict]) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "DELETE FROM content_plan WHERE user_id=$1 AND status='planned'", user_id
        )
        await conn.executemany(
            "INSERT INTO content_plan (user_id, date, topic, format, angle) VALUES ($1,$2,$3,$4,$5)",
            [
                (user_id, item.get("date",""), item.get("topic",""),
                 item.get("format",""), item.get("angle",""))
                for item in plan
            ],
        )


async def get_content_plan(user_id: int) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, date, topic, format, angle, status FROM content_plan "
            "WHERE user_id=$1 ORDER BY date",
            user_id,
        )
    return [
        {"id": r["id"], "date": r["date"], "topic": r["topic"],
         "format": r["format"], "angle": r["angle"], "status": r["status"]}
        for r in rows
    ]


async def mark_plan_done(user_id: int, date_str: str) -> bool:
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "UPDATE content_plan SET status='done' WHERE user_id=$1 AND date=$2 AND status='planned'",
            user_id, date_str,
        )
    return result != "UPDATE 0"


# ── User preferences ──────────────────────────────────────────────────────────

async def set_preference(user_id: int, key: str, value: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_preferences (user_id, key, value, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (user_id, key) DO UPDATE SET value=$3, updated_at=NOW()
            """,
            user_id, key, value,
        )


async def get_preference(user_id: int, key: str) -> Optional[str]:
    async with get_pool().acquire() as conn:
        return await conn.fetchval(
            "SELECT value FROM user_preferences WHERE user_id=$1 AND key=$2",
            user_id, key,
        )


# ── Subscriptions ─────────────────────────────────────────────────────────────

TRIAL_DAYS = 5

async def create_trial(user_id: int) -> None:
    """Create a 5-day trial subscription if the user has no subscription yet."""
    from datetime import datetime, timedelta, timezone
    expires = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO subscriptions (user_id, plan, status, expires_at)
            VALUES ($1, 'trial', 'active', $2)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id, expires,
        )


async def ensure_free_plan(user_id: int) -> None:
    """Downgrade user to free plan if trial expired and no paid plan exists."""
    from datetime import datetime, timezone
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT plan, status, expires_at FROM subscriptions WHERE user_id=$1",
            user_id,
        )
        if not row:
            # No subscription at all — create free
            await conn.execute(
                """
                INSERT INTO subscriptions (user_id, plan, status, expires_at)
                VALUES ($1, 'free', 'active', 'infinity')
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
            )
        elif row["plan"] == "trial" and _as_utc(row["expires_at"]) < datetime.now(timezone.utc):
            # Trial expired — downgrade to free
            await conn.execute(
                "UPDATE subscriptions SET plan='free', status='active', expires_at='infinity' WHERE user_id=$1",
                user_id,
            )


async def get_subscription(user_id: int) -> Optional[dict]:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT plan, status, started_at, expires_at FROM subscriptions WHERE user_id=$1",
            user_id,
        )
    if not row:
        return None
    result = dict(row)
    if result.get("expires_at") is not None:
        result["expires_at"] = _as_utc(result["expires_at"])
    return result


async def get_active_plan(user_id: int) -> str:
    """Return current active plan name: free | trial | basic | standard | pro."""
    from datetime import datetime, timezone
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT plan, status, expires_at FROM subscriptions WHERE user_id=$1",
            user_id,
        )
    if not row or row["status"] != "active":
        return "free"
    now = datetime.now(timezone.utc)
    # free plan has expires_at = 'infinity' — always active
    if str(row["expires_at"]) == "infinity" or _as_utc(row["expires_at"]) > now:
        return row["plan"]
    return "free"


async def is_subscribed(user_id: int) -> bool:
    """Return True if user has any active plan (including free)."""
    plan = await get_active_plan(user_id)
    return plan != ""  # always True — free plan is always available


async def get_monthly_usage(user_id: int, action: str) -> int:
    """Count usage for this billing period. Paid plans count from billing_period_start; free from calendar month."""
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


async def log_usage(user_id: int, action: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO usage_log (user_id, action) VALUES ($1, $2)",
            user_id, action,
        )


# ── Referrals ─────────────────────────────────────────────────────────────────

async def register_referral(referrer_id: int, invited_id: int) -> bool:
    """Register invited_id as invited by referrer_id. Returns True if new."""
    if referrer_id == invited_id:
        return False
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO referrals (referrer_id, invited_id)
            VALUES ($1, $2)
            ON CONFLICT (invited_id) DO NOTHING
            """,
            referrer_id, invited_id,
        )
    return result == "INSERT 0 1"


async def give_referral_bonus(referrer_id: int, invited_id: int) -> bool:
    """Give +5 days to referrer when invited_id activates subscription. Returns True if bonus given."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, bonus_given FROM referrals WHERE referrer_id=$1 AND invited_id=$2",
            referrer_id, invited_id,
        )
        if not row or row["bonus_given"]:
            return False
        await conn.execute(
            "UPDATE subscriptions SET expires_at = expires_at + INTERVAL '5 days' WHERE user_id = $1",
            referrer_id,
        )
        await conn.execute(
            "UPDATE referrals SET bonus_given=TRUE WHERE id=$1",
            row["id"],
        )
    return True


async def extend_subscription_days(user_id: int, days: int) -> None:
    """Add N days to user's subscription (trial or paid)."""
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE subscriptions SET expires_at = expires_at + ($1 || ' days')::interval WHERE user_id = $2",
            str(days), user_id,
        )


async def count_successful_referrals(user_id: int) -> int:
    """Count how many referrals this user has where bonus was given."""
    async with get_pool().acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=$1 AND bonus_given=TRUE",
            user_id,
        ) or 0


async def get_referral_stats(user_id: int) -> dict:
    async with get_pool().acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=$1", user_id
        ) or 0
        bonuses = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=$1 AND bonus_given=TRUE", user_id
        ) or 0
    return {"total": total, "bonuses_earned": bonuses}


# ── Scheduled posts ───────────────────────────────────────────────────────────

async def add_to_queue(
    user_id: int,
    content: str,
    channel_id: str,
    scheduled_at,
    topic: str = "",
    post_id: int | None = None,
) -> int:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO scheduled_posts (user_id, content, topic, channel_id, scheduled_at, post_id)
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
            """,
            user_id, content, topic, channel_id, scheduled_at, post_id,
        )
    return row["id"]


async def get_user_queue(user_id: int) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, content, topic, channel_id, scheduled_at, status, attempts
            FROM scheduled_posts
            WHERE user_id=$1 AND status='pending'
            ORDER BY scheduled_at
            """,
            user_id,
        )
    return [dict(r) for r in rows]


async def get_due_scheduled_posts() -> list[dict]:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, content, topic, channel_id, attempts
            FROM scheduled_posts
            WHERE status='pending' AND scheduled_at <= $1
            ORDER BY scheduled_at
            LIMIT 50
            """,
            now,
        )
    return [dict(r) for r in rows]


async def mark_scheduled_published(schedule_id: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE scheduled_posts SET status='published' WHERE id=$1",
            schedule_id,
        )


async def mark_scheduled_failed(schedule_id: int, error: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE scheduled_posts SET status='failed', last_error=$2 WHERE id=$1",
            schedule_id, error,
        )


async def increment_scheduled_attempts(schedule_id: int, attempts: int, error: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE scheduled_posts SET attempts=$2, last_error=$3 WHERE id=$1",
            schedule_id, attempts, error,
        )


async def reschedule_post(schedule_id: int, minutes: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            f"UPDATE scheduled_posts SET scheduled_at = NOW() + INTERVAL '{minutes} minutes' WHERE id=$1",
            schedule_id,
        )


async def delete_scheduled_post(schedule_id: int, user_id: int) -> bool:
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "DELETE FROM scheduled_posts WHERE id=$1 AND user_id=$2 AND status='pending'",
            schedule_id, user_id,
        )
    return result == "DELETE 1"


async def get_queue_stats(user_id: int) -> dict:
    async with get_pool().acquire() as conn:
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM scheduled_posts WHERE user_id=$1 AND status='pending'", user_id
        ) or 0
        published = await conn.fetchval(
            "SELECT COUNT(*) FROM scheduled_posts WHERE user_id=$1 AND status='published'", user_id
        ) or 0
    return {"pending": pending, "published": published}


async def is_queue_paused(user_id: int) -> bool:
    val = await get_preference(user_id, "queue_paused")
    return val == "1"


async def toggle_queue_pause(user_id: int) -> bool:
    """Toggle pause state. Returns new state (True = paused)."""
    paused = await is_queue_paused(user_id)
    await set_preference(user_id, "queue_paused", "0" if paused else "1")
    return not paused


# ── Schedule slots ────────────────────────────────────────────────────────────

async def get_schedule_slots(user_id: int) -> list[str]:
    """Return list of HH:MM strings (UTC)."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT time_utc FROM schedule_slots WHERE user_id=$1 ORDER BY time_utc",
            user_id,
        )
    return [str(r["time_utc"])[:5] for r in rows]


async def add_schedule_slot(user_id: int, time_utc: str) -> bool:
    """Add HH:MM slot. Returns False if already exists."""
    from datetime import time
    h, m = map(int, time_utc.split(":"))
    t = time(h, m)
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "INSERT INTO schedule_slots (user_id, time_utc) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id, t,
        )
    return result == "INSERT 0 1"


async def delete_schedule_slot(user_id: int, time_utc: str) -> bool:
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "DELETE FROM schedule_slots WHERE user_id=$1 AND time_utc=$2::time",
            user_id, time_utc,
        )
    return result == "DELETE 1"


async def next_free_slot(user_id: int) -> Optional[datetime]:
    """Return next datetime (UTC) from user's schedule slots that has no pending post."""
    from datetime import timedelta
    slots = await get_schedule_slots(user_id)
    if not slots:
        return None
    queue = await get_user_queue(user_id)
    taken = {r["scheduled_at"].strftime("%Y-%m-%d %H:%M") for r in queue}
    now = datetime.now(timezone.utc)
    for days_ahead in range(14):
        day = now.date() + timedelta(days=days_ahead)
        for slot in slots:
            h, m = map(int, slot.split(":"))
            candidate = datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)
            if candidate <= now:
                continue
            key = candidate.strftime("%Y-%m-%d %H:%M")
            if key not in taken:
                return candidate
    return None


# ── Renewal notifications ─────────────────────────────────────────────────────

async def get_expiring_subscriptions(days: int) -> list[dict]:
    """Return paid subscribers whose subscription expires in exactly `days` days
    and haven't been notified for that days_left value yet today."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.user_id, s.plan, s.expires_at
            FROM subscriptions s
            WHERE s.plan NOT IN ('free', 'trial')
              AND s.status = 'active'
              AND s.expires_at != 'infinity'
              AND s.expires_at::date = (NOW() + ($1 || ' days')::interval)::date
              AND NOT EXISTS (
                  SELECT 1 FROM renewal_notifications rn
                  WHERE rn.user_id = s.user_id AND rn.days_left = $2
                    AND rn.sent_at::date = NOW()::date
              )
            """,
            str(days), days,
        )
    return [dict(r) for r in rows]


async def mark_renewal_notified(user_id: int, days_left: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO renewal_notifications (user_id, days_left)
            VALUES ($1, $2)
            ON CONFLICT (user_id, days_left) DO UPDATE SET sent_at = NOW()
            """,
            user_id, days_left,
        )


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
            SELECT id, yookassa_method_id, type, brand, last4, is_active
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


# ── Payments ──────────────────────────────────────────────────────────────────

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
    """Update renewal_status: 'ok' | 'failed' | 'cancelled' | 'pending'."""
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


async def get_admin_stats() -> dict:
    """Aggregate stats for the /admin dashboard."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    day_ago   = now - timedelta(days=1)
    week_ago  = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    async with get_pool().acquire() as conn:
        # ── Users by plan ──────────────────────────────────────────────────
        total   = await conn.fetchval("SELECT COUNT(*) FROM subscriptions") or 0
        trial   = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE plan='trial' AND status='active' AND expires_at > $1", now
        ) or 0
        free    = await conn.fetchval("SELECT COUNT(*) FROM subscriptions WHERE plan='free'") or 0
        p_basic = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE plan='basic' AND status='active' AND expires_at > $1", now
        ) or 0
        p_std   = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE plan='standard' AND status='active' AND expires_at > $1", now
        ) or 0
        p_pro   = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE plan='pro' AND status='active' AND expires_at > $1", now
        ) or 0
        expired_paid = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE plan IN ('basic','standard','pro') AND expires_at < $1", now
        ) or 0

        # ── Revenue ───────────────────────────────────────────────────────
        rev_today = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_rub), 0) FROM payments WHERE created_at >= $1", day_ago
        ) or 0
        rev_week  = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_rub), 0) FROM payments WHERE created_at >= $1", week_ago
        ) or 0
        rev_month = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_rub), 0) FROM payments WHERE created_at >= $1", month_ago
        ) or 0
        rev_total = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_rub), 0) FROM payments"
        ) or 0

        # ── Conversion ────────────────────────────────────────────────────
        converted_total = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM payments"
        ) or 0
        converted_30d   = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM payments WHERE created_at >= $1", month_ago
        ) or 0
        registered_30d  = await conn.fetchval(
            "SELECT COUNT(*) FROM subscriptions WHERE started_at >= $1", month_ago
        ) or 0

        # ── Activity ──────────────────────────────────────────────────────
        posts_24h  = await conn.fetchval(
            "SELECT COUNT(*) FROM posts WHERE created_at >= $1", day_ago
        ) or 0
        posts_7d   = await conn.fetchval(
            "SELECT COUNT(*) FROM posts WHERE created_at >= $1", week_ago
        ) or 0
        images_7d  = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_log WHERE action='image_generated' AND created_at >= $1", week_ago
        ) or 0

    conv_30d_rate   = round(converted_30d   / registered_30d  * 100, 1) if registered_30d  > 0 else 0.0
    conv_total_rate = round(converted_total / total            * 100, 1) if total            > 0 else 0.0

    return {
        "total": total, "trial": trial, "free": free,
        "p_basic": p_basic, "p_std": p_std, "p_pro": p_pro,
        "paid_total": p_basic + p_std + p_pro,
        "expired_paid": expired_paid,
        "rev_today": rev_today, "rev_week": rev_week,
        "rev_month": rev_month, "rev_total": rev_total,
        "converted_total": converted_total, "conv_total_rate": conv_total_rate,
        "converted_30d": converted_30d, "registered_30d": registered_30d,
        "conv_30d_rate": conv_30d_rate,
        "posts_24h": posts_24h, "posts_7d": posts_7d, "images_7d": images_7d,
    }


# ── Token tracking ────────────────────────────────────────────────────────────

# OpenRouter pricing (per 1M tokens) in USD, converted at 90₽/$
_TOKEN_COST_RUB = {
    "anthropic/claude-3-5-sonnet": {"in": 3.0 * 90 / 1_000_000, "out": 15.0 * 90 / 1_000_000},
    "anthropic/claude-3-5-haiku":  {"in": 0.8 * 90 / 1_000_000, "out": 4.0  * 90 / 1_000_000},
    "perplexity/sonar":            {"in": 1.0 * 90 / 1_000_000, "out": 1.0  * 90 / 1_000_000},
}
_DEFAULT_COST = {"in": 3.0 * 90 / 1_000_000, "out": 15.0 * 90 / 1_000_000}


def _estimate_cost_rub(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _TOKEN_COST_RUB.get(model, _DEFAULT_COST)
    return round(input_tokens * rates["in"] + output_tokens * rates["out"], 4)


async def log_tokens(
    user_id: int | None,
    agent: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO token_log (user_id, agent, model, input_tokens, output_tokens)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id, agent, model, input_tokens, output_tokens,
        )


async def get_token_stats() -> dict:
    """Aggregate token usage for /admin_tokens."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    day_ago  = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    async with get_pool().acquire() as conn:
        # Totals by period
        def _q(since):
            return (
                "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) "
                "FROM token_log WHERE created_at >= $1"
            ), since

        row_24h = await conn.fetchrow(*_q(day_ago))
        row_7d  = await conn.fetchrow(*_q(week_ago))
        row_all = await conn.fetchrow(
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM token_log"
        )

        # By agent (7 days), top agents by output tokens
        agent_rows = await conn.fetch(
            """
            SELECT agent, model,
                   SUM(input_tokens)  AS inp,
                   SUM(output_tokens) AS out,
                   COUNT(*)           AS calls
            FROM token_log
            WHERE created_at >= $1
            GROUP BY agent, model
            ORDER BY out DESC
            LIMIT 10
            """,
            week_ago,
        )

    def _cost(row):
        return _estimate_cost_rub(
            row["model"] if "model" in row.keys() else "",
            int(row[0]), int(row[1])
        )

    in_24h,  out_24h  = int(row_24h[0]), int(row_24h[1])
    in_7d,   out_7d   = int(row_7d[0]),  int(row_7d[1])
    in_all,  out_all  = int(row_all[0]), int(row_all[1])

    cost_24h = _estimate_cost_rub("", in_24h, out_24h)
    cost_7d  = _estimate_cost_rub("", in_7d,  out_7d)
    cost_all = _estimate_cost_rub("", in_all, out_all)

    agents = [
        {
            "agent": r["agent"],
            "model": r["model"],
            "inp": int(r["inp"]),
            "out": int(r["out"]),
            "calls": int(r["calls"]),
            "cost": _estimate_cost_rub(r["model"], int(r["inp"]), int(r["out"])),
        }
        for r in agent_rows
    ]

    return {
        "in_24h": in_24h, "out_24h": out_24h, "cost_24h": cost_24h,
        "in_7d":  in_7d,  "out_7d":  out_7d,  "cost_7d":  cost_7d,
        "in_all": in_all, "out_all": out_all,  "cost_all": cost_all,
        "agents": agents,
    }


# ── Refund calculation (Appendix 1) ──────────────────────────────────────────

# Prices per action in rubles (Appendix 1 of Politika_vozvrata)
_REFUND_RATES: dict[str, int] = {
    "post_generated": 8,
    "plan_generated":  25,
    "style_analyzed":  20,
    "post_edited":     6,
    "image_generated": 0,   # not in Appendix 1 — no charge for refund
}


async def get_user_refund_summary(user_id: int, since: datetime | None = None) -> dict:
    """Calculate how much the user has consumed since their last payment.

    Returns:
        counts   — dict action→count
        used_rub — total cost of consumed generations (₽)
        sub      — subscription row or None
        payment  — last payment row or None
        refund   — calculated refund amount (₽, floor 0)
    """
    async with get_pool().acquire() as conn:
        # Last payment
        payment = await conn.fetchrow(
            "SELECT * FROM payments WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1",
            user_id,
        )
        since_dt = since or (payment["created_at"] if payment else None)

        # Subscription
        sub = await conn.fetchrow(
            "SELECT * FROM subscriptions WHERE user_id=$1", user_id
        )

        # Usage counts since payment date
        if since_dt:
            rows = await conn.fetch(
                """
                SELECT action, COUNT(*) AS cnt
                FROM usage_log
                WHERE user_id=$1 AND created_at >= $2
                GROUP BY action
                """,
                user_id, since_dt,
            )
        else:
            rows = await conn.fetch(
                "SELECT action, COUNT(*) AS cnt FROM usage_log WHERE user_id=$1 GROUP BY action",
                user_id,
            )

    counts: dict[str, int] = {r["action"]: int(r["cnt"]) for r in rows}

    used_rub = sum(
        counts.get(action, 0) * price
        for action, price in _REFUND_RATES.items()
    )

    # Refund = (price × remaining_days / total_days) − used_rub
    refund_amount = 0.0
    if sub and payment:
        from bot.plans import PLANS
        plan_data = PLANS.get(sub["plan"], {})
        paid_at  = _as_utc(payment["created_at"])
        expires  = _as_utc(sub["expires_at"])
        now      = datetime.now(timezone.utc)
        total_days     = max((expires - paid_at).days, 1)
        remaining_days = max((expires - now).days, 0)
        price_rub      = int(payment["amount_rub"])
        prorated       = price_rub * remaining_days / total_days
        refund_amount  = max(round(prorated - used_rub, 2), 0.0)

    return {
        "counts":      counts,
        "used_rub":    used_rub,
        "sub":         dict(sub) if sub else None,
        "payment":     dict(payment) if payment else None,
        "refund":      refund_amount,
    }
