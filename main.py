from __future__ import annotations
import asyncio
import logging
import signal

from signalbot import SignalBot
from telegram.ext import Application, CallbackQueryHandler, ChosenInlineResultHandler, CommandHandler, InlineQueryHandler, MessageHandler, filters

import db
from config import config
from handlers import handle_apikey, handle_chosen_inline_result, handle_inline_loading_callback, handle_inline_query, handle_message, handle_resetapikey
from server import start_server
from signal_handlers import DownloadHandler

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
    app.add_handler(InlineQueryHandler(handle_inline_query))
    app.add_handler(ChosenInlineResultHandler(handle_chosen_inline_result))
    app.add_handler(CallbackQueryHandler(handle_inline_loading_callback, pattern="^inline_loading$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.CAPTION, handle_message))

    signal_bot: SignalBot | None = None
    if config.signal_service and config.signal_phone_number:
        signal_bot = SignalBot(
            {
                "signal_service": config.signal_service,
                "phone_number": config.signal_phone_number,
                # signalbot defaults to WARNING, which hides received messages
                "logging_level": logging.INFO,
            }
        )
        allowed = config.signal_allowed_ids
        contacts = list(allowed) if allowed else True
        # signalbot applies the contacts allowlist to DMs only, so groups=True would
        # otherwise let any member of any group the bot is in use it. The filter
        # re-checks the sender for every message, group or not.
        sender_allowed = (lambda m: m.source_uuid in allowed or m.source_number in allowed) if allowed else None
        signal_bot.register(DownloadHandler(), contacts=contacts, groups=True, f=sender_allowed)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
        loop.add_signal_handler(sig, stop.set)

    async with app:
        await app.start()
        assert app.updater is not None
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot started")

        if signal_bot is not None:
            signal_bot.start(run_forever=False)
            logger.info("Signal bot started")

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
