import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.db.boards import create_board, delete_board, get_board, list_boards
from bot.db.work_logs import get_logs_by_board
from bot.keyboards.inline import CATEGORIES, boards_keyboard

router = Router()

SERIAL_PATTERN = re.compile(r"^[A-Z]{2,5}-\d{3,5}$")


@router.message(Command("board_add"))
async def cmd_board_add(message: Message, employee: dict) -> None:
    if employee["role"] not in ("lead", "admin"):
        await message.answer("Недостаточно прав. Добавлять борта могут руководители и админы.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Использование: /board_add <серийный_номер> [модель]\nПример: /board_add NSU-0042 Квадрокоптер X500")
        return

    serial = args[1].upper()
    if not SERIAL_PATTERN.match(serial):
        await message.answer(f"Неверный формат серийного номера: {serial}\nФормат: 2-5 букв, дефис, 3-5 цифр (например NSU-0042)")
        return

    existing = await get_board(serial)
    if existing:
        await message.answer(f"Борт {serial} уже зарегистрирован.")
        return

    model = args[2] if len(args) > 2 else None
    await create_board(serial, message.from_user.id, model)
    text = f"Борт {serial} зарегистрирован."
    if model:
        text += f"\nМодель: {model}"
    await message.answer(text)


@router.message(Command("board_list"))
async def cmd_board_list(message: Message, employee: dict) -> None:
    boards = await list_boards()
    if not boards:
        await message.answer("Нет зарегистрированных бортов.")
        return

    lines = ["Зарегистрированные борта:\n"]
    for b in boards:
        line = f"  {b['serial']}"
        if b.get("model"):
            line += f" - {b['model']}"
        lines.append(line)

    await message.answer("\n".join(lines))


@router.message(Command("board_delete"))
async def cmd_board_delete(message: Message, employee: dict) -> None:
    if employee["role"] != "admin":
        await message.answer("Только админ может удалять борта.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /board_delete <серийный_номер>")
        return

    serial = args[1].upper()
    ok = await delete_board(serial)
    if ok:
        await message.answer(f"Борт {serial} скрыт (данные сохранены).")
    else:
        await message.answer(f"Борт {serial} не найден.")


@router.message(Command("board_info"))
async def cmd_board_info(message: Message, employee: dict) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        boards = await list_boards()
        if not boards:
            await message.answer("Нет зарегистрированных бортов.")
            return
        await message.answer(
            "Выберите борт:", reply_markup=boards_keyboard(boards, action="info")
        )
        return

    serial = args[1].upper()
    await _show_board_info(message, serial, employee)


async def _show_board_info(
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
    logs, total = await get_logs_by_board(serial, employee_id=emp_filter, limit=5)

    text = f"Борт: {board['serial']}\n"
    if board.get("model"):
        text += f"Модель: {board['model']}\n"
    text += f"Зарегистрирован: {board['created_at']}\n"
    text += f"Всего работ: {total}\n"

    if logs:
        text += "\nПоследние работы:\n"
        for log_entry in logs:
            cat_name = CATEGORIES.get(log_entry["category"], log_entry["category"])
            text += f"\n#{log_entry['id']} | {log_entry['created_at']}"
            if can_see_all:
                text += f" | {log_entry['full_name']}"
            text += f"\n{cat_name}: {log_entry['description'][:80]}\n"

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text)
    else:
        await target.answer(text)


@router.callback_query(F.data.startswith("pick_info:"))
async def pick_info_board(callback: CallbackQuery, employee: dict) -> None:
    serial = callback.data.split(":")[1]
    await _show_board_info(callback, serial, employee)
    await callback.answer()


@router.callback_query(F.data.startswith("pick_info_pg:"))
async def pick_info_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    boards = await list_boards()
    await callback.message.edit_reply_markup(
        reply_markup=boards_keyboard(boards, page, action="info")
    )
    await callback.answer()
