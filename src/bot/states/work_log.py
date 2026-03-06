from aiogram.fsm.state import State, StatesGroup


class WorkLogStates(StatesGroup):
    choosing_board = State()
    choosing_category = State()
    entering_description = State()
    waiting_photo = State()
    confirming = State()
