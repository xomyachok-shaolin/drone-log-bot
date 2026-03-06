import asyncio
import tempfile
from pathlib import Path

import structlog

from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from bot.db.employees import list_employees, set_role
from bot.db.work_logs import delete_log, get_logs_by_board, get_photos
from bot.db.boards import list_boards
from bot.export_pdf import build_board_pdf, build_full_pdf
from bot.keyboards.inline import CATEGORIES, boards_keyboard

alog = structlog.get_logger()

router = Router()


@router.message(Command("set_role"))
async def cmd_set_role(message: Message, employee: dict) -> None:
    if employee["role"] != "admin":
        await message.answer("Только админ может назначать роли.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /set_role <telegram_id> <worker|lead|admin>")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return

    role = args[2].lower()
    if role not in ("worker", "lead", "admin"):
        await message.answer("Роль должна быть: worker, lead или admin")
        return

    ok = await set_role(target_id, role)
    if ok:
        alog.info("role_changed", target=target_id, role=role, by=employee["telegram_id"])
        await message.answer(f"Роль пользователя {target_id} изменена на {role}.")
    else:
        await message.answer(f"Пользователь {target_id} не найден.")


@router.message(Command("users"))
async def cmd_users(message: Message, employee: dict) -> None:
    if employee["role"] != "admin":
        await message.answer("Только админ может просматривать список пользователей.")
        return

    employees = await list_employees()
    if not employees:
        await message.answer("Нет зарегистрированных пользователей.")
        return

    lines = ["Сотрудники:\n"]
    for e in employees:
        pos = f", {e['position']}" if e.get("position") else ""
        lines.append(f"  {e['telegram_id']} | {e['full_name']}{pos} | {e['role']}")

    await message.answer("\n".join(lines))


@router.message(Command("delete_log"))
async def cmd_delete_log(message: Message, employee: dict) -> None:
    if employee["role"] != "admin":
        await message.answer("Только админ может удалять записи.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /delete_log <id>")
        return

    try:
        log_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    ok = await delete_log(log_id)
    if ok:
        alog.info("log_deleted", log_id=log_id, by=employee["telegram_id"])
        await message.answer(f"Запись #{log_id} скрыта (данные сохранены).")
    else:
        await message.answer(f"Запись #{log_id} не найдена.")


async def _download_one(bot: Bot, photo: dict, log_id: int, tmp_dir: str) -> str | None:
    try:
        file = await bot.get_file(photo["file_id"])
        local_path = Path(tmp_dir) / f"photo_{log_id}_{photo['id']}.jpg"
        await bot.download_file(file.file_path, str(local_path))
        return str(local_path)
    except Exception:
        return None


async def _download_photos(bot: Bot, log_ids: list[int], tmp_dir: str) -> dict[int, list[str]]:
    """Download photos for given log IDs in parallel. Returns {log_id: [local_path, ...]}."""
    # Collect all download tasks
    tasks: list[tuple[int, asyncio.Task]] = []
    for log_id in log_ids:
        photos = await get_photos(log_id)
        for photo in photos:
            task = asyncio.create_task(_download_one(bot, photo, log_id, tmp_dir))
            tasks.append((log_id, task))

    # Await all downloads concurrently
    result: dict[int, list[str]] = {}
    for log_id, task in tasks:
        path = await task
        if path:
            result.setdefault(log_id, []).append(path)
    return result


@router.message(Command("export"))
async def cmd_export(message: Message, employee: dict, bot: Bot) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        boards = await list_boards()
        if not boards:
            await message.answer("Нет зарегистрированных бортов.")
            return
        await message.answer(
            "Выберите борт для экспорта в PDF:",
            reply_markup=boards_keyboard(boards, action="export"),
        )
        return

    serial = args[1].upper()
    await _do_export(message, serial, employee, bot)


async def _do_export(
    target: Message | CallbackQuery, serial: str, employee: dict, bot: Bot
) -> None:
    can_see_all = employee["role"] in ("lead", "admin")
    emp_filter = None if can_see_all else employee["telegram_id"]

    logs, total = await get_logs_by_board(serial, employee_id=emp_filter, limit=10000)
    if not logs:
        text = f"Нет записей по борту {serial}."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)
        return

    if isinstance(target, CallbackQuery):
        await target.message.edit_text("Формирую PDF, подождите...")
        send_to = target.message
    else:
        await target.answer("Формирую PDF, подождите...")
        send_to = target

    with tempfile.TemporaryDirectory() as tmp_dir:
        log_ids = [entry["id"] for entry in logs]
        photo_paths = await _download_photos(bot, log_ids, tmp_dir)
        pdf_bytes = build_board_pdf(serial, logs, photo_paths)

    doc = BufferedInputFile(pdf_bytes, filename=f"{serial}_history.pdf")
    await send_to.answer_document(doc, caption=f"История борта {serial} ({total} записей)")


@router.callback_query(F.data.startswith("pick_exp:"))
async def pick_exp_board(callback: CallbackQuery, employee: dict, bot: Bot) -> None:
    serial = callback.data.split(":")[1]
    await _do_export(callback, serial, employee, bot)
    await callback.answer()


@router.callback_query(F.data.startswith("pick_exp_pg:"))
async def pick_exp_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    boards = await list_boards()
    await callback.message.edit_reply_markup(
        reply_markup=boards_keyboard(boards, page, action="export")
    )
    await callback.answer()


@router.message(Command("export_all"))
async def cmd_export_all(message: Message, employee: dict, bot: Bot) -> None:
    if employee["role"] != "admin":
        await message.answer("Только админ может выгружать все данные.")
        return

    boards = await list_boards()
    all_logs: dict[str, list[dict]] = {}
    total_count = 0
    for board in boards:
        logs, _ = await get_logs_by_board(board["serial"], limit=100000)
        if logs:
            all_logs[board["serial"]] = logs
            total_count += len(logs)

    if total_count == 0:
        await message.answer("Нет записей для экспорта.")
        return

    await message.answer("Формирую PDF, подождите...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        all_log_ids = [entry["id"] for serial_logs in all_logs.values() for entry in serial_logs]
        photo_paths = await _download_photos(bot, all_log_ids, tmp_dir)
        pdf_bytes = build_full_pdf(all_logs, photo_paths)

    doc = BufferedInputFile(pdf_bytes, filename="all_history.pdf")
    await message.answer_document(doc, caption=f"Полная выгрузка ({total_count} записей)")


@router.message(Command("help"))
async def cmd_help(message: Message, employee: dict) -> None:
    text = (
        "Доступные команды:\n\n"
        "/log - записать работу на борте\n"
        "/history <борт> - история по борту\n"
        "/history_my - мои работы\n"
        "/history_date <YYYY-MM-DD> - работы за дату\n"
        "/search <текст> - поиск по описанию\n"
        "/board_list - список бортов\n"
        "/board_info <борт> - информация о борте\n"
        "/export <борт> - экспорт истории борта в PDF\n"
        "/start - обновить профиль\n"
        "/cancel - отменить текущее действие\n"
    )

    if employee["role"] in ("lead", "admin"):
        text += "\nРуководитель:\n/board_add <борт> [модель] - добавить борт\n"

    if employee["role"] == "admin":
        text += (
            "\nАдмин:\n"
            "/set_role <telegram_id> <worker|lead|admin> - назначить роль\n"
            "/users - список сотрудников\n"
            "/delete_log <id> - удалить запись\n"
            "/board_delete <борт> - удалить борт\n"
            "/export_all - полная выгрузка\n"
        )

    await message.answer(text)
