"""Subscription middleware: checks plan limits and feature access per request."""
from typing import Any, Callable

from aiogram import Bot
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.database import get_active_plan, get_monthly_usage, ensure_free_plan
from bot.plans import get_plan, can_use_feature, FEATURE_NAMES

FREE_COMMANDS = {"/start", "/help"}

# callback_data prefixes that require a specific feature
_FEATURE_GATES = {
    "trend:":              "trends",
    "topicsearch:":        "trends",
    "plan:":               "content_plan",
    "sched:":              "schedule",
    "schedule:":           "schedule",
    "settings:setup_channel": "autopublish",
    "publish:channel:go":     "autopublish",
}

# Actions that count toward monthly limits
_POST_ACTIONS   = {"post:regenerate", "plan:write:"}
_IMAGE_ACTIONS  = {"image:generate"}


def _requires_feature(event: Message | CallbackQuery) -> str | None:
    """Return feature name if this event requires a gated feature, else None."""
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        for prefix, feature in _FEATURE_GATES.items():
            if data.startswith(prefix):
                return feature
    if isinstance(event, Message):
        text = event.text or ""
        if text in ("🔥 Тренды", "🔍 Поиск по теме"):
            return "trends"
        if text == "📋 Контент-план":
            return "content_plan"
        if text == "⏰ Расписание":
            return "schedule"
        if text.startswith("/channel"):
            return "autopublish"
    return None


def _is_post_generation(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        text = event.text or ""
        return text == "✏️ Написать пост"
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        return data == "post:regenerate" or data.startswith("plan:write:")
    return False


def _is_image_generation(event: TelegramObject) -> bool:
    if isinstance(event, CallbackQuery):
        return (event.data or "") == "image:generate"
    return False


async def _send_limit_message(bot: Bot, user_id: int, text: str) -> None:
    from bot.keyboards import plans_kb
    await bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=plans_kb())


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Always allow free commands
        if isinstance(event, Message):
            text = event.text or ""
            if any(text.startswith(cmd) for cmd in FREE_COMMANDS):
                return await handler(event, data)

        # Downgrade expired trial to free silently
        await ensure_free_plan(user.id)

        plan_name = await get_active_plan(user.id)
        plan = get_plan(plan_name)
        bot: Bot = data["bot"]

        # Feature gate check
        feature = _requires_feature(event)
        if feature and not can_use_feature(plan_name, feature):
            feature_label = FEATURE_NAMES.get(feature, feature)
            await _send_limit_message(
                bot, user.id,
                f"🔒 *{feature_label}* недоступен на тарифе *{plan['emoji']} {plan['name']}*.\n\n"
                f"Улучши тариф чтобы получить доступ:"
            )
            if isinstance(event, CallbackQuery):
                await event.answer()
            return

        # Monthly post limit check
        if _is_post_generation(event):
            limit = plan["posts_per_month"]
            if limit is not None:
                used = await get_monthly_usage(user.id, "post_generated")
                if used >= limit:
                    await _send_limit_message(
                        bot, user.id,
                        f"📊 Лимит постов на этот месяц исчерпан.\n"
                        f"На тарифе *{plan['emoji']} {plan['name']}*: {limit} постов/мес, использовано: {used}.\n\n"
                        f"Улучши тариф для продолжения:"
                    )
                    if isinstance(event, CallbackQuery):
                        await event.answer()
                    return

        # Monthly image limit check
        if _is_image_generation(event):
            limit = plan["images_per_month"]
            if limit is not None:
                used = await get_monthly_usage(user.id, "image_generated")
                if used >= limit:
                    await _send_limit_message(
                        bot, user.id,
                        f"🖼 Лимит картинок на этот месяц исчерпан.\n"
                        f"На тарифе *{plan['emoji']} {plan['name']}*: {limit} картинок/мес, использовано: {used}.\n\n"
                        f"Улучши тариф для продолжения:"
                    )
                    if isinstance(event, CallbackQuery):
                        await event.answer()
                    return

        return await handler(event, data)
