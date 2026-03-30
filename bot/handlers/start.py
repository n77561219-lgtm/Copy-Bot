import os
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from bot.config import settings
from bot.keyboards import main_menu, style_keyboard

router = Router()


def _style_loaded() -> bool:
    return os.path.exists(settings.style_profile_path)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Я твой персональный копирайтер.\n\n"
        "Я умею:\n"
        "✍️ Писать посты в твоём стиле\n"
        "📋 Создавать контент-планы\n"
        "🔧 Редактировать тексты\n\n"
        "Для начала загрузи примеры своих постов через «Мой стиль», и я начну писать как ты.",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 Как пользоваться:\n\n"
        "✏️ Написать пост — нажми кнопку или напиши тему\n"
        "📋 Контент-план — план на N дней\n"
        "🎨 Мой стиль — загрузить или посмотреть текущий стиль\n"
        "⚙️ Настройки — параметры бота\n\n"
        "Команды:\n"
        "/plan [дней] — создать контент-план\n"
        "/show_plan — текущий контент-план\n"
        "/upload — инструкция по загрузке стиля",
        reply_markup=main_menu(),
    )


@router.message(Command("upload"))
async def cmd_upload(message: Message) -> None:
    await message.answer(
        "📤 Как загрузить примеры стиля:\n\n"
        "1. Зайди в Telegram Desktop\n"
        "2. Открой свой канал → ··· → Экспорт истории канала\n"
        "3. Выбери формат JSON\n"
        "4. Отправь файл result.json сюда\n\n"
        "Или просто отправь свой Tone of Voice документ (.md)",
        reply_markup=main_menu(),
    )
