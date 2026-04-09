"""Subscription plan definitions for Copy-Bot.

Plans:
  free     — permanent free tier, limited features
  trial    — 7-day full access (auto-created on /start)
  basic    — 390₽/month  (290 Stars)
  standard — 690₽/month  (590 Stars)
  pro      — 1290₽/month (990 Stars)

Pricing rationale (cost per post ≈ $0.036 / ~3.2₽, per image ≈ $0.039 / ~3.5₽):
  basic:    30п+5ф → ~114₽ cost, ~360₽ net (after YuKassa+НПД) → margin ~246₽
  standard: 80п+15ф → ~309₽ cost, ~638₽ net → margin ~329₽
  pro:      200п+50ф → ~815₽ cost, ~1193₽ net → margin ~378₽
  price_rub is the canonical price for landing/oferta; stars used inside Telegram.
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
    price_rub: int                  # monthly price in rubles (0 = free)
    price_rub_year: int             # annual price in rubles (≈10 months, ~17% off)
    stars: int                      # Telegram Stars equivalent (kept for payment invoice)
    stars_year: int                 # Telegram Stars for annual payment
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
        "price_rub": 0,
        "price_rub_year": 0,
        "stars": 0,
        "stars_year": 0,
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
        "price_rub": 0,
        "price_rub_year": 0,
        "stars": 0,
        "stars_year": 0,
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
        "price_rub": 390,
        "price_rub_year": 3_890,   # ~325₽/мес, экономия 790₽
        "stars": 290,
        "stars_year": 2_420,       # 290 × 10 (2 месяца бесплатно)
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
        "price_rub": 690,
        "price_rub_year": 6_890,   # ~574₽/мес, экономия 1 390₽
        "stars": 590,
        "stars_year": 4_920,       # 590 × 10
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
        "price_rub": 1_290,
        "price_rub_year": 12_890,  # ~1074₽/мес, экономия 2 590₽
        "stars": 990,
        "stars_year": 8_250,       # 990 × 10
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
