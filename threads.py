from __future__ import annotations
import logging
import re
import urllib.request

from bs4 import BeautifulSoup

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

POST_ID_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:net|com)/(?:@[^/]+/)?p(?:ost)?/([a-zA-Z0-9_-]+)"
)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Dnt": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def extract(url: str) -> MediaResult:
    m = POST_ID_RE.search(url)
    if not m:
        raise ValueError(f"could not parse Threads post URL: {url}")

    post_id = m.group(1)
    embed_url = f"https://www.threads.net/@_/post/{post_id}/embed"

    req = urllib.request.Request(embed_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode(errors="replace")

    if "Thread not available" in body:
        raise ValueError("thread not available or private")

    soup = BeautifulSoup(body, "html.parser")

    caption_el = soup.select_one(".BodyTextContainer")
    caption = caption_el.get_text(strip=True) or None if caption_el else None

    result = MediaResult(caption=caption)

    for container in soup.select(".SoloMediaContainer, .MediaContainer"):
        for vid in container.find_all("video"):
            source = vid.find("source")
            src = source.get("src") if source else None
            if src:
                result.items.append(MediaItem(urls=[src], type="video"))
        for img in container.find_all("img"):
            src = img.get("src")
            if src:
                result.items.append(MediaItem(urls=[src], type="photo"))

    if not result.items:
        raise ValueError("no media found in Threads post")

    logger.info("Threads: extracted %d item(s) for post %s", len(result.items), post_id)
    return result
