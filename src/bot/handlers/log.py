import structlog

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.db.boards import list_boards
from bot.db.work_logs import create_work_log, add_photo

log = structlog.get_logger()
from bot.keyboards.inline import (
    boards_keyboard,
    categories_keyboard,
    confirm_keyboard,
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

    await state.update_data(photos=[])
    await state.set_state(WorkLogStates.choosing_board)
    await message.answer("Выберите борт:", reply_markup=boards_keyboard(boards))


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
        f"Фото добавлено ({len(photos)} шт.){hint}. Ещё фото или \"Готово\"?",
        reply_markup=photo_keyboard(),
    )


@router.callback_query(WorkLogStates.waiting_photo, F.data.in_({"photo:done", "photo:skip"}))
async def photo_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WorkLogStates.confirming)
    data = await state.get_data()

    cat_name = CATEGORIES.get(data["category"], data["category"])
    photos = data.get("photos", [])
    desc_preview = data["description"][:200]
    if len(data["description"]) > 200:
        desc_preview += "..."

    text = (
        f"Проверьте запись:\n\n"
        f"Борт: {data['board_serial']}\n"
        f"Категория: {cat_name}\n"
        f"Описание: {desc_preview}\n"
        f"Фото: {len(photos)} шт."
    )
    await callback.message.edit_text(text, reply_markup=confirm_keyboard())
    await callback.answer()


@router.callback_query(WorkLogStates.confirming, F.data == "confirm:save")
async def confirm_save(callback: CallbackQuery, state: FSMContext, employee: dict) -> None:
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


@router.callback_query(WorkLogStates.confirming, F.data == "confirm:cancel")
async def confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Запись отменена.")
    await callback.answer()
