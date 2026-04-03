"""Auto-publish posts to a Telegram channel.

User sets their channel username once (e.g. @mychannel or -100xxxxxxxxx).
Then after generating a post they can tap "📢 Опубликовать" to send it directly.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from bot.database import get_preference, set_preference

router = Router()


class PublishStates(StatesGroup):
    waiting_channel = State()


async def get_channel(user_id: int) -> str | None:
    return await get_preference(user_id, "publish_channel")


@router.message(Command("channel"))
async def cmd_channel(message: Message, state: FSMContext) -> None:
    channel = await get_channel(message.from_user.id)
    current = f"Текущий канал: `{channel}`\n\n" if channel else ""
    await message.answer(
        f"{current}"
        "Отправь username канала для автопубликации.\n\n"
        "Формат: `@mychannel` или `-1001234567890`\n\n"
        "⚠️ Бот должен быть добавлен в канал как **администратор** с правом публикации.",
        parse_mode="Markdown",
    )
    await state.set_state(PublishStates.waiting_channel)


@router.message(PublishStates.waiting_channel)
async def handle_channel_input(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    user_id = message.from_user.id

    # Validate: check bot can send to the channel
    try:
        test = await message.bot.send_message(text, "✅ Канал подключён к Copy-Bot!")
        await test.delete()
        await set_preference(user_id, "publish_channel", text)
        await state.clear()
        await message.answer(
            f"✅ Канал *{text}* подключён!\n\n"
            "Теперь после генерации поста появится кнопка «📢 Опубликовать».",
            parse_mode="Markdown",
        )
    except TelegramForbiddenError:
        await message.answer(
            "❌ Бот не может отправить сообщение в этот канал.\n\n"
            "Добавь бота как администратора канала с правом публикации постов."
        )
    except TelegramBadRequest as e:
        await message.answer(f"❌ Неверный chat ID: {e}\n\nПроверь username канала.")


@router.callback_query(F.data.startswith("publish:channel:"))
async def cb_publish_to_channel(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    post_text = callback.data[len("publish:channel:"):]

    # post_text is stored in FSM data, not callback (too long)
    # We use state data via a workaround: store in preferences temporarily
    channel = await get_channel(user_id)
    if not channel:
        await callback.answer("Канал не настроен. Используй /channel", show_alert=True)
        return

    stored = await get_preference(user_id, "pending_publish_text")
    if not stored:
        await callback.answer("Текст поста не найден.", show_alert=True)
        return

    try:
        await callback.bot.send_message(channel, stored, parse_mode="Markdown")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Опубликовано в {channel}!")
    except Exception as e:
        await callback.answer(f"Ошибка публикации: {e}", show_alert=True)

    await callback.answer()


def publish_kb(has_channel: bool) -> InlineKeyboardBuilder | None:
    if not has_channel:
        return None
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📢 Опубликовать в канал", callback_data="publish:channel:go"))
    return b.as_markup()
