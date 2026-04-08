"""Subscription plan definitions for Copy-Bot.

Plans:
  free     — permanent free tier, limited features
  trial    — 7-day full access (auto-created on /start)
  basic    — 290 Stars/month (~380₽)
  standard — 590 Stars/month (~770₽)
  pro      — 990 Stars/month (~1290₽)

Pricing rationale (cost per post ≈ $0.036 / ~3.2₽, per image ≈ $0.039 / ~3.5₽):
  basic:    30п+5ф → ~110₽ cost, ~340₽ payout → margin ~230₽
  standard: 80п+15ф → ~308₽ cost, ~690₽ payout → margin ~382₽
  pro:      200п+50ф → ~815₽ cost, ~1158₽ payout → margin ~343₽
  Pro "unlimited" removed — power users (5+ channels) would cause losses.
"""

from typing import TypedDict


class PlanConfig(TypedDict):
    name: str
    emoji: str
    posts_per_month: int | None     # None = unlimited
    images_per_month: int | None    # None = unlimited
    schedule_slots: int | None      # max schedule time slots; None = unlimited
    style_profiles: int             # max style profiles
    features: list[str]             # style | trends | content_plan | schedule | autopublish | priority
    stars: int                      # Telegram Stars price (0 = free)
    description: str


PLANS: dict[str, PlanConfig] = {
    "free": {
        "name": "Free",
        "emoji": "🆓",
        "posts_per_month": 5,
        "images_per_month": 1,
        "schedule_slots": 0,
        "style_profiles": 1,
        "features": ["style"],
        "stars": 0,
        "description": "5 постов + 1 картинка в месяц • Анализ стиля",
    },
    "trial": {
        "name": "Пробный период",
        "emoji": "⏳",
        "posts_per_month": None,
        "images_per_month": None,
        "schedule_slots": None,
        "style_profiles": 5,
        "features": ["style", "trends", "content_plan", "schedule", "autopublish", "priority"],
        "stars": 0,
        "description": "7 дней полного доступа",
    },
    "basic": {
        "name": "Базовый",
        "emoji": "⭐",
        "posts_per_month": 30,
        "images_per_month": 5,
        "schedule_slots": 1,
        "style_profiles": 1,
        "features": ["style", "trends"],
        "stars": 290,
        "description": "30 постов + 5 картинок • Тренды • Анализ стиля",
    },
    "standard": {
        "name": "Стандарт",
        "emoji": "💎",
        "posts_per_month": 80,
        "images_per_month": 15,
        "schedule_slots": 3,
        "style_profiles": 3,
        "features": ["style", "trends", "content_plan", "schedule", "autopublish"],
        "stars": 590,
        "description": "80 постов + 15 картинок • Контент-план • Расписание • Автопубликация",
    },
    "pro": {
        "name": "Про",
        "emoji": "🔥",
        "posts_per_month": 200,
        "images_per_month": 50,
        "schedule_slots": None,
        "style_profiles": 5,
        "features": ["style", "trends", "content_plan", "schedule", "autopublish", "priority"],
        "stars": 990,
        "description": "200 постов + 50 картинок • Для 3–5 каналов • Все функции",
    },
}

# Feature → human-readable name for error messages
FEATURE_NAMES = {
    "trends":       "🔥 Тренды",
    "content_plan": "📋 Контент-план",
    "schedule":     "⏰ Расписание",
    "autopublish":  "📢 Автопубликация в канал",
    "priority":     "⚡ Приоритет генерации",
}

# Plans available for purchase (shown in payment screen)
PAID_PLANS = ["basic", "standard", "pro"]


def get_plan(plan_name: str) -> PlanConfig:
    return PLANS.get(plan_name, PLANS["free"])


def can_use_feature(plan_name: str, feature: str) -> bool:
    return feature in get_plan(plan_name)["features"]


def posts_limit(plan_name: str) -> int | None:
    return get_plan(plan_name)["posts_per_month"]


def images_limit(plan_name: str) -> int | None:
    return get_plan(plan_name)["images_per_month"]


def slots_limit(plan_name: str) -> int | None:
    """Max schedule slots. 0 = feature disabled, None = unlimited."""
    return get_plan(plan_name)["schedule_slots"]


def profiles_limit(plan_name: str) -> int:
    return get_plan(plan_name)["style_profiles"]
