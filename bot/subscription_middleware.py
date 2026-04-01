"""Subscription paywall middleware.

Blocks access to the bot for users without an active subscription.
Free commands: /start, /help — always allowed.
"""
from typing import Any, Callable

from aiogram import Bot
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.database import is_subscribed
from bot.keyboards import subscribe_kb

FREE_COMMANDS = {"/start", "/help"}

PAYWALL_TEXT = (
    "⏳ *Твой пробный период закончился.*\n\n"
    "Чтобы продолжить пользоваться ботом — оформи подписку.\n\n"
    "💳 *490 Stars / месяц*\n"
    "Включает все функции без ограничений."
)


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

        # Allow free commands
        if isinstance(event, Message):
            text = event.text or ""
            if any(text.startswith(cmd) for cmd in FREE_COMMANDS):
                return await handler(event, data)

        # Check subscription
        if not await is_subscribed(user.id):
            bot: Bot = data["bot"]
            if isinstance(event, Message):
                await event.answer(PAYWALL_TEXT, parse_mode="Markdown", reply_markup=subscribe_kb())
            elif isinstance(event, CallbackQuery):
                await event.answer("Подписка истекла", show_alert=True)
                await bot.send_message(event.from_user.id, PAYWALL_TEXT, parse_mode="Markdown", reply_markup=subscribe_kb())
            return

        return await handler(event, data)
