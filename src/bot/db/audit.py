from bot.db.connection import get_db


async def log_action(
    actor_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: str | None = None,
) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO audit_log (actor_id, action, target_type, target_id, details) VALUES (?, ?, ?, ?, ?)",
        (actor_id, action, target_type, target_id, details),
    )
    await db.commit()


async def get_audit_log(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    db = await get_db()
    count_row = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM audit_log")
    total = count_row[0]["cnt"]

    rows = await db.execute_fetchall(
        """SELECT a.*, e.full_name
           FROM audit_log a
           JOIN employees e ON e.telegram_id = a.actor_id
           ORDER BY a.created_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    return [dict(r) for r in rows], total
