from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_full_name = State()
    waiting_position = State()
