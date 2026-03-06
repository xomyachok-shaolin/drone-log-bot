from aiogram import Router

from bot.handlers import start, board, log, history, admin, template


def setup_routers() -> Router:
    router = Router()
    router.include_router(start.router)
    router.include_router(board.router)
    router.include_router(template.router)
    router.include_router(log.router)
    router.include_router(history.router)
    router.include_router(admin.router)
    return router
