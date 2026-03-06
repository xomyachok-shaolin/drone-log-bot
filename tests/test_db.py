import pytest

from bot.db.employees import create_employee, get_employee, set_role, list_employees
from bot.db.boards import create_board, get_board, list_boards
from bot.db.work_logs import create_work_log, get_logs_by_board, get_logs_by_employee, search_logs


@pytest.mark.asyncio
async def test_employee_crud(db):
    await create_employee(111, "Иванов И.И.", "инженер")
    emp = await get_employee(111)
    assert emp is not None
    assert emp["full_name"] == "Иванов И.И."
    assert emp["role"] == "worker"


@pytest.mark.asyncio
async def test_set_role(db):
    await create_employee(222, "Петров П.П.", "техник")
    ok = await set_role(222, "lead")
    assert ok is True
    emp = await get_employee(222)
    assert emp["role"] == "lead"


@pytest.mark.asyncio
async def test_board_crud(db):
    await create_employee(111, "Иванов И.И.", "инженер")
    await create_board("NSU-0042", 111, "Квадрокоптер")
    board = await get_board("NSU-0042")
    assert board is not None
    assert board["model"] == "Квадрокоптер"


@pytest.mark.asyncio
async def test_work_log(db):
    await create_employee(111, "Иванов И.И.", "инженер")
    await create_board("NSU-0042", 111)

    log_id = await create_work_log("NSU-0042", 111, "repair", "Замена ESC #3")
    assert log_id is not None

    logs, total = await get_logs_by_board("NSU-0042")
    assert total == 1
    assert logs[0]["description"] == "Замена ESC #3"


@pytest.mark.asyncio
async def test_work_log_filter_by_employee(db):
    await create_employee(111, "Иванов И.И.", "инженер")
    await create_employee(222, "Петров П.П.", "техник")
    await create_board("NSU-0042", 111)

    await create_work_log("NSU-0042", 111, "repair", "Работа 1")
    await create_work_log("NSU-0042", 222, "testing", "Работа 2")

    logs, total = await get_logs_by_board("NSU-0042", employee_id=111)
    assert total == 1
    assert logs[0]["description"] == "Работа 1"

    logs, total = await get_logs_by_board("NSU-0042")
    assert total == 2


@pytest.mark.asyncio
async def test_search(db):
    await create_employee(111, "Иванов И.И.", "инженер")
    await create_board("NSU-0042", 111)

    await create_work_log("NSU-0042", 111, "repair", "Замена ESC на T-Motor F55A")
    await create_work_log("NSU-0042", 111, "testing", "Калибровка компаса")

    logs, total = await search_logs("ESC")
    assert total == 1
    assert "ESC" in logs[0]["description"]
