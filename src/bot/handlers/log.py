import structlog

from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.config import settings
from bot.db.boards import list_boards
from bot.db.employees import get_last_board, update_last_board
from bot.db.work_logs import create_work_log, add_photo, add_document, find_duplicate

log = structlog.get_logger()
from bot.keyboards.inline import (
    boards_keyboard,
    categories_keyboard,
    confirm_keyboard,
    confirm_duplicate_keyboard,
    last_board_keyboard,
    photo_keyboard,
    CATEGORIES,
)
from bot.states.work_log import WorkLogStates

router = Router()


@router.message(Command("log"))
async def cmd_log(message: Message, state: FSMContext, employee: dict) -> None:
    boards = await list_boards()
    if not boards:
        await message.answer("Нет зарегистрированных бортов. Сначала добавьте борт: /board_add")
        return

    await state.update_data(photos=[], documents=[])

    # Check last used board
    last_board = await get_last_board(employee["telegram_id"])
    if last_board:
        board_exists = any(b["serial"] == last_board for b in boards)
        if board_exists:
            await state.update_data(last_board_serial=last_board)
            await state.set_state(WorkLogStates.choosing_board)
            await message.answer(
                "Последний борт или другой?",
                reply_markup=last_board_keyboard(last_board),
            )
            return

    await state.set_state(WorkLogStates.choosing_board)
    await message.answer("Выберите борт:", reply_markup=boards_keyboard(boards))


@router.callback_query(WorkLogStates.choosing_board, F.data == "last_b:yes")
async def last_board_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    serial = data["last_board_serial"]
    await state.update_data(board_serial=serial)
    await state.set_state(WorkLogStates.choosing_category)
    await callback.message.edit_text(
        f"Борт: {serial}\n\nКатегория работы:",
        reply_markup=categories_keyboard(),
    )
    await callback.answer()


@router.callback_query(WorkLogStates.choosing_board, F.data == "last_b:no")
async def last_board_no(callback: CallbackQuery, state: FSMContext) -> None:
    boards = await list_boards()
    await callback.message.edit_text(
        "Выберите борт:", reply_markup=boards_keyboard(boards)
    )
    await callback.answer()


@router.callback_query(WorkLogStates.choosing_board, F.data.startswith("board_pg:"))
async def boards_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":")[1])
    boards = await list_boards()
    await callback.message.edit_reply_markup(reply_markup=boards_keyboard(boards, page))
    await callback.answer()


@router.callback_query(WorkLogStates.choosing_board, F.data.startswith("board:"))
async def board_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    serial = callback.data.split(":")[1]
    await state.update_data(board_serial=serial)
    data = await state.get_data()

    # If template pre-filled category and description, skip to photo step
    if data.get("category") and data.get("description"):
        await state.set_state(WorkLogStates.waiting_photo)
        cat_name = CATEGORIES.get(data["category"], data["category"])
        await callback.message.edit_text(
            f"Борт: {serial}\n"
            f"Категория: {cat_name}\n"
            f"Описание: {data['description'][:100]}\n\n"
            "Приложить фото? Отправьте фото или нажмите \"Пропустить\".",
            reply_markup=photo_keyboard(),
        )
    else:
        await state.set_state(WorkLogStates.choosing_category)
        await callback.message.edit_text(
            f"Борт: {serial}\n\nКатегория работы:",
            reply_markup=categories_keyboard(),
        )
    await callback.answer()


@router.callback_query(WorkLogStates.choosing_category, F.data.startswith("cat:"))
async def category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":")[1]
    await state.update_data(category=category)
    await state.set_state(WorkLogStates.entering_description)

    data = await state.get_data()
    cat_name = CATEGORIES.get(category, category)
    await callback.message.edit_text(
        f"Борт: {data['board_serial']}\n"
        f"Категория: {cat_name}\n\n"
        f"Опишите, что было сделано:"
    )
    await callback.answer()


@router.message(WorkLogStates.entering_description, F.text)
async def description_entered(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) < 5:
        await message.answer("Описание слишком короткое (минимум 5 символов). Попробуйте ещё раз:")
        return

    await state.update_data(description=text)
    await state.set_state(WorkLogStates.waiting_photo)
    await message.answer(
        "Приложить фото? Отправьте фото или нажмите \"Пропустить\".",
        reply_markup=photo_keyboard(),
    )


MAX_PHOTOS = 10
MAX_DOCS = 5


@router.message(WorkLogStates.waiting_photo, F.photo)
async def photo_received(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1]  # largest size
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"Максимум {MAX_PHOTOS} фото. Нажмите \"Готово\".",
            reply_markup=photo_keyboard(),
        )
        return
    photos.append(photo.file_id)
    await state.update_data(photos=photos)
    remaining = MAX_PHOTOS - len(photos)
    hint = f" (ещё можно {remaining})" if remaining > 0 else " (максимум)"
    await message.answer(
        f"Фото добавлено ({len(photos)} шт.){hint}. Ещё фото/документ или \"Готово\"?",
        reply_markup=photo_keyboard(),
    )


