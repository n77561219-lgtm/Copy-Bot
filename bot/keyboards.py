from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ── Reply keyboard (постоянное меню снизу) ────────────────────────────────────

MENU_WRITE    = "✏️ Написать пост"
MENU_PLAN     = "📋 Контент-план"
MENU_TRENDS   = "🔥 Тренды"
MENU_SEARCH   = "🔍 Поиск по теме"
MENU_STYLE    = "🧠 Мой стиль"
MENU_SETTINGS = "⚙️ Настройки"
MENU_PROFILE  = "👤 Профиль"
MENU_REFERRAL = "👥 Рефералы"
MENU_SCHEDULE = "⏰ Расписание"
MENU_HELP     = "❓ Помощь"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_WRITE),    KeyboardButton(text=MENU_PLAN)],
            [KeyboardButton(text=MENU_TRENDS),   KeyboardButton(text=MENU_SEARCH)],
            [KeyboardButton(text=MENU_STYLE),    KeyboardButton(text=MENU_SETTINGS)],
            [KeyboardButton(text=MENU_PROFILE),  KeyboardButton(text=MENU_REFERRAL)],
            [KeyboardButton(text=MENU_SCHEDULE)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ── Inline keyboards (под сообщениями) ───────────────────────────────────────

def post_actions_keyboard(has_channel: bool = False) -> InlineKeyboardMarkup:
    """Full action panel shown under every generated post."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✂️ Короче",     callback_data="edit:shorter"),
        InlineKeyboardButton(text="📝 Длиннее",    callback_data="edit:longer"),
    )
    b.row(
        InlineKeyboardButton(text="🫀 Человечнее", callback_data="edit:human"),
        InlineKeyboardButton(text="🔥 Хлёстче",   callback_data="edit:punchier"),
    )
    b.row(
        InlineKeyboardButton(text="✏️ Грамматика", callback_data="edit:grammar"),
        InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="post:regenerate"),
    )
    b.row(InlineKeyboardButton(text="🖼 Картинка", callback_data="image:generate"))
    if has_channel:
        b.row(
            InlineKeyboardButton(text="📢 Опубликовать сейчас", callback_data="publish:channel:go"),
            InlineKeyboardButton(text="⏰ В очередь", callback_data="schedule:enqueue"),
        )
    b.row(InlineKeyboardButton(text="✅ Готово", callback_data="post:save"))
    return b.as_markup()


def edit_actions_keyboard() -> InlineKeyboardMarkup:
    """Compact edit panel (after manual edit instruction)."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✂️ Короче",     callback_data="edit:shorter"),
        InlineKeyboardButton(text="📝 Длиннее",    callback_data="edit:longer"),
    )
    b.row(
        InlineKeyboardButton(text="🫀 Человечнее", callback_data="edit:human"),
        InlineKeyboardButton(text="🔥 Хлёстче",   callback_data="edit:punchier"),
    )
    b.row(
        InlineKeyboardButton(text="✏️ Грамматика", callback_data="edit:grammar"),
        InlineKeyboardButton(text="✍️ Своя правка...", callback_data="edit:custom"),
    )
    b.row(InlineKeyboardButton(text="✅ Готово", callback_data="post:save"))
    return b.as_markup()


def plan_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Сохранить план", callback_data="plan:save"),
        InlineKeyboardButton(text="🔄 Пересоздать", callback_data="plan:regenerate"),
    )
    return b.as_markup()


def plan_actions_keyboard(dates: list[str]) -> InlineKeyboardMarkup:
    """8-button plan keyboard. dates = list of ISO date strings for each row."""
    b = InlineKeyboardBuilder()
    for i, d in enumerate(dates[:3], 1):
        b.row(
            InlineKeyboardButton(text=f"✏️ Написать #{i}", callback_data=f"plan:write:{d}"),
            InlineKeyboardButton(text=f"✅ Готово #{i}",   callback_data=f"plan:done:{d}"),
        )
    b.row(
        InlineKeyboardButton(text="📋 Весь план",    callback_data="plan:show_all"),
        InlineKeyboardButton(text="🤖 Создать план", callback_data="plan:ai_generate"),
    )
    return b.as_markup()


def style_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 Загрузить новый файл", callback_data="style:upload_hint"))
    b.row(InlineKeyboardButton(text="🔄 Сменить профиль стиля", callback_data="style:switch"))
    return b.as_markup()


