import aiosqlite
from typing import Optional
from bot.config import settings

DB_PATH = settings.db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS style_examples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT    NOT NULL,
    source_file TEXT,
    imported_at TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT NOT NULL,
    topic      TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    published  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS content_plan (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT NOT NULL,
    topic      TEXT NOT NULL,
    format     TEXT,
    angle      TEXT,
    status     TEXT DEFAULT 'planned',
    post_id    INTEGER REFERENCES posts(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_preferences (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def save_style_examples(examples: list[str], source_file: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO style_examples (content, source_file) VALUES (?, ?)",
            [(text, source_file) for text in examples],
        )
        await db.commit()


async def get_style_examples(limit: int = 100) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT content FROM style_examples ORDER BY imported_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def get_style_examples_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM style_examples") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def save_post(content: str, topic: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO posts (content, topic) VALUES (?, ?)", (content, topic)
        )
        await db.commit()
        return cur.lastrowid


async def save_content_plan(plan: list[dict]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM content_plan WHERE status = 'planned'")
        await db.executemany(
            "INSERT INTO content_plan (date, topic, format, angle) VALUES (?, ?, ?, ?)",
            [
                (
                    item.get("date", ""),
                    item.get("topic", ""),
                    item.get("format", ""),
                    item.get("angle", ""),
                )
                for item in plan
            ],
        )
        await db.commit()


async def get_content_plan() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, date, topic, format, angle, status FROM content_plan ORDER BY date"
        ) as cur:
            rows = await cur.fetchall()
    return [
        {"id": r[0], "date": r[1], "topic": r[2], "format": r[3], "angle": r[4], "status": r[5]}
        for r in rows
    ]


async def set_preference(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (key, value),
        )
        await db.commit()


async def get_preference(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM user_preferences WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None
