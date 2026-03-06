from bot.db.connection import get_db


async def get_board(serial: str) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM boards WHERE serial = ? AND is_active = 1", (serial,)
    )
    return dict(rows[0]) if rows else None


async def create_board(serial: str, created_by: int, model: str | None = None) -> None:
    db = await get_db()
    # Reactivate if previously soft-deleted
    existing = await db.execute_fetchall("SELECT * FROM boards WHERE serial = ?", (serial,))
    if existing:
        await db.execute(
            "UPDATE boards SET is_active = 1, model = COALESCE(?, model), created_by = ? WHERE serial = ?",
            (model, created_by, serial),
        )
    else:
        await db.execute(
            "INSERT INTO boards (serial, model, created_by) VALUES (?, ?, ?)",
            (serial, model, created_by),
        )
    await db.commit()


async def delete_board(serial: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE boards SET is_active = 0 WHERE serial = ? AND is_active = 1", (serial,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def restore_board(serial: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE boards SET is_active = 1 WHERE serial = ? AND is_active = 0", (serial,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def list_boards() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM boards WHERE is_active = 1 ORDER BY serial"
    )
    return [dict(r) for r in rows]
