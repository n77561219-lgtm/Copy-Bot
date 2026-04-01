"""PostgreSQL database layer via asyncpg connection pool.

All tables are scoped by user_id (Telegram user ID as BIGINT).
"""
import asyncpg
from typing import Optional

_pool: asyncpg.Pool | None = None


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

CREATE INDEX IF NOT EXISTS idx_style_examples_user ON style_examples(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_content_plan_user ON content_plan(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires ON subscriptions(expires_at);
CREATE INDEX IF NOT EXISTS idx_usage_log_user ON usage_log(user_id);
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


async def get_subscription(user_id: int) -> Optional[dict]:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT plan, status, started_at, expires_at FROM subscriptions WHERE user_id=$1",
            user_id,
        )
    if not row:
        return None
    return dict(row)


async def is_subscribed(user_id: int) -> bool:
    """Return True if user has an active (non-expired) subscription."""
    from datetime import datetime, timezone
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, expires_at FROM subscriptions WHERE user_id=$1",
            user_id,
        )
    if not row:
        return False
    if row["status"] != "active":
        return False
    return row["expires_at"] > datetime.now(timezone.utc)


async def activate_subscription(user_id: int, months: int = 1, payment_id: str = "") -> None:
    """Activate or extend paid subscription."""
    from datetime import datetime, timedelta, timezone
    async with get_pool().acquire() as conn:
        current = await conn.fetchval(
            "SELECT expires_at FROM subscriptions WHERE user_id=$1 AND status='active'",
            user_id,
        )
        base = max(current, datetime.now(timezone.utc)) if current else datetime.now(timezone.utc)
        new_expires = base + timedelta(days=30 * months)
        await conn.execute(
            """
            INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_id)
            VALUES ($1, 'paid', 'active', $2, $3)
            ON CONFLICT (user_id) DO UPDATE
              SET plan='paid', status='active', expires_at=$2, payment_id=$3
            """,
            user_id, new_expires, payment_id,
        )


async def log_usage(user_id: int, action: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO usage_log (user_id, action) VALUES ($1, $2)",
            user_id, action,
        )
