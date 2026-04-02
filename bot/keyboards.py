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
MENU_HELP     = "❓ Помощь"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_WRITE),    KeyboardButton(text=MENU_PLAN)],
            [KeyboardButton(text=MENU_TRENDS),   KeyboardButton(text=MENU_SEARCH)],
            [KeyboardButton(text=MENU_STYLE),    KeyboardButton(text=MENU_SETTINGS)],
            [KeyboardButton(text=MENU_PROFILE),  KeyboardButton(text=MENU_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ── Inline keyboards (под сообщениями) ───────────────────────────────────────

def post_actions_keyboard() -> InlineKeyboardMarkup:
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


def subscribe_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💳 Оформить подписку — 490 Stars", callback_data="subscribe"))
    b.row(InlineKeyboardButton(text="ℹ️ Моя подписка", callback_data="subscription_info"))
    return b.as_markup()
