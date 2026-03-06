import asyncio
import functools
import tempfile
from datetime import datetime
from pathlib import Path

import structlog

from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from bot.db.boards import list_boards, restore_board
from bot.db.employees import list_employees, set_role
from bot.db.work_logs import (
    delete_log, get_log, get_logs_by_board, get_photos_batch,
    restore_log, update_log, get_stats, get_logs_for_export,
)
from bot.export_pdf import build_board_pdf, build_full_pdf
from bot.keyboards.inline import (
    CATEGORIES, boards_keyboard, categories_keyboard, edit_field_keyboard,
)
from bot.states.work_log import EditLogStates

alog = structlog.get_logger()

router = Router()


# --- set_role ---

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


# --- users ---

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


# --- delete / restore log ---

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
        await message.answer(f"Запись #{log_id} удалена.")
    else:
        await message.answer(f"Запись #{log_id} не найдена.")


@router.message(Command("restore_log"))
async def cmd_restore_log(message: Message, employee: dict) -> None:
    if employee["role"] != "admin":
        await message.answer("Только админ может восстанавливать записи.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /restore_log <id>")
        return

    try:
        log_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    ok = await restore_log(log_id)
    if ok:
        alog.info("log_restored", log_id=log_id, by=employee["telegram_id"])
        await message.answer(f"Запись #{log_id} восстановлена.")
    else:
        await message.answer(f"Запись #{log_id} не найдена среди удалённых.")


@router.message(Command("restore_board"))
async def cmd_restore_board(message: Message, employee: dict) -> None:
    if employee["role"] != "admin":
        await message.answer("Только админ может восстанавливать борта.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /restore_board <серийный_номер>")
        return

    serial = args[1].upper()
    ok = await restore_board(serial)
    if ok:
        alog.info("board_restored", serial=serial, by=employee["telegram_id"])
        await message.answer(f"Борт {serial} восстановлен.")
    else:
        await message.answer(f"Борт {serial} не найден среди удалённых.")


# --- edit log ---

@router.message(Command("edit_log"))
async def cmd_edit_log(message: Message, state: FSMContext, employee: dict) -> None:
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /edit_log <id>")
        return

    try:
        log_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    entry = await get_log(log_id)
    if not entry:
        await message.answer(f"Запись #{log_id} не найдена.")
        return

    # Only author or admin can edit
    if entry["employee_id"] != employee["telegram_id"] and employee["role"] != "admin":
        await message.answer("Можно редактировать только свои записи.")
        return

    cat_name = CATEGORIES.get(entry["category"], entry["category"])
    await state.set_state(EditLogStates.choosing_field)
    await state.update_data(edit_log_id=log_id, edit_category=entry["category"], edit_description=entry["description"])
    await message.answer(
        f"Запись #{log_id}\n"
        f"Категория: {cat_name}\n"
        f"Описание: {entry['description'][:200]}\n\n"
        f"Что изменить?",
        reply_markup=edit_field_keyboard(log_id),
    )


@router.callback_query(EditLogStates.choosing_field, F.data.startswith("edit_f:"))
async def edit_field_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    field = parts[1]

    if field == "cancel":
        await state.clear()
        await callback.message.edit_text("Редактирование отменено.")
        await callback.answer()
        return

    if field == "cat":
        await state.set_state(EditLogStates.editing_category)
        await callback.message.edit_text("Выберите новую категорию:", reply_markup=categories_keyboard())
    elif field == "desc":
        await state.set_state(EditLogStates.editing_description)
        await callback.message.edit_text("Введите новое описание:")
    await callback.answer()


@router.callback_query(EditLogStates.editing_category, F.data.startswith("cat:"))
async def edit_category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":")[1]
    data = await state.get_data()
    ok = await update_log(data["edit_log_id"], category, data["edit_description"])
    await state.clear()
    if ok:
        cat_name = CATEGORIES.get(category, category)
        await callback.message.edit_text(f"Категория записи #{data['edit_log_id']} изменена на: {cat_name}")
    else:
        await callback.message.edit_text("Не удалось обновить запись.")
    await callback.answer()


@router.message(EditLogStates.editing_description, F.text)
async def edit_description_entered(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) < 5:
        await message.answer("Описание слишком короткое (минимум 5 символов).")
        return
    data = await state.get_data()
    ok = await update_log(data["edit_log_id"], data["edit_category"], text)
    await state.clear()
    if ok:
        await message.answer(f"Описание записи #{data['edit_log_id']} обновлено.")
    else:
        await message.answer("Не удалось обновить запись.")


# --- stats ---

