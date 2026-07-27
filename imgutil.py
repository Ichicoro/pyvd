from __future__ import annotations
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Telegram rejects sendPhoto uploads above this size regardless of the bot's
# own MAX_FILE_SIZE_MB setting. Leave a little headroom below the hard cap.
TELEGRAM_PHOTO_LIMIT = 10 * 1024 * 1024
_TARGET_SIZE = TELEGRAM_PHOTO_LIMIT - 64 * 1024

_QUALITY_STEPS = (90, 80, 70, 60, 50, 40, 30)
_MIN_SCALE = 0.15


def compress_photo(path: Path) -> None:
    """Shrink an oversized photo in place so it always fits Telegram's sendPhoto cap.

    Tries a lossless re-encode first (stripped metadata, optimized entropy
    coding, original pixels untouched). Only if that isn't enough does it fall
    back to reducing JPEG quality, then downscaling resolution — always as a
    last resort, since we'd rather send a still-full-quality photo than a
    document.
    """
    if path.stat().st_size <= TELEGRAM_PHOTO_LIMIT:
        return

    try:
        with Image.open(path) as img:
            img.load()
            fmt = img.format
    except Exception as exc:
        logger.warning("Failed to open %s for compression: %s", path, exc)
        return

    if fmt == "JPEG":
        img.save(path, format="JPEG", quality="keep", optimize=True, progressive=True)
    elif fmt == "PNG":
        img.save(path, format="PNG", optimize=True)
    if path.stat().st_size <= _TARGET_SIZE:
        logger.info("Losslessly compressed %s to %d bytes", path, path.stat().st_size)
        return

    rgb = img.convert("RGB") if img.mode != "RGB" else img

    for quality in _QUALITY_STEPS:
        rgb.save(path, format="JPEG", quality=quality, optimize=True, progressive=True)
        if path.stat().st_size <= _TARGET_SIZE:
            logger.info("Compressed %s to %d bytes at quality=%d", path, path.stat().st_size, quality)
            return

    scale = 0.9
    while scale >= _MIN_SCALE:
        w = max(1, round(rgb.width * scale))
        h = max(1, round(rgb.height * scale))
        resized = rgb.resize((w, h), Image.LANCZOS)
        resized.save(path, format="JPEG", quality=70, optimize=True, progressive=True)
        if path.stat().st_size <= _TARGET_SIZE:
            logger.info("Downscaled %s to %dx%d (%d bytes)", path, w, h, path.stat().st_size)
            return
        scale -= 0.1

    logger.warning("Could not shrink %s under %d bytes (final size %d)", path, TELEGRAM_PHOTO_LIMIT, path.stat().st_size)
