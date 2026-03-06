from bot.db.connection import get_db


async def get_employee(telegram_id: int) -> dict | None:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM employees WHERE telegram_id = ?", (telegram_id,)
    )
    return dict(row[0]) if row else None


async def create_employee(telegram_id: int, full_name: str, position: str, role: str = "worker") -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO employees (telegram_id, full_name, position, role) VALUES (?, ?, ?, ?)",
        (telegram_id, full_name, position, role),
    )
    await db.commit()


async def update_employee(telegram_id: int, full_name: str, position: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE employees SET full_name = ?, position = ? WHERE telegram_id = ?",
        (full_name, position, telegram_id),
    )
    await db.commit()


async def set_role(telegram_id: int, role: str) -> bool:
    if role not in ("worker", "lead", "admin"):
        return False
    db = await get_db()
    cursor = await db.execute(
        "UPDATE employees SET role = ? WHERE telegram_id = ?",
        (role, telegram_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def list_employees() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM employees ORDER BY full_name")
    return [dict(r) for r in rows]
