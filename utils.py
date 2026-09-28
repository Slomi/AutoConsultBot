import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import Message

import config

TZ = ZoneInfo(config.TIMEZONE)


def now() -> datetime:
    return datetime.now(TZ)


def fmt_db_time(value: str) -> str:
    """SQLite хранит datetime('now') в UTC — показываем в часовом поясе бизнеса."""
    utc = datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("UTC"))
    return f"{utc.astimezone(TZ):%d.%m %H:%M}"


def parse_kb_markdown(text: str) -> list[tuple[str, str]]:
    """«## Заголовок» + текст до следующего заголовка → разделы базы знаний."""
    sections, title, lines = [], None, []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.+)", line)
        if m:
            if title and "\n".join(lines).strip():
                sections.append((title, "\n".join(lines).strip()))
            title, lines = m.group(1).strip(), []
        else:
            lines.append(line)
    if title and "\n".join(lines).strip():
        sections.append((title, "\n".join(lines).strip()))
    return sections


def kb_to_markdown(sections) -> str:
    return "\n\n".join(f"## {s['title']}\n{s['content']}" for s in sections) + "\n"


async def notify_admins(bot: Bot, text: str, **kwargs) -> list[Message]:
    sent = []
    for admin_id in config.ADMIN_IDS:
        try:
            sent.append(await bot.send_message(admin_id, text, **kwargs))
        except Exception:
            logging.exception("Не удалось отправить сообщение админу %s", admin_id)
    return sent
