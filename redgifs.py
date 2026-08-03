from __future__ import annotations
import json
import logging
import re
import urllib.error
import urllib.request

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

ID_RE = re.compile(
    r"https?://(?:www\.)?redgifs\.com/(?:watch|ifr)/([^-/?#.]+)"
    r"|https?://thumbs2\.redgifs\.com/([^-/?#.]+)"
)

_API_BASE = "https://api.redgifs.com/v2"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.redgifs.com/",
    "Origin": "https://www.redgifs.com",
}

_token: str | None = None


def _gif_id(url: str) -> str:
    m = ID_RE.search(url)
    if not m:
        raise ValueError(f"could not parse RedGifs URL: {url}")
    return (m.group(1) or m.group(2)).lower()


def _fetch_token() -> str:
    req = urllib.request.Request(f"{_API_BASE}/auth/temporary", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    token = data.get("token")
    if not token:
        raise ValueError("RedGifs: unable to obtain temporary auth token")
    return token


def _get_gif(gif_id: str) -> dict:
    global _token
    for attempt in range(2):
        if _token is None:
            _token = _fetch_token()
        headers = dict(_HEADERS)
        headers["Authorization"] = f"Bearer {_token}"
        req = urllib.request.Request(f"{_API_BASE}/gifs/{gif_id}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 0:
                _token = None
                continue
            raise


def extract(url: str) -> MediaResult:
    gif_id = _gif_id(url)
    data = _get_gif(gif_id)

    if "error" in data:
        raise ValueError(f"RedGifs said: {data['error']}")

    gif = data.get("gif") or {}
    urls = gif.get("urls") or {}
    video_url = urls.get("hd") or urls.get("sd") or urls.get("gif")
    if not video_url:
        raise ValueError("no downloadable media found in RedGifs post")

    result = MediaResult(caption=" ".join(gif.get("tags") or []) or None)
    result.items.append(MediaItem(
        urls=[video_url],
        type="video",
        thumbnail_url=(gif.get("urls") or {}).get("thumbnail"),
        width=gif.get("width", 0),
        height=gif.get("height", 0),
    ))

    logger.info("RedGifs: extracted 1 item for %s", gif_id)
    return result
