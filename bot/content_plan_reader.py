"""Reads and updates content-plan.md."""
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

PLAN_FILE = Path(__file__).parent.parent / "content-plan.md"

# Branch → colored circle
BRANCH_COLOR = {
    "личная":      "🟢",
    "экспертная":  "🔵",
    "продуктовая": "🟡",
    "продающая":   "🔴",
}

BRANCH_LABEL = {
    "личная":      "Личная",
    "экспертная":  "Экспертная",
    "продуктовая": "Продуктовая",
    "продающая":   "Продающая",
}

_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

_WEEKDAYS = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}


@dataclass
class PlannedPost:
    date: date
    branch: str
    status: str
    topic: str
    fmt: str
    audience: str
    angle: str


# ── Parsing ────────────────────────────────────────────────────────────────────

def _parse_plan(text: str) -> list[PlannedPost]:
    posts: list[PlannedPost] = []
    blocks = re.split(r"\n---\n", text)
    for block in blocks:
        header = re.search(
            r"##\s+(\d{4}-\d{2}-\d{2})\s*\|\s*(\S+)\s*\|\s*(\S+)",
            block, re.IGNORECASE,
        )
        if not header:
            continue
        try:
            post_date = datetime.strptime(header.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        topic = _field(block, "Тема")
        if topic:
            posts.append(PlannedPost(
                date=post_date,
                branch=header.group(2).lower(),
                status=header.group(3).lower(),
                topic=topic,
                fmt=_field(block, "Формат"),
                audience=_field(block, "ЦА"),
                angle=_field(block, "Угол"),
            ))
    return sorted(posts, key=lambda p: p.date)


def _field(block: str, name: str) -> str:
    m = re.search(rf"\*\*{name}:\*\*\s*(.+)", block)
    return m.group(1).strip() if m else ""


# ── Public API ─────────────────────────────────────────────────────────────────

def get_upcoming(n: int = 3) -> list[PlannedPost]:
    if not PLAN_FILE.exists():
        return []
    posts = _parse_plan(PLAN_FILE.read_text(encoding="utf-8"))
    today = date.today()
    return [p for p in posts if p.status == "planned" and p.date >= today][:n]


def get_all(include_done: bool = True) -> list[PlannedPost]:
    if not PLAN_FILE.exists():
        return []
    posts = _parse_plan(PLAN_FILE.read_text(encoding="utf-8"))
    if not include_done:
        posts = [p for p in posts if p.status != "done"]
    return posts


def mark_done(post_date: date) -> bool:
    """Change status planned → done for the given date in the file."""
    if not PLAN_FILE.exists():
        return False
    date_str = post_date.strftime("%Y-%m-%d")
    text = PLAN_FILE.read_text(encoding="utf-8")
    pattern = rf"(##\s+{re.escape(date_str)}\s*\|\s*\S+\s*\|)\s*planned"
    new_text, count = re.subn(pattern, r"\1 done", text, flags=re.IGNORECASE)
    if count:
        PLAN_FILE.write_text(new_text, encoding="utf-8")
    return bool(count)


# ── Formatting ─────────────────────────────────────────────────────────────────

def _date_label(d: date) -> str:
    return f"{_WEEKDAYS[d.weekday()]}, {d.day} {_MONTHS[d.month]}"


def format_upcoming(posts: list[PlannedPost]) -> str:
    if not posts:
        return "📋 Ближайших запланированных постов нет.\n\nОткрой content-plan.md чтобы добавить."

    lines = ["📋 Ближайшие темы:\n"]
    for i, p in enumerate(posts, 1):
        circle = BRANCH_COLOR.get(p.branch, "⚪")
        label  = BRANCH_LABEL.get(p.branch, p.branch.capitalize())
        lines.append(
            f"{i} {circle} День {i} ({_date_label(p.date)})\n"
            f"  {p.topic}\n"
            f"  ↳ _{p.angle}_\n"
        )
    return "\n".join(lines)


def format_all(posts: list[PlannedPost]) -> str:
    if not posts:
        return "📋 План пуст."
    lines = ["📋 Весь план:\n"]
    for p in posts:
        icon = "✅" if p.status == "done" else BRANCH_COLOR.get(p.branch, "⬜")
        lines.append(f"{icon} {p.date.strftime('%d.%m')} — {p.topic}")
    return "\n".join(lines)
