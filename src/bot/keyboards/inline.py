from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

CATEGORIES = {
    "assembly": "Сборка",
    "component_change": "Замена компонента",
    "firmware": "Обновление ПО",
    "repair": "Ремонт",
    "testing": "Тестирование",
    "inspection": "Осмотр",
    "other": "Другое",
}


def boards_keyboard(
    boards: list[dict],
    page: int = 0,
    per_page: int = 9,
    action: str = "board",
) -> InlineKeyboardMarkup:
    """Board picker keyboard. action sets callback prefix:
    board -> board:XX (log FSM), hist -> pick_hist:XX,
    info -> pick_info:XX, export -> pick_exp:XX
    """
    prefix_map = {
        "board": "board",
        "hist": "pick_hist",
        "info": "pick_info",
        "export": "pick_exp",
    }
    cb_prefix = prefix_map.get(action, action)

    builder = InlineKeyboardBuilder()
    start = page * per_page
    page_boards = boards[start : start + per_page]

    for b in page_boards:
        builder.button(text=b["serial"], callback_data=f"{cb_prefix}:{b['serial']}")

    builder.adjust(3)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="< назад", callback_data=f"{cb_prefix}_pg:{page - 1}")
        )
    if start + per_page < len(boards):
        nav_buttons.append(
            InlineKeyboardButton(text="ещё >", callback_data=f"{cb_prefix}_pg:{page + 1}")
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    return builder.as_markup()


def categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in CATEGORIES.items():
        builder.button(text=label, callback_data=f"cat:{code}")
    builder.adjust(3)
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сохранить", callback_data="confirm:save"),
                InlineKeyboardButton(text="Отменить", callback_data="confirm:cancel"),
            ]
        ]
    )


def photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Готово", callback_data="photo:done"),
                InlineKeyboardButton(text="Пропустить", callback_data="photo:skip"),
            ]
        ]
    )


def pagination_keyboard(prefix: str, page: int, total: int, page_size: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (total + page_size - 1) // page_size)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="< назад", callback_data=f"{prefix}:{page - 1}"))
    buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if (page + 1) * page_size < total:
        buttons.append(InlineKeyboardButton(text="вперёд >", callback_data=f"{prefix}:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
