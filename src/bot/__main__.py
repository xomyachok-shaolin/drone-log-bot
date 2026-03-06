import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, Message

from bot.config import settings
from bot.db.connection import init_db, close_db
from bot.db.migrations import run_migrations
from bot.handlers import setup_routers
from bot.middleware.auth import AuthMiddleware

cancel_router = Router()


@cancel_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного действия для отмены.")
        return
    await state.clear()
    await message.answer("Действие отменено.")


async def start() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
    )
    log = structlog.get_logger()

    # Init DB
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await init_db(str(settings.db_path))
    await run_migrations(db)
    log.info("database_ready", path=str(settings.db_path))

    # Bot setup
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # /cancel first (catches in any FSM state before other routers)
    dp.include_router(cancel_router)
    # All other handlers
    dp.include_router(setup_routers())

    await bot.set_my_commands([
        BotCommand(command="log", description="Записать работу на борте"),
        BotCommand(command="log_tpl", description="Записать по шаблону"),
        BotCommand(command="history", description="История по борту"),
        BotCommand(command="history_my", description="Мои работы"),
        BotCommand(command="history_date", description="Работы за дату"),
        BotCommand(command="search", description="Поиск по описанию"),
        BotCommand(command="board_list", description="Список бортов"),
        BotCommand(command="board_info", description="Информация о борте"),
        BotCommand(command="export", description="Экспорт истории борта в PDF"),
        BotCommand(command="stats", description="Статистика работ"),
        BotCommand(command="templates", description="Шаблоны работ"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="cancel", description="Отменить действие"),
    ])
    await bot.set_my_description(
        "Журнал технического обслуживания БПЛА\n\n"
        "Фиксируйте все работы на бортах: сборка, замена компонентов, ремонт, "
        "калибровка, обновление прошивок. Прикладывайте фото.\n\n"
        "Полная история по каждому борту с экспортом в PDF."
    )
    await bot.set_my_short_description(
        "Журнал техобслуживания БПЛА - учёт работ, история по бортам"
    )
    log.info("bot_commands_registered")

    @dp.errors()
    async def on_error(event, exception):
        log.error("unhandled_error", error=str(exception), exc_info=exception)

    log.info("bot_starting")
    try:
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()
        log.info("bot_stopped")


def main() -> None:
    asyncio.run(start())


if __name__ == "__main__":
    main()
