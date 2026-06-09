from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Callable

from config import config
import nitter
import instagram
import bluesky
import tumblr
from models import MediaResult


@dataclass
class Extractor:
    name: str
    display_name: str
    pattern: re.Pattern[str]
    cookies_file: str | None = None
    url_transform: Callable[[str], str] | None = None
    reply_url: Callable[[str], str] | None = None
    extract: Callable[[str], MediaResult] | None = None


EXTRACTORS: list[Extractor] = [
    Extractor(
        name="twitter",
        display_name="Twitter/X",
        pattern=re.compile(
            r"https?://(?:(?:fx|vx|fixup)?(?:twitter|x)\.com|t\.co|nitter\.net)/\S+"
        ),
        url_transform=nitter.twitter_download_url,
        reply_url=nitter.twitter_reply_url,
    ),
    Extractor(
        name="instagram",
        display_name="Instagram",
        pattern=re.compile(
            r"https?://(?:www\.)?(?:dd)?instagram\.com/(?:p|reel|reels|tv|stories|share)/\S+"
        ),
        extract=instagram.extract,
    ),
    Extractor(
        name="bluesky",
        display_name="Bluesky",
        pattern=re.compile(
            r"https?://(?:bsky|witchsky)\.app/profile/[^/]+/post/[a-zA-Z0-9]+"
        ),
        extract=bluesky.extract,
    ),
    Extractor(
        name="youtube",
        display_name="YouTube",
        pattern=re.compile(
            r"https?://(?:(?:www\.|m\.)?youtube\.com/(?:watch|shorts|live)|youtu\.be/)\S+"
        ),
    ),
    Extractor(
        name="tumblr",
        display_name="Tumblr",
        pattern=re.compile(
            r"https?://(?:www\.tumblr\.com/[^/?#]+/\d+|[^./?#]+\.tumblr\.com/post/\d+)"
        ),
        extract=tumblr.extract,
    ),
    Extractor(
        name="tiktok",
        display_name="TikTok",
        pattern=re.compile(
            r"https?://(?:(?:www|m|vm|vt)\.)?(?:vx)?tiktok\.com/\S+"
        ),
        cookies_file=config.tiktok_cookies_file,
    ),
]


def find_extractor(url: str) -> Extractor | None:
    for extractor in EXTRACTORS:
        if extractor.pattern.search(url):
            return extractor
    return None
