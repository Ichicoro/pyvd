from __future__ import annotations
import json
import logging
import re
import urllib.parse
import urllib.request

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

# https://blogname.tumblr.com/post/123/slug  OR  https://www.tumblr.com/blogname/123/slug
POST_URL_RE = re.compile(
    r"https?://(?:www\.tumblr\.com/([^/?#]+)/(\d+)|([^./?#]+)\.tumblr\.com/post/(\d+))"
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _parse_url(url: str) -> tuple[str, str]:
    m = POST_URL_RE.search(url)
    if not m:
        raise ValueError(f"could not parse Tumblr post URL: {url}")
    # group(1)/group(2) = www.tumblr.com/blog/id form
    # group(3)/group(4) = blog.tumblr.com/post/id form
    blog = m.group(1) or m.group(3)
    post_id = m.group(2) or m.group(4)
    return blog, post_id


def _get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={**_HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


# ── method 1: v2 API ───────────────────────────────────────────────────────────

def _api_media(blog: str, post_id: str, api_key: str) -> MediaResult:
    url = (
        f"https://api.tumblr.com/v2/blog/{blog}/posts"
        f"?api_key={urllib.parse.quote(api_key)}&id={post_id}&npf=true"
    )
    raw = _get(url, {"Accept": "application/json"})
    data = json.loads(raw)

    posts = data.get("response", {}).get("posts", [])
    if not posts:
        raise ValueError("no posts in API response")

    post = posts[0]
    caption = post.get("summary") or None
    result = MediaResult(caption=caption)

    for block in post.get("content", []):
        btype = block.get("type")
        if btype == "image":
            media_list = block.get("media", [])
            if not media_list:
                continue
            # pick highest resolution variant
            best = max(media_list, key=lambda m: m.get("width", 0) * m.get("height", 0))
            url_str = best.get("url")
            if url_str:
                result.items.append(MediaItem(
                    urls=[url_str],
                    type="photo",
                    width=best.get("width", 0),
                    height=best.get("height", 0),
                ))

    # legacy photo posts (non-NPF)
    if not result.items:
        for photo in post.get("photos", []):
            orig = photo.get("original_size", {}).get("url")
            if orig:
                result.items.append(MediaItem(urls=[orig], type="photo"))

    if not result.items:
        raise ValueError("no photo content in API response")
    return result


# ── method 2: HTML scrape ──────────────────────────────────────────────────────

_INITIAL_DATA_RE = re.compile(
    r'window\[(?:\'|")___INITIAL_DATA___(?:\'|")\]\s*=\s*({.+?});\s*</script>',
    re.DOTALL,
)
_OG_IMAGE_RE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')
_FIGURE_IMG_RE = re.compile(r'<figure[^>]*>.*?<img[^>]+src="([^"]+)"', re.DOTALL)


def _scrape_media(blog: str, post_id: str) -> MediaResult:
    page_url = f"https://{blog}.tumblr.com/post/{post_id}"
    html = _get(page_url).decode(errors="replace")

    result = MediaResult()

    # Try embedded JSON first
    m = _INITIAL_DATA_RE.search(html)
    if m:
        try:
            data = json.loads(m.group(1))
            posts = (
                data.get("PostStore", {}).get("postsById", {}).values()
                or data.get("posts", [])
            )
            for post in posts:
                for block in post.get("content", []):
                    if block.get("type") == "image":
                        media_list = block.get("media", [])
                        if not media_list:
                            continue
                        best = max(media_list, key=lambda m: m.get("width", 0) * m.get("height", 0))
                        url_str = best.get("url")
                        if url_str:
                            result.items.append(MediaItem(urls=[url_str], type="photo"))
            if result.items:
                return result
        except Exception as exc:
            logger.debug("INITIAL_DATA parse failed: %s", exc)

    # Fall back to og:image (first image only)
    m = _OG_IMAGE_RE.search(html)
    if m:
        result.items.append(MediaItem(urls=[m.group(1)], type="photo"))
        return result

    raise ValueError("no images found in Tumblr page")


# ── public entry point ─────────────────────────────────────────────────────────

def extract(url: str) -> MediaResult:
    blog, post_id = _parse_url(url)

    from config import config
    api_key = getattr(config, "tumblr_api_key", None)

    methods: list[tuple[str, object]] = []
    if api_key:
        methods.append(("API", lambda: _api_media(blog, post_id, api_key)))
    methods.append(("scrape", lambda: _scrape_media(blog, post_id)))

    for name, method in methods:
        try:
            result = method()
            logger.info("Tumblr %s method succeeded for %s/%s", name, blog, post_id)
            return result
        except Exception as exc:
            logger.warning("Tumblr %s method failed: %s", name, exc)

    raise RuntimeError(f"all Tumblr methods failed for {blog}/{post_id}")
