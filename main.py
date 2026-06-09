from __future__ import annotations
import asyncio
import logging
import signal

from telegram.ext import Application, CommandHandler, MessageHandler, filters

import db
from config import config
from handlers import handle_apikey, handle_message, handle_resetapikey
from server import start_server

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def _run() -> None:
    db.init(config.db_path)
    app = Application.builder().token(config.bot_token).build()
    app.add_handler(CommandHandler("apikey", handle_apikey))
    app.add_handler(CommandHandler("resetapikey", handle_resetapikey))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.CAPTION, handle_message))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
        loop.add_signal_handler(sig, stop.set)

    async with app:
        await app.start()
        assert app.updater is not None
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot started")

        runner = await start_server(app.bot)
        try:
            await stop.wait()
        finally:
            await runner.cleanup()

        await app.updater.stop()
        await app.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
