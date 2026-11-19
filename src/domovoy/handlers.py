"""Initial Telegram entry points."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from domovoy.config import Settings, load_json_config


router = Router()


@router.message(Command("report"))
async def start_report_from_group(message: Message, settings: Settings) -> None:
    if message.chat.type == "private":
        await message.answer("Начните создание заявки из группового чата вашего дома.")
        return

    configured_chats = load_json_config("houses.json")["chats"]
    house = next(
        (item for item in configured_chats if item["telegram_chat_id"] == message.chat.id),
        None,
    )
    if house is None:
        await message.answer("Этот групповой чат ещё не настроен для создания заявок.")
        return

    bot = message.bot
    bot_user = await bot.get_me()
    deep_link = f"https://t.me/{bot_user.username}?start=report_{message.chat.id}"
    await message.answer(
        "Чтобы создать заявку, перейдите в личный чат с ботом:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Создать заявку", url=deep_link)]
            ]
        ),
    )


@router.message(CommandStart())
async def start_private_chat(message: Message, settings: Settings) -> None:
    if message.from_user is None:
        return

    if message.from_user.id == settings.admin_telegram_id:
        role_note = " Вы назначены начальным администратором."
    else:
        role_note = ""

    payload = (message.text or "").partition(" ")[2]
    if payload.startswith("report_"):
        try:
            source_chat_id = int(payload.removeprefix("report_"))
        except ValueError:
            source_chat_id = None
        chats = load_json_config("houses.json")["chats"]
        house = next(
            (item for item in chats if item["telegram_chat_id"] == source_chat_id),
            None,
        )
        if house is None:
            await message.answer("Не удалось определить дом. Запустите заявку из чата дома.")
            return
        await message.answer(
            f"Заявка для дома: {house['address']}.\n"
            "Мастер заполнения заявки будет добавлен на следующем этапе." + role_note
        )
        return

    await message.answer(
        "Добро пожаловать в Домовой. Чтобы создать заявку, используйте /report "
        "в групповом чате своего дома." + role_note
    )
