from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.db.templates import create_template, list_templates, get_template, delete_template
from bot.keyboards.inline import CATEGORIES, categories_keyboard, templates_keyboard
from bot.states.work_log import TemplateStates, WorkLogStates

router = Router()


@router.message(Command("template_add"))
async def cmd_template_add(message: Message, state: FSMContext, employee: dict) -> None:
    if employee["role"] not in ("lead", "admin"):
        await message.answer("Создавать шаблоны могут руководители и админы.")
        return
    await state.set_state(TemplateStates.entering_name)
    await message.answer("Введите название шаблона (кратко):")


@router.message(TemplateStates.entering_name, F.text)
async def template_name_entered(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Название от 2 до 50 символов.")
        return
    await state.update_data(tpl_name=name)
    await state.set_state(TemplateStates.choosing_category)
    await message.answer("Выберите категорию:", reply_markup=categories_keyboard())


@router.callback_query(TemplateStates.choosing_category, F.data.startswith("cat:"))
async def template_category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":")[1]
    await state.update_data(tpl_category=category)
    await state.set_state(TemplateStates.entering_description)
    cat_name = CATEGORIES.get(category, category)
    await callback.message.edit_text(f"Категория: {cat_name}\n\nВведите описание для шаблона:")
    await callback.answer()


@router.message(TemplateStates.entering_description, F.text)
async def template_description_entered(message: Message, state: FSMContext, employee: dict) -> None:
    text = message.text.strip()
    if len(text) < 5:
        await message.answer("Описание слишком короткое (минимум 5 символов).")
        return
    data = await state.get_data()
    tpl_id = await create_template(data["tpl_name"], data["tpl_category"], text, employee["telegram_id"])
    await state.clear()
    await message.answer(f"Шаблон \"{data['tpl_name']}\" создан (ID: {tpl_id}).")


@router.message(Command("templates"))
async def cmd_templates(message: Message) -> None:
    templates = await list_templates()
    if not templates:
        await message.answer("Нет шаблонов. Создайте: /template_add")
        return

    lines = ["Шаблоны:\n"]
    for t in templates:
        cat_name = CATEGORIES.get(t["category"], t["category"])
        lines.append(f"  #{t['id']} {t['name']} - {cat_name}")
    await message.answer("\n".join(lines))


@router.message(Command("template_delete"))
async def cmd_template_delete(message: Message, employee: dict) -> None:
    if employee["role"] not in ("lead", "admin"):
        await message.answer("Удалять шаблоны могут руководители и админы.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /template_delete <id>")
        return

    try:
        tpl_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    ok = await delete_template(tpl_id)
    if ok:
        await message.answer(f"Шаблон #{tpl_id} удалён.")
    else:
        await message.answer(f"Шаблон #{tpl_id} не найден.")


@router.message(Command("log_tpl"))
async def cmd_log_from_template(message: Message, state: FSMContext, employee: dict) -> None:
    args = message.text.split()
    if len(args) < 2:
        templates = await list_templates()
        if not templates:
            await message.answer("Нет шаблонов. Создайте: /template_add")
            return
        await message.answer("Выберите шаблон:", reply_markup=templates_keyboard(templates))
        return

    try:
        tpl_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    tpl = await get_template(tpl_id)
    if not tpl:
        await message.answer(f"Шаблон #{tpl_id} не найден.")
        return

    await _apply_template(message, state, tpl)


@router.callback_query(F.data.startswith("tpl_use:"))
async def tpl_use_callback(callback: CallbackQuery, state: FSMContext) -> None:
    tpl_id = int(callback.data.split(":")[1])
    tpl = await get_template(tpl_id)
    if not tpl:
        await callback.message.edit_text("Шаблон не найден.")
        await callback.answer()
        return
    await callback.message.delete()
    await _apply_template(callback.message, state, tpl)
    await callback.answer()


async def _apply_template(message: Message, state: FSMContext, tpl: dict) -> None:
    from bot.db.boards import list_boards
    boards = await list_boards()
    if not boards:
        await message.answer("Нет зарегистрированных бортов.")
        return

    await state.update_data(
        photos=[],
        category=tpl["category"],
        description=tpl["description"],
    )
    await state.set_state(WorkLogStates.choosing_board)

    cat_name = CATEGORIES.get(tpl["category"], tpl["category"])
    from bot.keyboards.inline import boards_keyboard
    await message.answer(
        f"Шаблон: {tpl['name']}\n"
        f"Категория: {cat_name}\n"
        f"Описание: {tpl['description'][:100]}\n\n"
        f"Выберите борт:",
        reply_markup=boards_keyboard(boards),
    )
