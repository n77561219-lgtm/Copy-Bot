from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from bot.database import create_trial, get_subscription
from bot.keyboards import main_menu, subscribe_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    await create_trial(user_id)

    sub = await get_subscription(user_id)
    from datetime import datetime, timezone
    if sub and sub["plan"] == "trial" and sub["expires_at"] > datetime.now(timezone.utc):
        days_left = (sub["expires_at"] - datetime.now(timezone.utc)).days
        trial_note = f"\n\n⏳ Пробный период: ещё *{days_left} дн.*"
    else:
        trial_note = ""

    await message.answer(
        "👋 Привет! Я твой персональный копирайтер.\n\n"
        "Я умею:\n"
        "✍️ Писать посты в твоём стиле\n"
        "📋 Создавать контент-планы\n"
        "🔥 Находить тренды для постов\n"
        "🖼 Генерировать картинки\n\n"
        "Для начала загрузи примеры своих постов через «Мой стиль», и я начну писать как ты."
        + trial_note,
        parse_mode="Markdown",
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
