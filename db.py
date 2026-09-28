import aiosqlite

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    text       TEXT NOT NULL,
    answered   INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS leads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    name       TEXT, phone TEXT, car TEXT, problem TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS handoffs (   -- какое сообщение у админа относится к какому клиенту
    admin_chat_id INTEGER NOT NULL,
    admin_msg_id  INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    created_at    TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (admin_chat_id, admin_msg_id)
);
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    human_until TEXT               -- пока не истекло, сообщения клиента идут мастеру, а не AI
);
"""


def _connect():
    return aiosqlite.connect(DB_PATH)


async def _fetch(sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
    async with _connect() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(sql, params) as cur:
            return list(await cur.fetchall())


async def _exec(sql: str, params: tuple = ()) -> int:
    async with _connect() as conn:
        cur = await conn.execute(sql, params)
        await conn.commit()
        return cur.lastrowid


async def init() -> None:
    async with _connect() as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()


# --- база знаний ---

async def kb_all() -> list[aiosqlite.Row]:
    return await _fetch("SELECT * FROM kb ORDER BY id")


async def kb_get(section_id: int) -> aiosqlite.Row | None:
    rows = await _fetch("SELECT * FROM kb WHERE id=?", (section_id,))
    return rows[0] if rows else None


async def kb_add(title: str, content: str) -> int:
    return await _exec("INSERT INTO kb (title, content) VALUES (?, ?)", (title, content))


async def kb_update(section_id: int, content: str) -> None:
    await _exec("UPDATE kb SET content=? WHERE id=?", (content, section_id))


async def kb_delete(section_id: int) -> None:
    await _exec("DELETE FROM kb WHERE id=?", (section_id,))


async def kb_replace(sections: list[tuple[str, str]]) -> None:
    async with _connect() as conn:
        await conn.execute("DELETE FROM kb")
        await conn.executemany("INSERT INTO kb (title, content) VALUES (?, ?)", sections)
        await conn.commit()


# --- статистика ---

async def log_question(user_id: int, text: str, answered: bool) -> None:
    await _exec("INSERT INTO questions (user_id, text, answered) VALUES (?, ?, ?)", (user_id, text, int(answered)))


async def questions_since(days: int) -> list[aiosqlite.Row]:
    return await _fetch("SELECT * FROM questions WHERE created_at >= datetime('now', ?) ORDER BY id DESC",
                        (f"-{days} days",))


# --- заявки ---

async def add_lead(user_id: int, name: str, phone: str, car: str, problem: str) -> int:
    return await _exec("INSERT INTO leads (user_id, name, phone, car, problem) VALUES (?, ?, ?, ?, ?)",
                       (user_id, name, phone, car, problem))


async def leads_last(limit: int = 10) -> list[aiosqlite.Row]:
    return await _fetch("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,))


async def leads_count_since(days: int) -> int:
    rows = await _fetch("SELECT COUNT(*) AS n FROM leads WHERE created_at >= datetime('now', ?)", (f"-{days} days",))
    return rows[0]["n"]


# --- передача мастеру ---

async def add_handoff(admin_chat_id: int, admin_msg_id: int, user_id: int) -> None:
    await _exec("INSERT OR REPLACE INTO handoffs (admin_chat_id, admin_msg_id, user_id) VALUES (?, ?, ?)",
                (admin_chat_id, admin_msg_id, user_id))


async def handoff_user(admin_chat_id: int, admin_msg_id: int) -> int | None:
    rows = await _fetch("SELECT user_id FROM handoffs WHERE admin_chat_id=? AND admin_msg_id=?",
                        (admin_chat_id, admin_msg_id))
    return rows[0]["user_id"] if rows else None


async def handoffs_count_since(days: int) -> int:
    rows = await _fetch("SELECT COUNT(DISTINCT user_id) AS n FROM handoffs WHERE created_at >= datetime('now', ?)",
                        (f"-{days} days",))
    return rows[0]["n"]


async def set_human_until(user_id: int, until_iso: str | None) -> None:
    await _exec("INSERT INTO users (user_id, human_until) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET human_until=excluded.human_until", (user_id, until_iso))


async def get_human_until(user_id: int) -> str | None:
    rows = await _fetch("SELECT human_until FROM users WHERE user_id=?", (user_id,))
    return rows[0]["human_until"] if rows else None
