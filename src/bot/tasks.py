import asyncio
import shutil
from datetime import datetime, timedelta

import structlog

from aiogram import Bot

from bot.config import settings
from bot.db.connection import get_db
from bot.db.employees import list_employees
from bot.db.work_logs import get_stats
from bot.keyboards.inline import CATEGORIES

log = structlog.get_logger()


async def _check_inactive_boards(bot: Bot) -> None:
    """Warn admins about boards with no work logs for REMINDER_DAYS."""
    db = await get_db()
    cutoff = (datetime.now() - timedelta(days=settings.reminder_days)).strftime("%Y-%m-%d %H:%M:%S")

    rows = await db.execute_fetchall(
        """SELECT b.serial, MAX(w.created_at) as last_log
           FROM boards b
           LEFT JOIN work_logs w ON w.board_serial = b.serial AND w.is_active = 1
           WHERE b.is_active = 1
           GROUP BY b.serial
           HAVING last_log IS NULL OR last_log < ?""",
        (cutoff,),
    )

    if not rows:
        return

    lines = [f"Борта без обслуживания > {settings.reminder_days} дней:\n"]
    for r in rows:
        last = r["last_log"] or "нет записей"
        lines.append(f"  {r['serial']} - последняя запись: {last}")

    text = "\n".join(lines)

    # Send to all admins
    employees = await list_employees()
    for emp in employees:
        if emp["role"] == "admin":
            try:
                await bot.send_message(emp["telegram_id"], text)
            except Exception:
                pass

    log.info("reminders_sent", boards=len(rows))


async def _backup_db() -> None:
    """Copy SQLite DB to a timestamped backup file."""
    src = settings.db_path
    if not src.exists():
        return

    backup_dir = src.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = backup_dir / f"drone_log_{stamp}.db"
    shutil.copy2(str(src), str(dst))

    # Keep only last 7 backups
    backups = sorted(backup_dir.glob("drone_log_*.db"), reverse=True)
    for old in backups[7:]:
        old.unlink()

    log.info("db_backup_created", path=str(dst))


async def _send_weekly_digest(bot: Bot) -> None:
    """Send weekly stats to leads and admins on Monday."""
    if datetime.now().weekday() != 0:  # Monday
        return

    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    stats = await get_stats(date_from=week_ago, date_to=today)

    if stats["total"] == 0:
        return

    text = f"Дайджест за неделю ({week_ago} - {today})\n\nВсего записей: {stats['total']}\n"

    if stats["by_board"]:
        text += "\nПо бортам:\n"
        for row in stats["by_board"][:10]:
            text += f"  {row['board_serial']}: {row['cnt']}\n"

    if stats["by_employee"]:
        text += "\nПо сотрудникам:\n"
        for row in stats["by_employee"][:10]:
            text += f"  {row['full_name']}: {row['cnt']}\n"

    if stats["by_category"]:
        text += "\nПо категориям:\n"
        for row in stats["by_category"]:
            cat_name = CATEGORIES.get(row["category"], row["category"])
            text += f"  {cat_name}: {row['cnt']}\n"

    employees = await list_employees()
    for emp in employees:
        if emp["role"] in ("lead", "admin"):
            try:
                await bot.send_message(emp["telegram_id"], text)
            except Exception:
                pass

    log.info("weekly_digest_sent")


async def run_scheduled_tasks(bot: Bot) -> None:
    """Background loop running daily tasks at ~08:00."""
    while True:
        try:
            now = datetime.now()
            # Run at 08:00
            next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            log.info("scheduler_waiting", next_run=str(next_run), wait_s=int(wait_seconds))
            await asyncio.sleep(wait_seconds)

            if settings.backup_enabled:
                await _backup_db()

            await _check_inactive_boards(bot)

            if settings.digest_enabled:
                await _send_weekly_digest(bot)

        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("scheduler_error")
            await asyncio.sleep(3600)