def trends_entry_kb(niche_label: str = "") -> InlineKeyboardMarkup:
    """Entry menu shown when user taps 🔥 Тренды."""
    b = InlineKeyboardBuilder()
    niche_text = f"🌐 По нише: {niche_label[:30]}" if niche_label else "🌐 По нише"
    b.row(InlineKeyboardButton(text=niche_text, callback_data="trend:by_niche"))
    b.row(InlineKeyboardButton(text="🔍 Поиск по конкретной теме", callback_data="trend:by_query"))
    return b.as_markup()


def trend_topics_kb(trends: list[dict]) -> InlineKeyboardMarkup:
    """One button per trend + refresh. Indexes used as callback data (no title in data)."""
    b = InlineKeyboardBuilder()
    for i in range(min(len(trends), 5)):
        b.row(InlineKeyboardButton(
            text=f"{i+1} Написать пост",
            callback_data=f"trend:write:{i}",
        ))
    b.row(InlineKeyboardButton(text="🔄 Обновить тренды", callback_data="trend:refresh"))
    b.row(InlineKeyboardButton(text="🔍 Поиск по теме", callback_data="trend:by_query"))
    return b.as_markup()


def topic_search_kb(topics: list[dict]) -> InlineKeyboardMarkup:
    """One button per found topic (3 items) + nav buttons."""
    b = InlineKeyboardBuilder()
    for i in range(min(len(topics), 3)):
        b.row(InlineKeyboardButton(
            text=f"{i+1} Написать пост",
            callback_data=f"topicsearch:write:{i}",
        ))
    b.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="trend:by_query"),
        InlineKeyboardButton(text="🌐 По нише", callback_data="trend:by_niche"),
    )
    return b.as_markup()


def next_topics_kb() -> InlineKeyboardMarkup:
    """Shown when style profile is missing."""
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 Загрузить стиль", callback_data="style:upload_hint"))
    return b.as_markup()


def format_choice_kb() -> InlineKeyboardMarkup:
    """Format selection shown after user enters a post topic."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📚 Экспертный", callback_data="format:expert"),
        InlineKeyboardButton(text="📖 Кейс",       callback_data="format:case"),
    )
    b.row(
        InlineKeyboardButton(text="💰 Продающий",  callback_data="format:sales"),
        InlineKeyboardButton(text="🔥 Провокация", callback_data="format:provocation"),
    )
    b.row(InlineKeyboardButton(text="💬 Сторителлинг", callback_data="format:story"))
    b.row(InlineKeyboardButton(text="✨ Без формата", callback_data="format:default"))
    return b.as_markup()


def subscribe_kb() -> InlineKeyboardMarkup:
    """Legacy single-button — replaced by plans_kb in most places."""
    return plans_kb()


def plans_kb(current_plan: str = "") -> InlineKeyboardMarkup:
    """Plan selection keyboard shown in paywall and profile."""
    from bot.plans import PLANS, PAID_PLANS
    b = InlineKeyboardBuilder()
    for plan_id in PAID_PLANS:
        p = PLANS[plan_id]
        mark = " ✅" if plan_id == current_plan else ""
        b.row(InlineKeyboardButton(
            text=f"{p['emoji']} {p['name']} — {p['price_rub']}₽/мес{mark}",
            callback_data=f"subscribe:{plan_id}",
        ))
    b.row(InlineKeyboardButton(text="ℹ️ Моя подписка", callback_data="subscription_info"))
    return b.as_markup()


def schedule_main_kb(paused: bool, pending: int) -> InlineKeyboardMarkup:
    """Main schedule screen keyboard."""
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Добавить слот времени", callback_data="sched:add_slot"))
    b.row(InlineKeyboardButton(text="🗑 Удалить слот", callback_data="sched:del_slot"))
    if pending > 0:
        pause_text = "▶️ Возобновить очередь" if paused else "⏸ Пауза очереди"
        b.row(InlineKeyboardButton(text=pause_text, callback_data="sched:toggle_pause"))
    return b.as_markup()


def schedule_queue_kb(posts: list[dict]) -> InlineKeyboardMarkup:
    """List of queued posts with delete buttons."""
    b = InlineKeyboardBuilder()
    for post in posts[:10]:
        topic = (post.get("topic") or "без темы")[:25]
        dt = post["scheduled_at"].strftime("%d.%m %H:%M")
        b.row(InlineKeyboardButton(
            text=f"🗑 {dt} — {topic}",
            callback_data=f"sched:del_post:{post['id']}",
        ))
    return b.as_markup()


def schedule_confirm_kb(scheduled_at_str: str) -> InlineKeyboardMarkup:
    """Confirm adding post to queue."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Да, добавить", callback_data=f"sched:confirm:{scheduled_at_str}"),
        InlineKeyboardButton(text="🕐 Другое время", callback_data="sched:manual_time"),
    )
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="sched:cancel"))
    return b.as_markup()
