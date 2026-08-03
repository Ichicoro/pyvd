from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Callable

from config import config
import nitter
import twitter
import instagram
import bluesky
import tumblr
import threads
import pixiv
import reddit
import redgifs
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
            r"https?://(?:(?:fx|vx|fixup)?(?:twitter|x)\.com|t\.co"
            r"|nitter\.net|xcancel\.com|nitter\.poast\.org|nitter\.privacyredirect\.com"
            r"|nitter\.tiekoetter\.com|lightbrd\.com|nitter\.catsarch\.com|nitter\.kareem\.one"
            r"|girlcockx\.com)/\S+"
        ),
        reply_url=nitter.twitter_reply_url,
        extract=twitter.extract,
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
        cookies_file=config.youtube_cookies_file,
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
    Extractor(
        name="threads",
        display_name="Threads",
        pattern=re.compile(
            r"https?://(?:www\.)?threads\.(?:net|com)/@[^/]+/post/[a-zA-Z0-9_-]+"
        ),
        extract=threads.extract,
    ),
    Extractor(
        name="pixiv",
        display_name="Pixiv",
        pattern=re.compile(
            r"https?://(?:www\.)?pixiv\.net/(?:en/)?artworks/\d+"
            r"|https?://(?:www\.)?pixiv\.net/member_illust\.php\?[^\s#]*\billust_id=\d+"
        ),
        extract=pixiv.extract,
    ),
    Extractor(
        name="reddit",
        display_name="Reddit",
        pattern=re.compile(
            r"https?://(?:(?:www|old|new|np|m)\.)?reddit\.com/\S+"
            r"|https?://redd\.it/\S+"
        ),
        extract=reddit.extract,
    ),
    Extractor(
        name="redgifs",
        display_name="RedGifs",
        pattern=re.compile(
            r"https?://(?:www\.)?redgifs\.com/(?:watch|ifr)/[^-/?#\s.]+"
            r"|https?://thumbs2\.redgifs\.com/[^-/?#\s.]+"
        ),
        extract=redgifs.extract,
    ),
]


def find_extractor(url: str) -> Extractor | None:
    for extractor in EXTRACTORS:
        if extractor.pattern.search(url):
            return extractor
    return None
