"""Прогоняет демо-сценарий через НАСТОЯЩИЕ обработчики бота (aiogram + GigaChat),
подменяя только транспорт Telegram. Все ответы бота записываются в public/script.json для ролика.
Запуск из корня проекта: .venv\\Scripts\\python video\\gen_script.py"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import config  # noqa: E402

CLIENT_ID, ADMIN_ID, BOT_ID = 2000, 1000, 9999
config.DB_PATH = "video_demo.db"
config.ADMIN_IDS.clear()
config.ADMIN_IDS.add(ADMIN_ID)

import db  # noqa: E402

db.DB_PATH = config.DB_PATH
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import (InlineKeyboardMarkup, Message, MessageId, ReplyKeyboardMarkup,  # noqa: E402
                           ReplyKeyboardRemove, Update)

import bot as bot_main  # noqa: E402
from handlers import admin, client  # noqa: E402

EVENTS: list[dict] = []
MESSAGES: dict[tuple[int, int], dict] = {}   # (chat, id) -> сырое сообщение (для кнопок и reply)
USERS = {CLIENT_ID: {"id": CLIENT_ID, "is_bot": False, "first_name": "Иван"},
         ADMIN_ID: {"id": ADMIN_ID, "is_bot": False, "first_name": "Мастер"}}
BOT_USER = {"id": BOT_ID, "is_bot": True, "first_name": "Поршень"}


def dump_markup(m):
    if isinstance(m, InlineKeyboardMarkup):
        return {"inline": [[b.text for b in row] for row in m.inline_keyboard]}
    if isinstance(m, ReplyKeyboardMarkup):
        return {"reply": [[b.text for b in row] for row in m.keyboard]}
    if isinstance(m, ReplyKeyboardRemove):
        return {"remove": True}
    return None


class MockSession(BaseSession):
    """Вместо HTTP к Telegram — запись того, что бот отправил."""

    def __init__(self):
        super().__init__()
        self._id = 500

    def new_id(self) -> int:
        self._id += 1
        return self._id

    def msg(self, bot, chat_id, mid, text, from_user=BOT_USER, markup=None, reply_to=None):
        data = {"message_id": mid, "date": int(time.time()), "chat": {"id": chat_id, "type": "private"},
                "from": from_user, "text": text}
        if markup is not None:
            data["reply_markup"] = markup.model_dump(exclude_none=True)
        if reply_to:
            data["reply_to_message"] = reply_to
        return Message.model_validate(data, context={"bot": bot}), data

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name == "SendMessage":
            mid = self.new_id()
            inline = method.reply_markup if isinstance(method.reply_markup, InlineKeyboardMarkup) else None
            m, data = self.msg(bot, method.chat_id, mid, method.text, markup=inline)
            MESSAGES[(method.chat_id, mid)] = data
            EVENTS.append({"op": "bot", "chat": method.chat_id, "id": mid, "text": method.text,
                           "markup": dump_markup(method.reply_markup)})
            return m
        if name == "EditMessageText":
            data = MESSAGES[(method.chat_id, method.message_id)]
            data["text"] = method.text
            if isinstance(method.reply_markup, InlineKeyboardMarkup):
                data["reply_markup"] = method.reply_markup.model_dump(exclude_none=True)
            else:
                data.pop("reply_markup", None)
            EVENTS.append({"op": "edit", "chat": method.chat_id, "id": method.message_id, "text": method.text,
                           "markup": dump_markup(method.reply_markup)})
            m, _ = self.msg(bot, method.chat_id, method.message_id, method.text)
            return m
        if name == "CopyMessage":
            src = MESSAGES[(method.from_chat_id, method.message_id)]
            mid = self.new_id()
            EVENTS.append({"op": "bot", "chat": method.chat_id, "id": mid, "text": src["text"], "markup": None})
            return MessageId(message_id=mid)
        if name == "AnswerCallbackQuery":
            if method.text:
                EVENTS.append({"op": "toast", "chat": None, "text": method.text})
            return True
        if name in ("SendChatAction", "SetMyCommands", "DeleteWebhook"):
            return True
        raise RuntimeError(f"Не замокан метод {name}")

    async def close(self):
        pass

    async def stream_content(self, *a, **kw):
        raise RuntimeError("не нужно")


class Demo:
    def __init__(self):
        self.session = MockSession()
        self.bot = Bot("1:demo", session=self.session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.dp.include_routers(admin.router, client.router)
        self.upd = 0

    async def feed(self, payload: dict):
        self.upd += 1
        update = Update.model_validate({"update_id": self.upd, **payload}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, update)

    async def say(self, uid: int, text: str, reply_to_id: int | None = None):
        mid = self.session.new_id()
        reply_to = MESSAGES.get((uid, reply_to_id)) if reply_to_id else None
        _, data = self.session.msg(self.bot, uid, mid, text, from_user=USERS[uid], reply_to=reply_to)
        MESSAGES[(uid, mid)] = data
        EVENTS.append({"op": "user", "chat": uid, "id": mid, "text": text, "reply_to": reply_to_id})
        await self.feed({"message": data})

    async def click(self, uid: int, prefix: str) -> bool:
        """Жмёт последнюю по времени inline-кнопку с таким началом текста."""
        for (chat, mid), data in sorted(MESSAGES.items(), key=lambda kv: -kv[0][1]):
            if chat != uid or "reply_markup" not in data:
                continue
            for row in data["reply_markup"].get("inline_keyboard", []):
                for b in row:
                    if b["text"].startswith(prefix):
                        EVENTS.append({"op": "click", "chat": uid, "id": mid, "button": b["text"]})
                        await self.feed({"callback_query": {
                            "id": str(self.upd), "from": USERS[uid], "chat_instance": "demo",
                            "message": data, "data": b["callback_data"]}})
                        return True
        return False

    def last_admin_notice(self, starts: str) -> int:
        return next(e["id"] for e in reversed(EVENTS)
                    if e.get("chat") == ADMIN_ID and e["op"] == "bot" and e["text"].startswith(starts))


async def main():
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    await db.init()
    await bot_main.seed_kb()
    d = Demo()
    try:
        await d.say(CLIENT_ID, "/start")
        await d.say(CLIENT_ID, "Сколько стоит поменять передние колодки на Skoda Octavia?")
        await d.say(CLIENT_ID, "А диски вместе с ними?")
        await d.say(CLIENT_ID, "А турбину на ней меняете? Сколько будет стоить?")
        if not await d.click(CLIENT_ID, "📝"):
            await d.say(CLIENT_ID, "📝 Записаться на ремонт")
        await d.say(CLIENT_ID, "Иван")
        await d.say(CLIENT_ID, "+7 900 123-45-67")
        await d.say(CLIENT_ID, "Skoda Octavia 2017, 1.8 TSI")
        await d.say(CLIENT_ID, "➡️ Пропустить")
        await d.say(CLIENT_ID, "👨‍🔧 Позвать мастера")
        notice = d.last_admin_notice("🆘")
        await d.say(ADMIN_ID, "Здравствуйте, Иван! Турбину на 1.8 TSI меняем. Точную цену скажу после "
                              "диагностики — при ремонте у нас она бесплатная. Завтра в 10:00 удобно?",
                    reply_to_id=notice)
        await d.say(CLIENT_ID, "Да, отлично, буду в 10!")
        await d.say(ADMIN_ID, "/admin")
        await d.click(ADMIN_ID, "📊")
        await d.click(ADMIN_ID, "«")
        await d.click(ADMIN_ID, "❓")
    finally:
        if os.path.exists(config.DB_PATH):
            os.remove(config.DB_PATH)

    out = Path(__file__).parent / "src" / "data" / "script.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"client": CLIENT_ID, "admin": ADMIN_ID, "events": EVENTS},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"событий: {len(EVENTS)} → {out}")


if __name__ == "__main__":
    asyncio.run(main())
