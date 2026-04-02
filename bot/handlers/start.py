from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from bot.database import create_trial, get_subscription, get_style_examples_count
from bot.keyboards import main_menu

router = Router()


def _onboarding_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 Загрузить стиль сейчас", callback_data="onboarding:upload"))
    b.row(InlineKeyboardButton(text="➡️ Пропустить", callback_data="onboarding:skip"))
    return b.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    is_new = await _is_new_user(user_id)
    await create_trial(user_id)

    sub = await get_subscription(user_id)
    if sub and sub["expires_at"] > datetime.now(timezone.utc):
        days_left = (sub["expires_at"] - datetime.now(timezone.utc)).days
        trial_note = f"\n\n⏳ Пробный период: ещё *{days_left} дн.*"
    else:
        trial_note = ""

    if is_new:
        await message.answer(
            "👋 Привет! Я твой персональный копирайтер.\n\n"
            "Я пишу посты *в твоём стиле* — достаточно один раз загрузить примеры.\n\n"
            "✍️ Посты и тексты\n"
            "📋 Контент-план на несколько недель\n"
            "🔥 Тренды по твоей нише\n"
            "🖼 Картинки к постам"
            + trial_note,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        await message.answer(
            "🎯 *Шаг 1 из 2 — загрузи примеры своих постов*\n\n"
            "Экспортируй историю своего Telegram-канала в JSON и отправь файл сюда.\n\n"
            "_Или загрузи Tone of Voice документ в формате .md_",
            parse_mode="Markdown",
            reply_markup=_onboarding_kb(),
        )
    else:
        await message.answer(
            "👋 С возвращением!"
            + trial_note,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )


async def _is_new_user(user_id: int) -> bool:
    """True if user has no style examples uploaded yet."""
    count = await get_style_examples_count(user_id)
    return count == 0


@router.callback_query(F.data == "onboarding:upload")
async def cb_onboarding_upload(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📤 *Как загрузить примеры стиля:*\n\n"
        "1. Открой Telegram Desktop\n"
        "2. Зайди в свой канал → ··· → Экспорт истории\n"
        "3. Формат: *JSON*, галочка только на «Текстовые сообщения»\n"
        "4. Отправь файл `result.json` сюда\n\n"
        "Или просто отправь `.md` файл с описанием своего стиля.",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "onboarding:skip")
async def cb_onboarding_skip(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "✅ Хорошо, можешь загрузить стиль позже через кнопку *🧠 Мой стиль*.\n\n"
        "Пока что я буду писать в нейтральном стиле.",
        parse_mode="Markdown",
    )
    await callback.answer()


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
