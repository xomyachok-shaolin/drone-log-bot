from aiogram.fsm.state import State, StatesGroup


class WorkLogStates(StatesGroup):
    choosing_board = State()
    choosing_category = State()
    entering_description = State()
    waiting_photo = State()
    confirming = State()


class EditLogStates(StatesGroup):
    choosing_field = State()
    editing_category = State()
    editing_description = State()


class TemplateStates(StatesGroup):
    entering_name = State()
    choosing_category = State()
    entering_description = State()
