from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.db.employees import get_employee
from bot.states.registration import RegistrationStates


class AuthMiddleware(BaseMiddleware):
    """Check that user is registered. Pass employee data into handler."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None:
            return await handler(event, data)

        employee = await get_employee(user.id)

        if employee is None:
            # Allow /start and registration FSM states
            if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                data["employee"] = None
                return await handler(event, data)

            fsm: FSMContext | None = data.get("state")
            if fsm:
                state = await fsm.get_state()
                if state and state.startswith("RegistrationStates:"):
                    data["employee"] = None
                    return await handler(event, data)

            if isinstance(event, Message):
                await event.answer(
                    "Вы не зарегистрированы. Отправьте /start для регистрации."
                )
            return None

        data["employee"] = employee
        return await handler(event, data)
