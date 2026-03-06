from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.config import settings
from bot.db.boards import get_board, list_boards
from bot.db.work_logs import get_logs_by_board, get_logs_by_employee, get_logs_by_date, search_logs
from bot.keyboards.inline import CATEGORIES, pagination_keyboard, boards_keyboard

router = Router()


def format_logs(logs: list[dict], show_author: bool, show_board: bool = False) -> str:
    if not logs:
        return "Записей не найдено."

    lines = []
    for log in logs:
        header = f"#{log['id']} | {log['created_at']}"
        if show_author and "full_name" in log:
            pos = f" ({log['position']})" if log.get("position") else ""
            header += f" | {log['full_name']}{pos}"
        if show_board:
            header += f" | {log['board_serial']}"
        cat_name = CATEGORIES.get(log["category"], log["category"])
        desc = log["description"][:120]
        if len(log["description"]) > 120:
            desc += "..."
        lines.append(f"{header}\n{cat_name}: {desc}")

    return "\n\n".join(lines)


@router.message(Command("history"))
async def cmd_history(message: Message, employee: dict) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        boards = await list_boards()
        if not boards:
            await message.answer("Нет зарегистрированных бортов.")
            return
        await message.answer(
            "Выберите борт для просмотра истории:",
            reply_markup=boards_keyboard(boards, action="hist"),
        )
        return

    serial = args[1].upper()
    await _show_board_history(message, serial, employee)


async def _show_board_history(
    target: Message | CallbackQuery, serial: str, employee: dict
) -> None:
    board = await get_board(serial)
    if not board:
        text = f"Борт {serial} не найден."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)
        return

    can_see_all = employee["role"] in ("lead", "admin")
    emp_filter = None if can_see_all else employee["telegram_id"]
    page_size = settings.page_size

    logs, total = await get_logs_by_board(serial, employee_id=emp_filter, limit=page_size)

    if can_see_all:
        header = f"Борт {serial} - все работы ({total}):\n\n"
    else:
        header = f"Борт {serial} - ваши работы ({total}):\n\n"

    text = header + format_logs(logs, show_author=can_see_all)

    reply_markup = None
    if total > page_size:
        prefix = f"hist_b:{serial}:{1 if can_see_all else 0}"
        reply_markup = pagination_keyboard(prefix, 0, total, page_size)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=reply_markup)
    else:
        await target.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("pick_hist:"))
async def pick_hist_board(callback: CallbackQuery, employee: dict) -> None:
    serial = callback.data.split(":")[1]
    await _show_board_history(callback, serial, employee)
    await callback.answer()


@router.callback_query(F.data.startswith("pick_hist_pg:"))
async def pick_hist_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    boards = await list_boards()
    await callback.message.edit_reply_markup(
        reply_markup=boards_keyboard(boards, page, action="hist")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("hist_b:"))
async def history_board_page(callback: CallbackQuery, employee: dict) -> None:
    parts = callback.data.split(":")
    serial = parts[1]
    can_see_all = parts[2] == "1"
    page = int(parts[3])
    page_size = settings.page_size

    emp_filter = None if can_see_all else employee["telegram_id"]
    logs, total = await get_logs_by_board(serial, employee_id=emp_filter, limit=page_size, offset=page * page_size)

    if can_see_all:
        header = f"Борт {serial} - все работы ({total}):\n\n"
    else:
        header = f"Борт {serial} - ваши работы ({total}):\n\n"

    text = header + format_logs(logs, show_author=can_see_all)
    prefix = f"hist_b:{serial}:{1 if can_see_all else 0}"
    await callback.message.edit_text(text, reply_markup=pagination_keyboard(prefix, page, total, page_size))
    await callback.answer()


@router.message(Command("history_my"))
async def cmd_history_my(message: Message, employee: dict) -> None:
    page_size = settings.page_size
    logs, total = await get_logs_by_employee(employee["telegram_id"], limit=page_size)

    text = f"Ваши работы ({total}):\n\n" + format_logs(logs, show_author=False, show_board=True)

    reply_markup = None
    if total > page_size:
        prefix = f"hist_my:{employee['telegram_id']}"
        reply_markup = pagination_keyboard(prefix, 0, total, page_size)

    await message.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("hist_my:"))
