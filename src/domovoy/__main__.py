"""Run the bot with ``python -m domovoy``."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from domovoy.config import Settings, load_validated_configs
from domovoy.database import initialize_database
from domovoy.handlers import router


async def main() -> None:
    settings = Settings.from_env()
    load_validated_configs()
    initialize_database(settings.database_path)

    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    await dispatcher.start_polling(
        bot,
        allowed_updates=dispatcher.resolve_used_update_types(),
        settings=settings,
    )


if __name__ == "__main__":
    asyncio.run(main())