@router.message(WorkLogStates.waiting_photo, F.document)
async def document_received(message: Message, state: FSMContext) -> None:
    doc = message.document
    data = await state.get_data()
    docs = data.get("documents", [])
    if len(docs) >= MAX_DOCS:
        await message.answer(
            f"Максимум {MAX_DOCS} документов. Нажмите \"Готово\".",
            reply_markup=photo_keyboard(),
        )
        return
    docs.append({"file_id": doc.file_id, "file_name": doc.file_name or "document"})
    await state.update_data(documents=docs)
    photos = data.get("photos", [])
    total = len(photos) + len(docs)
    await message.answer(
        f"Документ добавлен. Вложений: {total} шт. Ещё фото/документ или \"Готово\"?",
        reply_markup=photo_keyboard(),
    )


@router.callback_query(WorkLogStates.waiting_photo, F.data.in_({"photo:done", "photo:skip"}))
async def photo_done(callback: CallbackQuery, state: FSMContext, employee: dict) -> None:
    data = await state.get_data()

    # Check for duplicates
    dup = await find_duplicate(
        data["board_serial"], employee["telegram_id"], data["category"], data["description"]
    )
    if dup:
        await state.set_state(WorkLogStates.confirming)
        await state.update_data(dup_warned=True)
        await callback.message.edit_text(
            f"Похожая запись уже есть (#{dup['id']} от {dup['created_at']}).\n"
            "Всё равно сохранить?",
            reply_markup=confirm_duplicate_keyboard(),
        )
        await callback.answer()
        return

    await _show_confirm(callback, state, data)


async def _show_confirm(callback: CallbackQuery, state: FSMContext, data: dict) -> None:
    await state.set_state(WorkLogStates.confirming)
    cat_name = CATEGORIES.get(data["category"], data["category"])
    photos = data.get("photos", [])
    desc_preview = data["description"][:200]
    if len(data["description"]) > 200:
        desc_preview += "..."

    docs = data.get("documents", [])
    attach = f"Фото: {len(photos)} шт."
    if docs:
        attach += f", документов: {len(docs)} шт."

    text = (
        f"Проверьте запись:\n\n"
        f"Борт: {data['board_serial']}\n"
        f"Категория: {cat_name}\n"
        f"Описание: {desc_preview}\n"
        f"{attach}"
    )
    await callback.message.edit_text(text, reply_markup=confirm_keyboard())
    await callback.answer()


async def _save_log(callback: CallbackQuery, state: FSMContext, employee: dict, bot: Bot) -> None:
    data = await state.get_data()
    log_id = await create_work_log(
        board_serial=data["board_serial"],
        employee_id=employee["telegram_id"],
        category=data["category"],
        description=data["description"],
    )
    photos = data.get("photos", [])
    for file_id in photos:
        await add_photo(log_id, file_id)
    docs = data.get("documents", [])
    for d in docs:
        await add_document(log_id, d["file_id"], d.get("file_name"))

    # Remember last board
    await update_last_board(employee["telegram_id"], data["board_serial"])

    log.info(
        "work_logged",
        log_id=log_id,
        board=data["board_serial"],
        employee=employee["telegram_id"],
        category=data["category"],
        photos=len(photos),
    )
    await callback.message.edit_text(f"Работа записана (ID: {log_id})")
    await state.clear()
    await callback.answer()

    # Notify group chat
    if settings.notify_chat_id:
        cat_name = CATEGORIES.get(data["category"], data["category"])
        desc = data["description"][:100]
        notify_text = (
            f"Новая запись #{log_id}\n"
            f"Борт: {data['board_serial']}\n"
            f"Категория: {cat_name}\n"
            f"Описание: {desc}\n"
            f"Автор: {employee['full_name']}"
        )
        try:
            await bot.send_message(settings.notify_chat_id, notify_text)
        except Exception:
            log.warning("notify_failed", chat_id=settings.notify_chat_id)


@router.callback_query(WorkLogStates.confirming, F.data == "confirm:save")
async def confirm_save(callback: CallbackQuery, state: FSMContext, employee: dict, bot: Bot) -> None:
    await _save_log(callback, state, employee, bot)


@router.callback_query(WorkLogStates.confirming, F.data == "dup:save")
async def dup_save(callback: CallbackQuery, state: FSMContext, employee: dict, bot: Bot) -> None:
    await _save_log(callback, state, employee, bot)


@router.callback_query(WorkLogStates.confirming, F.data.in_({"confirm:cancel", "dup:cancel"}))
async def confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Запись отменена.")
    await callback.answer()
