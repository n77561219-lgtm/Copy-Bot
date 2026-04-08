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

CREATE INDEX IF NOT EXISTS idx_style_examples_user ON style_examples(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_content_plan_user ON content_plan(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires ON subscriptions(expires_at);
CREATE INDEX IF NOT EXISTS idx_usage_log_user ON usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_posts_due ON scheduled_posts(scheduled_at, status);
CREATE INDEX IF NOT EXISTS idx_scheduled_posts_user ON scheduled_posts(user_id);
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

async def create_trial(user_id: int) -> None:
    """Create a 7-day trial subscription if the user has no subscription yet."""
    from datetime import datetime, timedelta, timezone
    expires = datetime.now(timezone.utc) + timedelta(days=7)
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
    return dict(row)


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
    """Count usage_log entries for this user/action in the current calendar month."""
    async with get_pool().acquire() as conn:
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
) -> None:
    """Activate or extend a paid subscription for the given plan."""
    from datetime import datetime, timedelta, timezone
    async with get_pool().acquire() as conn:
        current = await conn.fetchval(
            "SELECT expires_at FROM subscriptions WHERE user_id=$1 AND status='active' AND plan NOT IN ('free','trial')",
            user_id,
        )
        now = datetime.now(timezone.utc)
        if current and str(current) != "infinity" and current > now:
            base = current
        else:
            base = now
        new_expires = base + timedelta(days=30 * months)
        await conn.execute(
            """
            INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_id)
            VALUES ($1, $2, 'active', $3, $4)
            ON CONFLICT (user_id) DO UPDATE
              SET plan=$2, status='active', expires_at=$3, payment_id=$4
            """,
            user_id, plan, new_expires, payment_id,
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
    """Give +7 days to referrer when invited_id activates subscription. Returns True if bonus given."""
    from datetime import datetime, timedelta, timezone
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, bonus_given FROM referrals WHERE referrer_id=$1 AND invited_id=$2",
            referrer_id, invited_id,
        )
        if not row or row["bonus_given"]:
            return False
        # extend referrer subscription by 7 days
        await conn.execute(
            """
            UPDATE subscriptions
            SET expires_at = expires_at + INTERVAL '7 days'
            WHERE user_id = $1
            """,
            referrer_id,
        )
        await conn.execute(
            "UPDATE referrals SET bonus_given=TRUE WHERE id=$1",
            row["id"],
        )
    return True


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


async def next_free_slot(user_id: int) -> Optional["datetime"]:
    """Return next datetime (UTC) from user's schedule slots that has no pending post."""
    from datetime import datetime, timezone, timedelta
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
