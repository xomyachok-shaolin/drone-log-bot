from bot.db.connection import get_db


async def create_work_log(
    board_serial: str,
    employee_id: int,
    category: str,
    description: str,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO work_logs (board_serial, employee_id, category, description) VALUES (?, ?, ?, ?)",
        (board_serial, employee_id, category, description),
    )
    await db.commit()
    return cursor.lastrowid


async def add_photo(work_log_id: int, file_id: str, caption: str | None = None) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO work_photos (work_log_id, file_id, caption) VALUES (?, ?, ?)",
        (work_log_id, file_id, caption),
    )
    await db.commit()


async def get_photos(work_log_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM work_photos WHERE work_log_id = ?", (work_log_id,)
    )
    return [dict(r) for r in rows]


async def get_logs_by_board(
    board_serial: str,
    employee_id: int | None = None,
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Return (logs, total_count). If employee_id is set, filter by employee."""
    db = await get_db()
    where = "WHERE w.board_serial = ? AND w.is_active = 1"
    params: list = [board_serial]
    if employee_id is not None:
        where += " AND w.employee_id = ?"
        params.append(employee_id)

    count_row = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM work_logs w {where}", params
    )
    total = count_row[0]["cnt"]

    rows = await db.execute_fetchall(
        f"""SELECT w.*, e.full_name, e.position
            FROM work_logs w
            JOIN employees e ON e.telegram_id = w.employee_id
            {where}
            ORDER BY w.created_at DESC
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    )
    return [dict(r) for r in rows], total


async def get_logs_by_employee(
    employee_id: int, limit: int = 5, offset: int = 0
) -> tuple[list[dict], int]:
    db = await get_db()
    count_row = await db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM work_logs WHERE employee_id = ? AND is_active = 1",
        (employee_id,),
    )
    total = count_row[0]["cnt"]

    rows = await db.execute_fetchall(
        """SELECT w.*, b.model
           FROM work_logs w
           JOIN boards b ON b.serial = w.board_serial
           WHERE w.employee_id = ? AND w.is_active = 1
           ORDER BY w.created_at DESC
           LIMIT ? OFFSET ?""",
        (employee_id, limit, offset),
    )
    return [dict(r) for r in rows], total


async def get_logs_by_date(
    date: str,
    employee_id: int | None = None,
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[dict], int]:
    db = await get_db()
    where = "WHERE DATE(w.created_at) = ? AND w.is_active = 1"
    params: list = [date]
    if employee_id is not None:
        where += " AND w.employee_id = ?"
        params.append(employee_id)

    count_row = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM work_logs w {where}", params
    )
    total = count_row[0]["cnt"]

    rows = await db.execute_fetchall(
        f"""SELECT w.*, e.full_name, e.position
            FROM work_logs w
            JOIN employees e ON e.telegram_id = w.employee_id
            {where}
            ORDER BY w.created_at DESC
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    )
    return [dict(r) for r in rows], total


async def search_logs(
    query: str,
    employee_id: int | None = None,
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[dict], int]:
    db = await get_db()
    where = "WHERE w.description LIKE ? AND w.is_active = 1"
    params: list = [f"%{query}%"]
    if employee_id is not None:
        where += " AND w.employee_id = ?"
        params.append(employee_id)

    count_row = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM work_logs w {where}", params
    )
    total = count_row[0]["cnt"]

    rows = await db.execute_fetchall(
        f"""SELECT w.*, e.full_name, e.position
            FROM work_logs w
            JOIN employees e ON e.telegram_id = w.employee_id
            {where}
            ORDER BY w.created_at DESC
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    )
    return [dict(r) for r in rows], total


async def delete_log(log_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE work_logs SET is_active = 0 WHERE id = ? AND is_active = 1", (log_id,)
    )
    await db.commit()
    return cursor.rowcount > 0
