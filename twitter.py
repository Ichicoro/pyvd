from __future__ import annotations
import json
import logging
import re
import urllib.request

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

_STATUS_RE = re.compile(r"/status/(\d+)")
_API_BASE = "https://api.fxtwitter.com/status/"
_HEADERS = {"User-Agent": "pyvd/1.0"}


def _tweet_id(url: str) -> str:
    m = _STATUS_RE.search(url)
    if not m:
        raise ValueError(f"could not extract tweet ID from: {url}")
    return m.group(1)


def extract(url: str) -> MediaResult:
    tweet_id = _tweet_id(url)
    req = urllib.request.Request(_API_BASE + tweet_id, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    code = data.get("code")
    if code not in (200, None):
        raise ValueError(f"fxtwitter: {data.get('message', code)}")

    tweet = data.get("tweet", {})
    media = tweet.get("media") or {}
    result = MediaResult(caption=tweet.get("text") or None)

    for photo in media.get("photos", []):
        media_url = photo.get("url")
        if media_url:
            result.items.append(MediaItem(
                urls=[media_url],
                type="photo",
                width=photo.get("width", 0),
                height=photo.get("height", 0),
            ))

    for video in media.get("videos", []):
        media_url = video.get("url")
        if media_url:
            result.items.append(MediaItem(
                urls=[media_url],
                type="video",
                width=video.get("width", 0),
                height=video.get("height", 0),
                thumbnail_url=video.get("thumbnail_url"),
            ))

    if not result.items:
        raise ValueError("no media in tweet")

    return result
