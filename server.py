from __future__ import annotations
import logging

from aiohttp import web
from telegram import Bot

import db
from handlers import download_and_deliver

logger = logging.getLogger(__name__)

PORT = 5868


async def _download(request: web.Request) -> web.Response:
    auth = request.headers.get("Authorization", "")
    if not auth:
        return web.Response(status=401, text="Missing Authorization header")

    user_id = db.get_user_id_by_api_key(auth)
    if user_id is None:
        return web.Response(status=403, text="Invalid API key")

    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="Request body must be JSON")

    url = body.get("url", "").strip()
    if not url:
        return web.Response(status=400, text="Missing 'url' field")

    bot: Bot = request.app["bot"]
    logger.info("API download request from user_id=%d url=%s", user_id, url)

    try:
        await download_and_deliver(bot, user_id, url)
    except ValueError as exc:
        return web.Response(status=422, text=str(exc))
    except Exception as exc:
        logger.error("API download failed for %s: %s", url, exc, exc_info=True)
        return web.Response(status=500, text=f"Download failed: {exc}")

    return web.Response(status=200, text="OK")


def create_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/api/download", _download)
    return app


async def start_server(bot: Bot) -> web.AppRunner:
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("HTTP server listening on port %d", PORT)
    return runner
