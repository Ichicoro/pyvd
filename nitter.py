from __future__ import annotations
import json
import logging
import re
import time
import urllib.request

logger = logging.getLogger(__name__)

STATUS_API = "https://status.d420.de/api/v1/instances"
REPLY_HOST = "https://nitter.net"

# Known Nitter mirrors, treated as Twitter/X links wherever tweet URLs are matched.
KNOWN_DOMAINS = [
    "twitter.com", "x.com", "t.co",
    "nitter.net", "xcancel.com", "nitter.poast.org", "nitter.privacyredirect.com",
    "nitter.tiekoetter.com", "lightbrd.com", "nitter.catsarch.com", "nitter.kareem.one",
    "girlcockx.com",
]

TWITTER_URL_PATTERN = re.compile(
    r"https?://(?:(?:fx|vx|fixup)?(?:twitter|x)\.com|" +
    "|".join(re.escape(d) for d in KNOWN_DOMAINS if d not in ("twitter.com", "x.com")) +
    r")/\S+"
)

_TWITTER_PATH_RE = re.compile(
    r"https?://(?:(?:fx|vx|fixup)?(?:twitter|x)\.com|" +
    "|".join(re.escape(d) for d in KNOWN_DOMAINS if d not in ("twitter.com", "x.com")) +
    r")(.*)"
)

_cache: list[str] = []
_cache_time: float = 0.0
_CACHE_TTL = 300.0


def _fetch_instances() -> list[dict]:
    req = urllib.request.Request(STATUS_API, headers={"User-Agent": "pyvd/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return next((v for v in data.values() if isinstance(v, list)), [])
    return []


def get_healthy_instances() -> list[str]:
    global _cache, _cache_time
    now = time.monotonic()
    if _cache and now - _cache_time < _CACHE_TTL:
        return _cache

    try:
        raw = _fetch_instances()
    except Exception as exc:
        logger.warning("Failed to fetch Nitter instances: %s", exc)
        return _cache

    scored = sorted(
        (
            (inst["url"].rstrip("/"), inst.get("points", 0))
            for inst in raw
            if isinstance(inst, dict) and inst.get("healthy") and inst.get("url")
        ),
        key=lambda x: x[1],
        reverse=True,
    )
    _cache = [url for url, _ in scored]
    _cache_time = now
    logger.info("Nitter cache refreshed: %d healthy instances", len(_cache))
    return _cache


def pick_instance() -> str | None:
    instances = get_healthy_instances()
    return instances[0] if instances else None


def to_nitter_url(twitter_url: str, instance: str) -> str:
    m = _TWITTER_PATH_RE.match(twitter_url)
    return f"{instance}{m.group(1)}" if m else twitter_url


def twitter_download_url(url: str) -> str:
    instance = pick_instance()
    if instance is None:
        logger.warning("No healthy Nitter instance found, using original URL")
        return url
    return to_nitter_url(url, instance)


def twitter_reply_url(url: str) -> str:
    return to_nitter_url(url, REPLY_HOST)