@router.message(Command("stats"))
async def cmd_stats(message: Message, employee: dict) -> None:
    if employee["role"] not in ("lead", "admin"):
        await message.answer("Статистика доступна руководителям и админам.")
        return

    args = message.text.split()
    date_from = args[1] if len(args) > 1 else None
    date_to = args[2] if len(args) > 2 else None

    # Validate dates
    for d in (date_from, date_to):
        if d:
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                await message.answer("Формат дат: /stats [YYYY-MM-DD] [YYYY-MM-DD]")
                return

    stats = await get_stats(date_from, date_to)

    period = ""
    if date_from and date_to:
        period = f" за {date_from} - {date_to}"
    elif date_from:
        period = f" с {date_from}"

    text = f"Статистика{period}\n\nВсего записей: {stats['total']}\n"

    if stats["by_board"]:
        text += "\nПо бортам:\n"
        for row in stats["by_board"][:10]:
            text += f"  {row['board_serial']}: {row['cnt']}\n"

    if stats["by_employee"]:
        text += "\nПо сотрудникам:\n"
        for row in stats["by_employee"][:10]:
            text += f"  {row['full_name']}: {row['cnt']}\n"

    if stats["by_category"]:
        text += "\nПо категориям:\n"
        for row in stats["by_category"]:
            cat_name = CATEGORIES.get(row["category"], row["category"])
            text += f"  {cat_name}: {row['cnt']}\n"

    await message.answer(text)


# --- photo download helpers ---

async def _download_one(bot: Bot, photo: dict, log_id: int, tmp_dir: str) -> tuple[int, str | None]:
    try:
        file = await bot.get_file(photo["file_id"])
        local_path = Path(tmp_dir) / f"photo_{log_id}_{photo['id']}.jpg"
        await bot.download_file(file.file_path, str(local_path))
        return log_id, str(local_path)
    except Exception:
        return log_id, None


async def _download_photos(bot: Bot, log_ids: list[int], tmp_dir: str) -> dict[int, list[str]]:
    """Download photos for given log IDs in parallel. Single DB query + concurrent downloads."""
    photos_by_log = await get_photos_batch(log_ids)
    if not photos_by_log:
        return {}

    tasks = [
        _download_one(bot, photo, log_id, tmp_dir)
        for log_id, photos in photos_by_log.items()
        for photo in photos
    ]
    results = await asyncio.gather(*tasks)

    out: dict[int, list[str]] = {}
    for log_id, path in results:
        if path:
            out.setdefault(log_id, []).append(path)
    return out


# --- export ---

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
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None, functools.partial(build_board_pdf, serial, logs, photo_paths)
        )

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
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None, functools.partial(build_full_pdf, all_logs, photo_paths)
        )

    doc = BufferedInputFile(pdf_bytes, filename="all_history.pdf")
    await message.answer_document(doc, caption=f"Полная выгрузка ({total_count} записей)")


@router.message(Command("export_period"))
async def cmd_export_period(message: Message, employee: dict, bot: Bot) -> None:
    if employee["role"] not in ("lead", "admin"):
        await message.answer("Экспорт по периоду доступен руководителям и админам.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /export_period <YYYY-MM-DD> <YYYY-MM-DD>")
        return

    date_from, date_to = args[1], args[2]
    for d in (date_from, date_to):
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            await message.answer("Неверный формат даты. Используйте YYYY-MM-DD")
            return

    all_logs, total_count = await get_logs_for_export(date_from=date_from, date_to=date_to)
    if total_count == 0:
        await message.answer(f"Нет записей за период {date_from} - {date_to}.")
        return

    await message.answer("Формирую PDF, подождите...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        all_log_ids = [entry["id"] for logs in all_logs.values() for entry in logs]
        photo_paths = await _download_photos(bot, all_log_ids, tmp_dir)
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None, functools.partial(build_full_pdf, all_logs, photo_paths)
        )

    doc = BufferedInputFile(pdf_bytes, filename=f"export_{date_from}_{date_to}.pdf")
    await message.answer_document(doc, caption=f"Экспорт за {date_from} - {date_to} ({total_count} записей)")


# --- help ---

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
        "/edit_log <id> - редактировать запись\n"
        "/template_add - создать шаблон работы\n"
        "/templates - список шаблонов\n"
        "/start - обновить профиль\n"
        "/cancel - отменить текущее действие\n"
    )

    if employee["role"] in ("lead", "admin"):
        text += (
            "\nРуководитель:\n"
            "/board_add <борт> [модель] - добавить борт\n"
            "/stats [от] [до] - статистика\n"
            "/export_period <от> <до> - экспорт за период\n"
        )

    if employee["role"] == "admin":
        text += (
            "\nАдмин:\n"
            "/set_role <telegram_id> <worker|lead|admin> - назначить роль\n"
            "/users - список сотрудников\n"
            "/delete_log <id> - удалить запись\n"
            "/restore_log <id> - восстановить запись\n"
            "/board_delete <борт> - удалить борт\n"
            "/restore_board <борт> - восстановить борт\n"
            "/export_all - полная выгрузка\n"
        )

    await message.answer(text)
