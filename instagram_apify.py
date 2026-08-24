"""Instagram extraction via the Apify actor shahidirfan/Instagram-Video-Downloader.

Primary path for Instagram when APIFY_TOKEN is set; instagram.py falls back to the
old cookie-based chain in instagram_legacy.py when this is unavailable or fails.

The actor has no photo-specific input flag: image posts come back through the
"browser" download method (yt-dlp only handles videos), so a run that yields no
media is retried with downloadMethod forced to "browser".
"""
from __future__ import annotations
import logging
import urllib.parse
import urllib.request

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

# shahidirfan/Instagram-Video-Downloader
DEFAULT_ACTOR_ID = "mGz1tKemfhpbQTkBv"

# Dataset items expose the direct media link under one of these, best first.
_URL_FIELDS = ("download_url", "url", "video_url", "videoUrl", "downloadUrl", "image_url", "display_url")
_THUMB_FIELDS = ("thumbnail", "thumbnail_url", "thumbnailUrl", "display_url")
_CAPTION_FIELDS = ("description", "caption", "title")
# carousels arrive as a list of children under one of these
_CHILDREN_FIELDS = ("media", "images", "items", "children", "media_urls", "downloads")

_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "heif", "gif", "avif"}
_VIDEO_EXTS = {"mp4", "mov", "webm", "m4v", "mkv"}
_AUDIO_EXTS = {"mp3", "m4a", "aac", "opus", "wav", "ogg"}

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _first(item: dict, fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _type_for_ext(ext: str | None) -> str | None:
    if not ext:
        return None
    ext = ext.lower().lstrip(".")
    if ext in _IMAGE_EXTS:
        return "photo"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _AUDIO_EXTS:
        return "audio"
    return None


def _ext_from_url(url: str) -> str | None:
    path = urllib.parse.urlparse(url).path
    _, _, tail = path.rpartition("/")
    if "." not in tail:
        return None
    return tail.rsplit(".", 1)[1]


def _probe_content_type(url: str) -> str | None:
    """Last resort when nothing in the item says what the media is."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA}, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    except Exception as exc:
        logger.debug("Apify media content-type probe failed for %s: %s", url, exc)
        return None
    if ctype.startswith("image/"):
        return "photo"
    if ctype.startswith("video/"):
        return "video"
    if ctype.startswith("audio/"):
        return "audio"
    return None


def _media_type(item: dict, url: str) -> str:
    for candidate in (
        _type_for_ext(item.get("file_extension")),
        _type_for_ext(item.get("downloaded_format")),
        _type_for_ext(_ext_from_url(url)),
    ):
        if candidate:
            return candidate

    duration = item.get("duration")
    if isinstance(duration, (int, float)) and duration > 0:
        return "video"

    probed = _probe_content_type(url)
    if probed:
        return probed

    # the actor is video-oriented; default accordingly
    return "video"


def _media_items(item: dict) -> list[MediaItem]:
    """One dataset record → one or more MediaItems (carousels list their children)."""
    thumbnail = _first(item, _THUMB_FIELDS)

    children: list[dict] = []
    for field in _CHILDREN_FIELDS:
        value = item.get(field)
        if isinstance(value, list) and value:
            for child in value:
                if isinstance(child, dict):
                    children.append(child)
                elif isinstance(child, str) and child.strip():
                    children.append({"url": child.strip()})
            if children:
                break

    media: list[MediaItem] = []
    for child in children:
        url = _first(child, _URL_FIELDS)
        if not url:
            continue
        media.append(
            MediaItem(
                urls=[url],
                type=_media_type({**item, **child}, url),
                thumbnail_url=_first(child, _THUMB_FIELDS) or thumbnail,
            )
        )
    if media:
        return media

    url = _first(item, _URL_FIELDS)
    if not url:
        return []
    return [MediaItem(urls=[url], type=_media_type(item, url), thumbnail_url=thumbnail)]


def _run_actor(client, actor_id: str, url: str, download_method: str) -> tuple[MediaResult, list[str]]:
    run_input = {
        "urls": [url],
        "downloadMode": "videos",
        "downloadMethod": download_method,
        "maxItems": 10,
        "quality": "best",
        "proxyConfiguration": {},
    }
    run = client.actor(actor_id).call(run_input=run_input)
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
        media = _media_items(item)
        if not media:
            continue
        if result.caption is None:
            result.caption = _first(item, _CAPTION_FIELDS)
        result.items.extend(media)

    return result, errors


def extract(url: str) -> MediaResult:
    from config import config

    if not config.apify_token:
        raise RuntimeError("APIFY_TOKEN not configured")

    from apify_client import ApifyClient

    client = ApifyClient(config.apify_token)
    actor_id = config.apify_instagram_actor

    all_errors: list[str] = []
    # "auto" tries yt-dlp first (fast, videos only); "browser" reads the direct
    # media URLs off the page, which is how photo posts come through.
    for method in ("auto", "browser"):
        result, errors = _run_actor(client, actor_id, url, method)
        all_errors.extend(errors)
        if result.items:
            logger.info(
                "Instagram Apify actor (%s) returned %d item(s) for %s",
                method, len(result.items), url,
            )
            return result
        logger.info("Instagram Apify actor (%s) returned no media for %s", method, url)

    detail = "; ".join(dict.fromkeys(all_errors)) if all_errors else "no media in Apify dataset"
    raise RuntimeError(f"Apify actor returned no media: {detail}")
