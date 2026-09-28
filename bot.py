import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import config
import db
from handlers import admin, client
from utils import parse_kb_markdown


async def seed_kb() -> None:
    if await db.kb_all():
        return
    seed = Path(config.KB_SEED_FILE)
    if seed.exists():
        sections = parse_kb_markdown(seed.read_text(encoding="utf-8"))
        await db.kb_replace(sections)
        logging.info("База знаний заполнена из %s: %d разделов", seed, len(sections))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан — впишите его в файл .env")

    await db.init()
    await seed_kb()
    session = AiohttpSession(proxy=config.PROXY) if config.PROXY else None
    bot = Bot(config.BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_routers(admin.router, client.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Начать заново"),
        BotCommand(command="myid", description="Узнать свой Telegram ID"),
    ])
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
