import pytest
import aiosqlite

from bot.db.connection import init_db, close_db
from bot.db.migrations import run_migrations


@pytest.fixture
async def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = await init_db(db_path)
    await run_migrations(conn)
    yield conn
    await close_db()
