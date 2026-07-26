from __future__ import annotations
import asyncio
import base64
import logging
import shutil
from pathlib import Path

from signalbot import Command, Context

from config import config
from downloader import download_blocking
from extractors import Extractor, find_extractor
from urlutil import URL_RE, clean_url

logger = logging.getLogger(__name__)


def _b64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


class DownloadCommand(Command):
    """Watches every DM/group message for supported URLs and replies with the media."""

    async def handle(self, c: Context) -> None:
        text = c.message.text or ""
        urls = URL_RE.findall(text)
        if not urls:
            return

        unsupported: list[str] = []
        for raw_url in urls:
            url = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
            extractor = find_extractor(url)
            if extractor is None:
                unsupported.append(url)
                continue

            await self._download_and_reply(c, extractor, url)

        if unsupported and c.message.is_private():
            lines = "\n".join(f"• {u}" for u in unsupported)
            await c.reply(f"⚠️ Unsupported URL(s):\n{lines}")

    async def _download_and_reply(self, c: Context, extractor: Extractor, url: str) -> None:
        session_dir = None
        try:
            await c.start_typing()
            session_dir, files = await asyncio.to_thread(
                download_blocking,
                url,
                config.download_dir,
                extractor.cookies_file,
                extractor.url_transform,
                extractor.extract,
            )

            if not files:
                await c.reply("❌ No media found.")
                return

            sendable = [f for f in files if f.stat().st_size <= config.max_file_size]
            if not sendable:
                limit_mb = config.max_file_size // 1024 // 1024
                await c.reply(f"❌ All files exceed {limit_mb}MB limit.")
                return

            caption = extractor.reply_url(clean_url(url)) if extractor.reply_url else clean_url(url)
            attachments = [_b64_file(f) for f in sendable]
            await c.send(caption, base64_attachments=attachments)

            skipped = len(files) - len(sendable)
            if skipped:
                await c.reply(f"⚠️ {skipped} file(s) skipped (too large).")
        except Exception as exc:
            logger.error("Signal download failed for %s: %s", url, exc, exc_info=True)
            await c.reply(f"❌ Failed: {exc}")
        finally:
            await c.stop_typing()
            if session_dir is not None:
                await asyncio.to_thread(shutil.rmtree, session_dir, True)
