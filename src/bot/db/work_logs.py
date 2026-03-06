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


async def get_photos_batch(log_ids: list[int]) -> dict[int, list[dict]]:
    """Fetch photos for multiple log IDs in one query."""
    if not log_ids:
        return {}
    db = await get_db()
    placeholders = ",".join("?" for _ in log_ids)
    rows = await db.execute_fetchall(
        f"SELECT * FROM work_photos WHERE work_log_id IN ({placeholders})", log_ids
    )
    result: dict[int, list[dict]] = {}
    for r in rows:
        d = dict(r)
        result.setdefault(d["work_log_id"], []).append(d)
    return result


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


async def get_log(log_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT w.*, e.full_name, e.position
           FROM work_logs w
           JOIN employees e ON e.telegram_id = w.employee_id
           WHERE w.id = ?""",
        (log_id,),
    )
    return dict(rows[0]) if rows else None


async def update_log(log_id: int, category: str, description: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE work_logs SET category = ?, description = ? WHERE id = ? AND is_active = 1",
        (category, description, log_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_log(log_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE work_logs SET is_active = 0 WHERE id = ? AND is_active = 1", (log_id,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def restore_log(log_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE work_logs SET is_active = 1 WHERE id = ? AND is_active = 0", (log_id,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def find_duplicate(
    board_serial: str, employee_id: int, category: str, description: str, minutes: int = 10
) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT * FROM work_logs
           WHERE board_serial = ? AND employee_id = ? AND category = ?
             AND description = ? AND is_active = 1
             AND created_at >= datetime('now', ? || ' minutes')
           LIMIT 1""",
        (board_serial, employee_id, category, description, f"-{minutes}"),
    )
    return dict(rows[0]) if rows else None


async def get_stats(
    date_from: str | None = None, date_to: str | None = None
) -> dict:
    db = await get_db()
    where = "WHERE w.is_active = 1"
    params: list = []
    if date_from:
        where += " AND DATE(w.created_at) >= ?"
        params.append(date_from)
    if date_to:
        where += " AND DATE(w.created_at) <= ?"
        params.append(date_to)

    total = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM work_logs w {where}", params
    )

    by_board = await db.execute_fetchall(
        f"""SELECT w.board_serial, COUNT(*) as cnt
            FROM work_logs w {where}
            GROUP BY w.board_serial ORDER BY cnt DESC""",
        params,
    )

    by_employee = await db.execute_fetchall(
        f"""SELECT e.full_name, COUNT(*) as cnt
            FROM work_logs w
            JOIN employees e ON e.telegram_id = w.employee_id
            {where}
            GROUP BY w.employee_id ORDER BY cnt DESC""",
        params,
    )

    by_category = await db.execute_fetchall(
        f"""SELECT w.category, COUNT(*) as cnt
            FROM work_logs w {where}
            GROUP BY w.category ORDER BY cnt DESC""",
        params,
    )

    return {
        "total": total[0]["cnt"],
        "by_board": [dict(r) for r in by_board],
        "by_employee": [dict(r) for r in by_employee],
        "by_category": [dict(r) for r in by_category],
    }


async def get_logs_for_export(
    date_from: str | None = None,
    date_to: str | None = None,
    employee_id: int | None = None,
) -> tuple[dict[str, list[dict]], int]:
    """Return logs grouped by board serial for export, with optional filters."""
    db = await get_db()
    where = "WHERE w.is_active = 1"
    params: list = []
    if date_from:
        where += " AND DATE(w.created_at) >= ?"
        params.append(date_from)
    if date_to:
        where += " AND DATE(w.created_at) <= ?"
        params.append(date_to)
    if employee_id is not None:
        where += " AND w.employee_id = ?"
        params.append(employee_id)

    rows = await db.execute_fetchall(
        f"""SELECT w.*, e.full_name, e.position
            FROM work_logs w
            JOIN employees e ON e.telegram_id = w.employee_id
            {where}
            ORDER BY w.board_serial, w.created_at DESC""",
        params,
    )

    grouped: dict[str, list[dict]] = {}
    for r in rows:
        d = dict(r)
        grouped.setdefault(d["board_serial"], []).append(d)
    total = sum(len(v) for v in grouped.values())
    return grouped, total
