from __future__ import annotations
import http.cookiejar
import json
import logging
import os
import re
import urllib.request

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

ARTWORK_URL_RE = re.compile(
    r"https?://(?:www\.)?pixiv\.net/(?:en/)?artworks/(\d+)"
    r"|https?://(?:www\.)?pixiv\.net/member_illust\.php\?[^\s#]*\billust_id=(\d+)"
)

REFERER = "https://www.pixiv.net/"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": REFERER,
    "Accept": "application/json",
}


def _parse_illust_id(url: str) -> str:
    m = ARTWORK_URL_RE.search(url)
    if not m:
        raise ValueError(f"could not parse Pixiv artwork URL: {url}")
    return m.group(1) or m.group(2)


def _load_cookie_header(cookies_file: str) -> str:
    jar = http.cookiejar.MozillaCookieJar(cookies_file)
    jar.load(ignore_discard=True, ignore_expires=True)
    return "; ".join(f"{c.name}={c.value}" for c in jar if "pixiv.net" in (c.domain or ""))


def _get_json(url: str, cookie_header: str | None) -> dict:
    headers = dict(_HEADERS)
    if cookie_header:
        headers["Cookie"] = cookie_header
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if data.get("error"):
        raise ValueError(data.get("message") or "Pixiv API returned an error")
    return data["body"]


def extract(url: str) -> MediaResult:
    illust_id = _parse_illust_id(url)

    from config import config
    cookies_file = config.pixiv_cookies_file
    cookie_header = None
    if cookies_file and os.path.exists(cookies_file):
        try:
            cookie_header = _load_cookie_header(cookies_file)
        except Exception as exc:
            logger.warning("Failed to load Pixiv cookies from %s: %s", cookies_file, exc)

    meta = _get_json(f"https://www.pixiv.net/ajax/illust/{illust_id}", cookie_header)
    caption = meta.get("title") or None
    result = MediaResult(caption=caption)

    if meta.get("illustType") == 2:
        # ugoira (animated illustration) is delivered as a zip of frames; not a
        # format Telegram can display directly, so we skip it rather than send a zip.
        raise ValueError("Pixiv ugoira (animated) posts are not supported")

    pages = _get_json(f"https://www.pixiv.net/ajax/illust/{illust_id}/pages", cookie_header)
    for page in pages:
        original = (page.get("urls") or {}).get("original")
        if original:
            result.items.append(MediaItem(
                urls=[original],
                type="photo",
                width=page.get("width", 0),
                height=page.get("height", 0),
            ))

    if not result.items:
        raise ValueError("no media found in Pixiv artwork")

    logger.info("Pixiv: extracted %d item(s) for illust %s", len(result.items), illust_id)
    return result
