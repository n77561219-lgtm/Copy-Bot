import asyncio
import logging
from typing import Any, Callable

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from aiogram.dispatcher.middlewares.base import BaseMiddleware

from bot.config import settings
from bot.database import init_db
from bot.handlers import start, upload, generate
from bot.handlers import settings as settings_handler
from bot.handlers import trends as trends_handler
from bot.handlers import topic_search as topic_search_handler
from bot.handlers import payment as payment_handler
from bot.handlers import profile as profile_handler
from bot.handlers import admin as admin_handler
from bot.subscription_middleware import SubscriptionMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    def __init__(self, allowed: set[int]) -> None:
        self.allowed = allowed

    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user and user.id not in self.allowed:
            # answer via the bot stored in data
            bot: Bot = data["bot"]
            chat_id = getattr(event, "chat", None)
            if chat_id:
                await bot.send_message(chat_id.id, "⛔ Доступ запрещён.")
            return
        return await handler(event, data)


async def main() -> None:
    await init_db(settings.database_url)

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    allowed = settings.allowed_user_ids
    if allowed:
        mw = AuthMiddleware(allowed)
        dp.message.middleware(mw)
        dp.callback_query.middleware(mw)
        logger.info("Auth enabled for user IDs: %s", allowed)
    else:
        logger.info("Auth disabled — all users allowed")

    sub_mw = SubscriptionMiddleware()
    dp.message.middleware(sub_mw)
    dp.callback_query.middleware(sub_mw)

    dp.include_router(start.router)
    dp.include_router(admin_handler.router)
    dp.include_router(payment_handler.router)
    dp.include_router(profile_handler.router)
    dp.include_router(upload.router)
    dp.include_router(settings_handler.router)
    dp.include_router(trends_handler.router)
    dp.include_router(topic_search_handler.router)
    dp.include_router(generate.router)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
