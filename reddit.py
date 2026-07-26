from __future__ import annotations
import logging
import re
import urllib.parse
import urllib.request

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

# Tried in order; first instance that returns real post content wins. Public
# Redlib instances vary in uptime and many sit behind bot-challenge walls
# (Anubis, go-away, etc.) that a plain HTTP client can't pass, so we can't
# assume any of them work reliably.
PUBLIC_INSTANCES = [
    "https://redlib.catsarch.com",
    "https://redlib.matthew.science",
    "https://redlib.privacyredirect.com",
    "https://red.artemislena.eu",
    "https://redlib.privadency.com",
    "https://safereddit.com",
]


def _instances() -> list[str]:
    from config import config
    if config.redlib_service:
        return [f"http://{config.redlib_service}", *PUBLIC_INSTANCES]
    return PUBLIC_INSTANCES


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Ask Redlib to serve the HLS (video+audio) source instead of the
    # audio-less DASH mp4 fallback.
    "Cookie": "use_hls=on",
}

_POST_TYPE_RE = re.compile(r"<!--\s*post_type:\s*(\w+)\s*-->")
_IMAGE_RE = re.compile(r'<a href="([^"]+)"\s+class="post_media_image"')
_SOURCE_RE = re.compile(r'<source src="([^"]+)" type="(?:application/vnd\.apple\.mpegurl|video/mp4)"\s*/>')
_SIMPLE_VIDEO_RE = re.compile(r'<video class="post_media_video" src="([^"]+)"')
_GALLERY_IMG_RE = re.compile(r'<img loading="lazy" alt="Gallery image" src="([^"]+)"')


def _fetch(instance: str, path: str) -> str:
    req = urllib.request.Request(instance + path, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _absolute(instance: str, url: str) -> str:
    return url if url.startswith("http") else instance + url


def _post_path(url: str) -> str:
    return urllib.parse.urlparse(url).path or "/"


def extract(url: str) -> MediaResult:
    path = _post_path(url)

    html = None
    used_instance = None
    failures: list[str] = []
    for instance in _instances():
        try:
            candidate = _fetch(instance, path)
        except Exception as exc:
            failures.append(f"{instance}: {exc}")
            logger.warning("Redlib instance %s failed: %s", instance, exc)
            continue
        if _POST_TYPE_RE.search(candidate):
            html, used_instance = candidate, instance
            break
        failures.append(f"{instance}: no post content (likely blocked)")
        logger.warning("Redlib instance %s returned no post content (likely blocked)", instance)

    if html is None or used_instance is None:
        raise ValueError(f"all Redlib instances failed: {'; '.join(failures)}")

    post_type = _POST_TYPE_RE.search(html).group(1)
    result = MediaResult()

    if post_type == "image":
        m = _IMAGE_RE.search(html)
        if m:
            result.items.append(MediaItem(urls=[_absolute(used_instance, m.group(1))], type="photo"))
    elif post_type in ("video", "gif"):
        urls = [_absolute(used_instance, u) for u in _SOURCE_RE.findall(html)]
        if not urls:
            m = _SIMPLE_VIDEO_RE.search(html)
            if m:
                urls = [_absolute(used_instance, m.group(1))]
        if urls:
            result.items.append(MediaItem(urls=urls, type="video"))
    elif post_type == "gallery":
        for img_url in _GALLERY_IMG_RE.findall(html):
            result.items.append(MediaItem(urls=[_absolute(used_instance, img_url)], type="photo"))

    if not result.items:
        raise ValueError(f"no downloadable media found in Reddit post (type={post_type})")

    logger.info("Reddit: extracted %d item(s) via %s", len(result.items), used_instance)
    return result