async def history_my_page(callback: CallbackQuery, employee: dict) -> None:
    parts = callback.data.split(":")
    page = int(parts[2])
    page_size = settings.page_size

    logs, total = await get_logs_by_employee(employee["telegram_id"], limit=page_size, offset=page * page_size)
    text = f"Ваши работы ({total}):\n\n" + format_logs(logs, show_author=False, show_board=True)
    prefix = f"hist_my:{employee['telegram_id']}"
    await callback.message.edit_text(text, reply_markup=pagination_keyboard(prefix, page, total, page_size))
    await callback.answer()


@router.message(Command("history_date"))
async def cmd_history_date(message: Message, employee: dict) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /history_date <YYYY-MM-DD>")
        return

    date = args[1].strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await message.answer("Неверный формат даты. Используйте YYYY-MM-DD, например: 2026-03-06")
        return

    can_see_all = employee["role"] in ("lead", "admin")
    emp_filter = None if can_see_all else employee["telegram_id"]
    page_size = settings.page_size

    logs, total = await get_logs_by_date(date, employee_id=emp_filter, limit=page_size)

    text = f"Работы за {date} ({total}):\n\n" + format_logs(logs, show_author=can_see_all, show_board=True)

    reply_markup = None
    if total > page_size:
        prefix = f"hist_d:{date}:{1 if can_see_all else 0}"
        reply_markup = pagination_keyboard(prefix, 0, total, page_size)

    await message.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("hist_d:"))
async def history_date_page(callback: CallbackQuery, employee: dict) -> None:
    parts = callback.data.split(":")
    date = parts[1]
    can_see_all = parts[2] == "1"
    page = int(parts[3])
    page_size = settings.page_size

    emp_filter = None if can_see_all else employee["telegram_id"]
    logs, total = await get_logs_by_date(date, employee_id=emp_filter, limit=page_size, offset=page * page_size)

    text = f"Работы за {date} ({total}):\n\n" + format_logs(logs, show_author=can_see_all, show_board=True)
    prefix = f"hist_d:{date}:{1 if can_see_all else 0}"
    await callback.message.edit_text(text, reply_markup=pagination_keyboard(prefix, page, total, page_size))
    await callback.answer()


@router.message(Command("search"))
async def cmd_search(message: Message, employee: dict) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /search <текст>")
        return

    query = args[1].strip()
    can_see_all = employee["role"] in ("lead", "admin")
    emp_filter = None if can_see_all else employee["telegram_id"]
    page_size = settings.page_size

    logs, total = await search_logs(query, employee_id=emp_filter, limit=page_size)

    text = f"Поиск \"{query}\" ({total}):\n\n" + format_logs(logs, show_author=can_see_all, show_board=True)

    reply_markup = None
    if total > page_size:
        prefix = f"srch:{query}:{1 if can_see_all else 0}"
        reply_markup = pagination_keyboard(prefix, 0, total, page_size)

    await message.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("srch:"))
async def search_page(callback: CallbackQuery, employee: dict) -> None:
    parts = callback.data.split(":")
    # srch:query_text:can_see_all:page
    query = parts[1]
    can_see_all = parts[2] == "1"
    page = int(parts[3])
    page_size = settings.page_size

    emp_filter = None if can_see_all else employee["telegram_id"]
    logs, total = await search_logs(query, employee_id=emp_filter, limit=page_size, offset=page * page_size)

    text = f"Поиск \"{query}\" ({total}):\n\n" + format_logs(logs, show_author=can_see_all, show_board=True)
    prefix = f"srch:{query}:{1 if can_see_all else 0}"
    await callback.message.edit_text(text, reply_markup=pagination_keyboard(prefix, page, total, page_size))
    await callback.answer()
