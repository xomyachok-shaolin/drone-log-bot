from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import settings
from bot.db.employees import create_employee, get_employee, update_employee
from bot.states.registration import RegistrationStates

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, employee: dict | None) -> None:
    if employee is not None:
        await message.answer(
            f"Вы уже зарегистрированы:\n"
            f"ФИО: {employee['full_name']}\n"
            f"Должность: {employee['position']}\n"
            f"Роль: {employee['role']}\n\n"
            f"Чтобы обновить данные, введите новое ФИО или отправьте /cancel"
        )
        await state.set_state(RegistrationStates.waiting_full_name)
        await state.update_data(is_update=True)
        return

    await message.answer(
        "Добро пожаловать в AlgaDrone Log!\n"
        "Для начала работы нужно зарегистрироваться.\n\n"
        "Введите ваше ФИО:"
    )
    await state.set_state(RegistrationStates.waiting_full_name)
    await state.update_data(is_update=False)


@router.message(RegistrationStates.waiting_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext) -> None:
    full_name = message.text.strip()
    if len(full_name) < 3:
        await message.answer("ФИО слишком короткое. Попробуйте ещё раз:")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_position)
    await message.answer("Введите вашу должность:")


@router.message(RegistrationStates.waiting_position, F.text)
async def process_position(message: Message, state: FSMContext) -> None:
    position = message.text.strip()
    if len(position) < 2:
        await message.answer("Должность слишком короткая. Попробуйте ещё раз:")
        return

    data = await state.get_data()
    full_name = data["full_name"]
    is_update = data.get("is_update", False)
    user_id = message.from_user.id

    if is_update:
        await update_employee(user_id, full_name, position)
        await message.answer(
            f"Данные обновлены!\n"
            f"ФИО: {full_name}\n"
            f"Должность: {position}"
        )
    else:
        role = "admin" if user_id in settings.admin_ids else "worker"
        await create_employee(user_id, full_name, position, role)
        await message.answer(
            f"Регистрация завершена!\n"
            f"ФИО: {full_name}\n"
            f"Должность: {position}\n"
            f"Роль: {role}\n\n"
            f"Используйте /help для списка команд."
        )

    await state.clear()
