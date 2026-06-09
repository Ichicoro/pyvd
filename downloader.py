from __future__ import annotations
import logging
import os
import shutil
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator

import yt_dlp

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
AUDIO_EXTS = {".mp3", ".m4a", ".ogg", ".flac", ".opus", ".wav"}
SKIP_EXTS = {".json", ".part", ".ytdl", ".description", ".annotations"}

_EXT_FOR_TYPE = {"video": "mp4", "photo": "jpg", "audio": "mp3"}


def file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in PHOTO_EXTS:
        return "photo"
    if ext in AUDIO_EXTS:
        return "audio"
    return "document"


@contextmanager
def download(
    url: str,
    base_dir: str = "/tmp/pygovd",
    cookies_file: str | None = None,
    url_transform: Callable[[str], str] | None = None,
    extract: Callable[[str], MediaResult] | None = None,
) -> Generator[list[Path], None, None]:
    session_dir = Path(base_dir) / uuid.uuid4().hex
    session_dir.mkdir(parents=True, exist_ok=True)
    try:
        if extract is not None:
            files = _download_from_extractor(extract, url, session_dir)
        else:
            effective_url = url_transform(url) if url_transform else url
            if effective_url != url:
                logger.info("URL rewritten: %s -> %s", url, effective_url)
            files = _do_ytdlp(effective_url, session_dir, cookies_file)
        yield files
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)


def _download_from_extractor(
    extract: Callable[[str], MediaResult],
    url: str,
    dest: Path,
) -> list[Path]:
    result = extract(url)
    files: list[Path] = []
    for i, item in enumerate(result.items):
        ext = _EXT_FOR_TYPE.get(item.type, "bin")
        path = dest / f"{i:04d}.{ext}"
        _fetch_url(item, path)
        files.append(path)
    logger.info("Downloaded %d file(s) via custom extractor", len(files))
    return files


def _fetch_url(item: MediaItem, dest: Path) -> None:
    last_exc: Exception | None = None
    for url in item.urls:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("Failed to fetch %s: %s", url, exc)
    raise RuntimeError(f"all URLs failed for item: {last_exc}")


def _do_ytdlp(url: str, dest: Path, cookies_file: str | None) -> list[Path]:
    ydl_opts: dict = {
        "outtmpl": str(dest / "%(autonumber)04d.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "format": (
            "bestvideo[ext=mp4][filesize<50M]+bestaudio[ext=m4a]"
            "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/best[ext=mp4]/best"
        ),
        "writeinfojson": False,
        "writethumbnail": False,
        "nopart": True,
    }
    if cookies_file and Path(cookies_file).exists():
        ydl_opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = sorted(
        p for p in dest.iterdir()
        if p.is_file() and p.suffix.lower() not in SKIP_EXTS
    )
    logger.info("Downloaded %d file(s) from %s", len(files), url)
    return files
