from __future__ import annotations
import logging
import re

from atproto import Client

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

POST_URL_RE = re.compile(
    r"https?://(?:bsky|witchsky)\.app/profile/([^/]+)/post/([a-zA-Z0-9]+)"
)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(base_url="https://public.api.bsky.app")
    return _client


def _extract_embed(embed, result: MediaResult) -> None:
    if embed is None:
        return

    # Images
    images = getattr(embed, "images", None)
    if images:
        for img in images:
            url = getattr(img, "fullsize", None) or getattr(img, "thumb", None)
            if url:
                result.items.append(MediaItem(urls=[url], type="photo"))
        return

    # Video (served as HLS playlist)
    playlist = getattr(embed, "playlist", None)
    if playlist:
        thumbnail = getattr(embed, "thumbnail", None)
        result.items.append(MediaItem(urls=[playlist], type="video", thumbnail_url=thumbnail))
        return

    # Quote post with media — recurse into the media half
    media = getattr(embed, "media", None)
    if media is not None:
        _extract_embed(media, result)


def extract(url: str) -> MediaResult:
    m = POST_URL_RE.search(url)
    if not m:
        raise ValueError(f"could not parse Bluesky post URL: {url}")

    handle, rkey = m.group(1), m.group(2)
    at_uri = f"at://{handle}/app.bsky.feed.post/{rkey}"

    thread = _get_client().get_post_thread(uri=at_uri)
    post = thread.thread.post

    result = MediaResult(caption=getattr(post.record, "text", None) or None)
    _extract_embed(post.embed, result)

    if not result.items:
        raise ValueError("no media found in Bluesky post")

    return result
