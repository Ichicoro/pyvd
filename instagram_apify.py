"""Instagram extraction via the Apify actor shahidirfan/Instagram-Video-Downloader.

Primary path for Instagram when APIFY_TOKEN is set; instagram.py falls back to the
old cookie-based chain in instagram_legacy.py when this is unavailable or fails.
"""
from __future__ import annotations
import logging

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

# shahidirfan/Instagram-Video-Downloader
DEFAULT_ACTOR_ID = "mGz1tKemfhpbQTkBv"

# Dataset items expose the direct media link under one of these, best first.
_URL_FIELDS = ("download_url", "url", "video_url", "videoUrl", "downloadUrl")
_THUMB_FIELDS = ("thumbnail", "thumbnail_url", "thumbnailUrl", "display_url")
_CAPTION_FIELDS = ("description", "caption", "title")

_VIDEO_EXTS = {"mp4", "mov", "webm", "m4v"}


def _first(item: dict, fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _media_type(item: dict, url: str) -> str:
    ext = (item.get("file_extension") or "").lower().lstrip(".")
    if not ext:
        tail = url.split("?")[0].rsplit(".", 1)
        ext = tail[1].lower() if len(tail) == 2 else ""
    if ext in {"jpg", "jpeg", "png", "webp", "heic"}:
        return "photo"
    if ext in _VIDEO_EXTS:
        return "video"
    # the actor is video-oriented; default accordingly
    return "video"


def extract(url: str) -> MediaResult:
    from config import config

    if not config.apify_token:
        raise RuntimeError("APIFY_TOKEN not configured")

    from apify_client import ApifyClient

    client = ApifyClient(config.apify_token)
    run_input = {
        "urls": [url],
        "downloadMode": "videos",
        "downloadMethod": "auto",
        "maxItems": 10,
        "quality": "best",
        "proxyConfiguration": {},
    }
    run = client.actor(config.apify_instagram_actor).call(run_input=run_input)
    if not run:
        raise RuntimeError("Apify actor returned no run")
    if run.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Apify run status: {run.get('status')}")

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError("Apify run has no dataset")

    result = MediaResult()
    errors: list[str] = []
    for item in client.dataset(dataset_id).iterate_items():
        if not isinstance(item, dict):
            continue
        if item.get("error"):
            errors.append(str(item["error"]))
            continue
        media_url = _first(item, _URL_FIELDS)
        if not media_url:
            continue
        if result.caption is None:
            result.caption = _first(item, _CAPTION_FIELDS)
        result.items.append(
            MediaItem(
                urls=[media_url],
                type=_media_type(item, media_url),
                thumbnail_url=_first(item, _THUMB_FIELDS),
            )
        )

    if not result.items:
        detail = "; ".join(errors) if errors else "no media in Apify dataset"
        raise RuntimeError(f"Apify actor returned no media: {detail}")

    logger.info("Instagram Apify actor returned %d item(s) for %s", len(result.items), url)
    return result
