from __future__ import annotations
import asyncio
import logging
import re
import shutil
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

from telegram import Bot, Update, InputMediaVideo, InputMediaPhoto, InputMediaDocument
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import db
from config import config
from downloader import download_blocking, file_type
from extractors import find_extractor

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://\S+|(?<!\w)(?:www\.)?\w[\w.-]*/\S*")

_TRACKING_PARAMS = re.compile(
    r"^(utm_\w+|igsh|fbclid|si|ref|ref_src|ref_url|twsrc|twgr|twcon|s|share_id)$",
    re.IGNORECASE,
)


def _clean_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    qs = {k: v for k, v in urllib.parse.parse_qsl(parsed.query) if not _TRACKING_PARAMS.match(k)}
    cleaned = parsed._replace(query=urllib.parse.urlencode(qs), fragment="")
    return urllib.parse.urlunparse(cleaned)
MAX_ALBUM_SIZE = 10


@asynccontextmanager
async def _chat_action(bot: Bot, chat_id: int, action: ChatAction):
    async def _repeat():
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)

    task = asyncio.create_task(_repeat())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _upload_action(files: list[Path]) -> ChatAction:
    types = {file_type(f) for f in files}
    if types == {"photo"}:
        return ChatAction.UPLOAD_PHOTO
    if types == {"audio"}:
        return ChatAction.UPLOAD_VOICE
    return ChatAction.UPLOAD_VIDEO


async def _send_to_chat(bot: Bot, chat_id: int, path: Path, caption: str | None = None) -> None:
    ftype = file_type(path)
    with open(path, "rb") as fh:
        if ftype == "video":
            await bot.send_video(chat_id, fh, supports_streaming=True, caption=caption, write_timeout=120)
        elif ftype == "photo":
            await bot.send_photo(chat_id, fh, caption=caption, write_timeout=120)
        elif ftype == "audio":
            await bot.send_audio(chat_id, fh, caption=caption, write_timeout=120)
        else:
            await bot.send_document(chat_id, fh, caption=caption, write_timeout=120)


async def _send_files_to_chat(bot: Bot, chat_id: int, files: list[Path], caption: str | None = None) -> None:
    if len(files) == 1:
        await _send_to_chat(bot, chat_id, files[0], caption=caption)
        return

    for i in range(0, len(files), MAX_ALBUM_SIZE):
        chunk = files[i : i + MAX_ALBUM_SIZE]
        media_group = []
        opened = []
        try:
            for j, path in enumerate(chunk):
                fh = open(path, "rb")
                opened.append(fh)
                ftype = file_type(path)
                item_caption = caption if j == 0 else None
                if ftype == "video":
                    media_group.append(InputMediaVideo(fh, caption=item_caption))
                elif ftype == "photo":
                    media_group.append(InputMediaPhoto(fh, caption=item_caption))
                else:
                    media_group.append(InputMediaDocument(fh, caption=item_caption))
            await bot.send_media_group(chat_id, media_group, write_timeout=120)
        finally:
            for fh in opened:
                fh.close()


async def download_and_deliver(bot: Bot, chat_id: int, url: str) -> None:
    """Download url and send resulting files to chat_id. Raises on failure."""
    extractor = find_extractor(url)
    if extractor is None:
        raise ValueError(f"Unsupported URL: {url}")

    session_dir = None
    try:
        async with _chat_action(bot, chat_id, ChatAction.TYPING):
            session_dir, files = await asyncio.to_thread(
                download_blocking,
                url,
                config.download_dir,
                extractor.cookies_file,
                extractor.url_transform,
                extractor.extract,
            )

        if not files:
            raise ValueError("No media found")

        sendable = [f for f in files if f.stat().st_size <= config.max_file_size]
        if not sendable:
            limit_mb = config.max_file_size // 1024 // 1024
            raise ValueError(f"All files exceed {limit_mb}MB limit")

        caption = extractor.reply_url(_clean_url(url)) if extractor.reply_url else _clean_url(url)
        async with _chat_action(bot, chat_id, _upload_action(sendable)):
            await _send_files_to_chat(bot, chat_id, sendable, caption=caption)

        skipped = len(files) - len(sendable)
        if skipped:
            await bot.send_message(chat_id, f"⚠️ {skipped} file(s) skipped (too large).")
    finally:
        if session_dir is not None:
            await asyncio.to_thread(shutil.rmtree, session_dir, True)


async def handle_apikey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if update.effective_chat and update.effective_chat.type != "private":
        await message.reply_text("⚠️ This command is only available in private chats.")
        return
    key, created = db.get_or_create_api_key(user.id)
    verb = "generated" if created else "existing"
    await message.reply_text(
        f"Your {verb} API key:\n<code>{key}</code>\n\nKeep it secret.",
        parse_mode="HTML",
    )


async def handle_resetapikey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if update.effective_chat and update.effective_chat.type != "private":
        await message.reply_text("⚠️ This command is only available in private chats.")
        return
    key = db.reset_api_key(user.id)
    await message.reply_text(
        f"API key reset. New key:\n<code>{key}</code>\n\nYour old key is now invalid.",
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    user = update.effective_user
    if config.allowed_user_ids is not None and (user is None or user.id not in config.allowed_user_ids):
        return

    text = message.text or message.caption or ""
    urls = URL_RE.findall(text)
    logger.info("Message received: %d URL(s) found", len(urls))

    bot = context.bot
    chat_id = message.chat_id

    unsupported: list[str] = []
    for raw_url in urls:
        url = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
        if find_extractor(url) is None:
            logger.info("No extractor for URL: %s", url)
            unsupported.append(url)
            continue

        status = await message.reply_text(f"⬇️ Downloading...")
        try:
            await download_and_deliver(bot, chat_id, url)
            await status.delete()
        except Exception as exc:
            logger.error("Download failed for %s: %s", url, exc, exc_info=True)
            await status.edit_text(f"❌ Failed: {exc}")

    if unsupported and message.chat.type == "private":
        lines = "\n".join(f"• {u}" for u in unsupported)
        await message.reply_text(f"⚠️ Unsupported URL(s):\n{lines}")
