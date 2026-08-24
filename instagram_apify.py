"""Instagram extraction via the Apify actor shahidirfan/Instagram-Video-Downloader.

Primary path for Instagram when APIFY_TOKEN is set; instagram.py falls back to the
old cookie-based chain in instagram_legacy.py when this is unavailable or fails.

The actor has no photo-specific input flag: image posts come back through the
"browser" download method (yt-dlp only handles videos), so a run that yields no
media is retried with downloadMethod forced to "browser".

Two quirks of the actor drive the code below:

* `download_url` points at the run's key-value store, which 403s without the API
  token, so the token is appended to the URL before it reaches the downloader.
* The stored record is named `.mp4` and served as `Content-Type: video/mp4` even
  when it holds a JPEG, so the media type is decided by sniffing the first bytes;
  the item metadata is only a fallback.
"""
from __future__ import annotations
import logging
import re
import urllib.parse
import urllib.request

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

# shahidirfan/Instagram-Video-Downloader
DEFAULT_ACTOR_ID = "mGz1tKemfhpbQTkBv"

# Dataset items expose the direct media link under one of these, best first.
# NB: the item's "url" is the *input* post URL, not media — deliberately absent.
_URL_FIELDS = ("download_url", "downloadUrl", "video_url", "videoUrl", "image_url", "display_url", "media_url")
_THUMB_FIELDS = ("thumbnail", "thumbnail_url", "thumbnailUrl", "display_url")
_CAPTION_FIELDS = ("description", "caption", "title")

_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "heif", "gif", "avif"}
_VIDEO_EXTS = {"mp4", "mov", "webm", "m4v", "mkv"}
_AUDIO_EXTS = {"mp3", "m4a", "aac", "opus", "wav", "ogg"}

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_KVS_HOST = "api.apify.com"


def _field(obj, name: str, key: str):
    """Read a field off an apify-client model (3.x) or a plain dict (2.x)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, name, None)


def _authorize(url: str, token: str) -> str:
    """Key-value-store records are private; the downloader needs the token inline."""
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname != _KVS_HOST:
        return url
    query = urllib.parse.parse_qs(parsed.query)
    if "token" in query:
        return url
    query["token"] = [token]
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query, doseq=True))
    )


def _redact(url: str) -> str:
    return re.sub(r"(token=)[^&]+", r"\1<redacted>", url)


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


def _type_from_magic(head: bytes) -> str | None:
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM")):
        return "photo"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "photo"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio"
        return "video"
    if head.startswith((b"\x1a\x45\xdf\xa3", b"OggS")):  # matroska/webm, ogg
        return "video" if head.startswith(b"\x1a\x45\xdf\xa3") else "audio"
    if head.startswith((b"ID3", b"fLaC")) or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio"
    return None


def _sniff_media_type(url: str) -> str | None:
    """Read the first bytes of the media itself.

    The actor stores photos under an .mp4 name and serves them as video/mp4, so
    neither the extension nor the Content-Type can be trusted — the bytes can.
    """
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": _UA, "Range": "bytes=0-31"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            head = resp.read(32)
    except Exception as exc:
        logger.debug("Apify media sniff failed for %s: %s", _redact(url), exc)
        return None
    return _type_from_magic(head)


def _media_type(item: dict, url: str) -> str:
    sniffed = _sniff_media_type(url)
    if sniffed:
        return sniffed

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

    # the actor is video-oriented; default accordingly
    return "video"


def _media_items(item: dict, token: str) -> list[MediaItem]:
    """One dataset record → its media item.

    The actor emits a single record per input URL and exposes only one media
    file, so a carousel yields just its first slide — instagram.py prefers the
    legacy extractor when a post turns out to be photos, for that reason.
    """
    thumbnail = _first(item, _THUMB_FIELDS)
    url = _first(item, _URL_FIELDS)
    if not url:
        return []
    url = _authorize(url, token)
    media_type = _media_type(item, url)
    # the CDN thumbnail is a usable stand-in for a photo if the store copy fails
    urls = [url, thumbnail] if media_type == "photo" and thumbnail else [url]
    return [MediaItem(urls=urls, type=media_type, thumbnail_url=thumbnail)]


def _run_actor(client, actor_id: str, url: str, download_method: str, token: str) -> tuple[MediaResult, list[str]]:
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
    status = _field(run, "status", "status")
    dataset_id = _field(run, "default_dataset_id", "defaultDatasetId")
    if not dataset_id:
        raise RuntimeError(f"Apify run has no dataset (status {status})")
    # A run where every URL failed ends FAILED, but its dataset still holds the
    # per-URL error records — read them rather than raising on status alone.

    result = MediaResult()
    errors: list[str] = []
    for item in client.dataset(dataset_id).iterate_items():
        if not isinstance(item, dict):
            continue
        if item.get("error"):
            errors.append(str(item["error"]))
            continue
        media = _media_items(item, token)
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
        try:
            result, errors = _run_actor(client, actor_id, url, method, config.apify_token)
        except Exception as exc:
            logger.warning("Instagram Apify actor (%s) run failed: %s", method, exc)
            all_errors.append(f"{method}: {exc}")
            continue
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
