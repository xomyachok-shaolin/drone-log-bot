import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    telegram_id   INTEGER PRIMARY KEY,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'worker',
    position      TEXT,
    last_board    TEXT,
    registered_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS work_templates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    description   TEXT NOT NULL,
    created_by    INTEGER REFERENCES employees(telegram_id)
);

CREATE TABLE IF NOT EXISTS boards (
    serial        TEXT PRIMARY KEY,
    model         TEXT,
    description   TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now')),
    created_by    INTEGER REFERENCES employees(telegram_id)
);

CREATE TABLE IF NOT EXISTS work_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    board_serial  TEXT NOT NULL REFERENCES boards(serial),
    employee_id   INTEGER NOT NULL REFERENCES employees(telegram_id),
    category      TEXT NOT NULL,
    description   TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS work_photos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_log_id   INTEGER NOT NULL REFERENCES work_logs(id) ON DELETE CASCADE,
    file_id       TEXT NOT NULL,
    caption       TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id      INTEGER NOT NULL REFERENCES employees(telegram_id),
    action        TEXT NOT NULL,
    target_type   TEXT,
    target_id     TEXT,
    details       TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS work_documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_log_id   INTEGER NOT NULL REFERENCES work_logs(id) ON DELETE CASCADE,
    file_id       TEXT NOT NULL,
    file_name     TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(created_at);

CREATE INDEX IF NOT EXISTS idx_logs_board ON work_logs(board_serial);
CREATE INDEX IF NOT EXISTS idx_logs_employee ON work_logs(employee_id);
CREATE INDEX IF NOT EXISTS idx_logs_date ON work_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_category ON work_logs(category);
"""

# Add is_active column to existing tables (safe to run repeatedly)
MIGRATIONS = [
    "ALTER TABLE boards ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE work_logs ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE employees ADD COLUMN last_board TEXT",
]


async def run_migrations(db: aiosqlite.Connection) -> None:
    await db.executescript(SCHEMA)
    for sql in MIGRATIONS:
        try:
            await db.execute(sql)
        except Exception:
            pass  # column already exists
    await db.commit()
