"""Subscription plan definitions for Copy-Bot.

Plans:
  free     — permanent free tier, limited features
  trial    — 7-day full access (auto-created on /start)
  basic    — 290 Stars/month
  standard — 590 Stars/month
  pro      — 1490 Stars/month
"""

from typing import TypedDict


class PlanConfig(TypedDict):
    name: str
    emoji: str
    posts_per_month: int | None    # None = unlimited
    images_per_month: int | None   # None = unlimited
    features: list[str]            # style | trends | content_plan | schedule
    stars: int                     # Telegram Stars price (0 = free)
    description: str


PLANS: dict[str, PlanConfig] = {
    "free": {
        "name": "Free",
        "emoji": "🆓",
        "posts_per_month": 3,
        "images_per_month": 1,
        "features": ["style"],
        "stars": 0,
        "description": "3 поста + 1 картинка в месяц • Анализ стиля",
    },
    "trial": {
        "name": "Пробный период",
        "emoji": "⏳",
        "posts_per_month": None,
        "images_per_month": None,
        "features": ["style", "trends", "content_plan", "schedule"],
        "stars": 0,
        "description": "7 дней полного доступа",
    },
    "basic": {
        "name": "Базовый",
        "emoji": "⭐",
        "posts_per_month": 30,
        "images_per_month": 3,
        "features": ["style", "trends"],
        "stars": 290,
        "description": "30 постов + 3 картинки • Тренды • Анализ стиля",
    },
    "standard": {
        "name": "Стандарт",
        "emoji": "💎",
        "posts_per_month": 60,
        "images_per_month": 10,
        "features": ["style", "trends", "content_plan", "schedule"],
        "stars": 590,
        "description": "60 постов + 10 картинок • Контент-план • Тренды • Анализ стиля",
    },
    "pro": {
        "name": "Про",
        "emoji": "🔥",
        "posts_per_month": None,
        "images_per_month": None,
        "features": ["style", "trends", "content_plan", "schedule"],
        "stars": 1490,
        "description": "Безлимит постов и картинок • Контент-план • Тренды • Анализ стиля",
    },
}

# Feature → human-readable name for error messages
FEATURE_NAMES = {
    "trends":       "🔥 Тренды",
    "content_plan": "📋 Контент-план",
    "schedule":     "⏰ Расписание",
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
