from bot.db.connection import get_db


async def create_template(name: str, category: str, description: str, created_by: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO work_templates (name, category, description, created_by) VALUES (?, ?, ?, ?)",
        (name, category, description, created_by),
    )
    await db.commit()
    return cursor.lastrowid


async def list_templates() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM work_templates ORDER BY name")
    return [dict(r) for r in rows]


async def get_template(template_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM work_templates WHERE id = ?", (template_id,)
    )
    return dict(rows[0]) if rows else None


async def delete_template(template_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM work_templates WHERE id = ?", (template_id,))
    await db.commit()
    return cursor.rowcount > 0
