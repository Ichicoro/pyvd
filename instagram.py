from __future__ import annotations
import hashlib
import hmac
import http.cookiejar
import json
import logging
import os
import random
import re
import string
import time
import urllib.error
import urllib.parse
import urllib.request

import yt_dlp

from models import MediaItem, MediaResult

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://www.instagram.com/graphql/query/"
POLARIS_ACTION = "PolarisPostActionLoadPostQueryQuery"
IGRAM_HOSTNAME = "api-wh.igram.world"
IGRAM_API_BASE = "api.igram.world"
IGRAM_HMAC_KEY = bytes.fromhex(
    "75f2d70d3724f98e4a7d1ffd0ba9cfd907f3ae2632ee159980e2c521bff62358"
)
IGRAM_STATIC_TS = 1771418815381

_BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_ALPHA_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

SHORTCODE_RE = re.compile(r"(?:dd)?instagram\.com/(?:p|reel|reels|tv)/([a-zA-Z0-9_-]+)")
STORY_RE = re.compile(r"(?:dd)?instagram\.com/stories/[a-zA-Z0-9._]+/(\d+)")
SHARE_RE = re.compile(r"(?:dd)?instagram\.com/share/(?:(?:reel|video|s|p)/)?([^/?]+)")
CONTEXT_JSON_RE = re.compile(r'"contextJSON"\s*:\s*"((?:[^"\\]|\\.)*)"')

WEB_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Dnt": "1",
    "Priority": "u=0, i",
    "Sec-Ch-Ua": 'Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": "macOS",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

IGRAM_EXTRA_HEADERS = {
    "Referer": "https://igram.world/",
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _load_ig_cookies(cookies_file: str) -> tuple[str, dict[str, str]]:
    """Return (cookie_header_string, {name: value} dict) for instagram.com cookies."""
    jar = http.cookiejar.MozillaCookieJar(cookies_file)
    jar.load(ignore_discard=True, ignore_expires=True)
    ig = {c.name: c.value for c in jar if c.domain.endswith("instagram.com")}
    header = "; ".join(f"{k}={v}" for k, v in ig.items())
    return header, ig


def _random_base64(n: int) -> str:
    return "".join(random.choices(_BASE64_CHARS, k=n))


def _random_alpha(n: int) -> str:
    return "".join(random.choices(_ALPHA_CHARS, k=n))


def _get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _post(url: str, data: bytes, headers: dict) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _parse_media(node: dict) -> MediaItem | None:
    typename = node.get("__typename", "")
    if typename in ("GraphVideo", "XDTGraphVideo"):
        video_url = node.get("video_url")
        if not video_url:
            return None
        dimensions = node.get("dimensions") or {}
        return MediaItem(
            urls=[video_url],
            type="video",
            thumbnail_url=node.get("display_url"),
            width=dimensions.get("width", 0),
            height=dimensions.get("height", 0),
        )
    if typename in ("GraphImage", "XDTGraphImage"):
        display_url = node.get("display_url")
        if not display_url:
            return None
        return MediaItem(urls=[display_url], type="photo")
    return None


# ── method 1: GQL API ──────────────────────────────────────────────────────────

def _build_gql_request(shortcode: str, real_cookies: dict[str, str] | None = None) -> tuple[dict, bytes]:
    session_data = _random_base64(8)
    device_id = _random_base64(24)
    machine_id = _random_base64(24)
    dynamic_flags = _random_base64(154)
    client_session_rnd = _random_base64(154)
    jazoest = str(random.randint(1, 10000))
    timestamp = str(int(time.time()))
    session = "::" + _random_alpha(6)

    if real_cookies:
        csrf_token = real_cookies.get("csrftoken", _random_base64(32))
        cookie_str = "; ".join(f"{k}={v}" for k, v in real_cookies.items())
    else:
        csrf_token = _random_base64(32)
        cookie_str = f"csrftoken={csrf_token}; ig_did={device_id}; wd=1280x720; dpr=2; mid={machine_id}; ig_nrcb=1"

    headers = {
        "x-ig-app-id": "936619743392459",
        "X-FB-LSD": session_data,
        "X-CSRFToken": csrf_token,
        "X-Bloks-Version-Id": "6309c8d03d8a3f47a1658ba38b304a3f837142ef5f637ebf1f8f52d4b802951e",
        "x-asbd-id": "129477",
        "cookie": cookie_str,
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-Friendly-Name": POLARIS_ACTION,
        **WEB_HEADERS,
    }

    variables = json.dumps({
        "shortcode": shortcode,
        "fetch_tagged_user_count": None,
        "hoisted_comment_id": None,
        "hoisted_reply_id": None,
    })

    body = urllib.parse.urlencode({
        "__d": "www",
        "__a": "1",
        "__s": session,
        "__hs": "20126.HYP:instagram_web_pkg.2.1...0",
        "__req": "b",
        "__ccg": "EXCELLENT",
        "__rev": "1019933358",
        "__hsi": "7436540909012459023",
        "__dyn": dynamic_flags,
        "__csr": client_session_rnd,
        "__user": "0",
        "__comet_req": "7",
        "libav": "0",
        "dpr": "2",
        "lsd": session_data,
        "jazoest": jazoest,
        "__spin_r": "1019933358",
        "__spin_b": "trunk",
        "__spin_t": timestamp,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": POLARIS_ACTION,
        "variables": variables,
        "server_timestamps": "true",
        "doc_id": "8845758582119845",
    }).encode()

    return headers, body


def _gql_media(shortcode: str, real_cookies: dict[str, str] | None = None) -> MediaResult:
    headers, body = _build_gql_request(shortcode, real_cookies)
    raw = _post(GRAPHQL_ENDPOINT, body, headers)
    resp = json.loads(raw)

    if resp.get("status") != "ok":
        raise ValueError(f"GQL status: {resp.get('status')}")

    node = (resp.get("data") or {}).get("xdt_shortcode_media")
    if not node:
        raise ValueError("xdt_shortcode_media missing")

    caption = ""
    edges = (node.get("edge_media_to_caption") or {}).get("edges", [])
    if edges:
        caption = (edges[0].get("node") or {}).get("text", "")

    result = MediaResult(caption=caption or None)
    typename = node.get("__typename", "")

    if typename in ("GraphVideo", "XDTGraphVideo", "GraphImage", "XDTGraphImage"):
        item = _parse_media(node)
        if item:
            result.items.append(item)
    elif typename in ("GraphSidecar", "XDTGraphSidecar"):
        for edge in (node.get("edge_sidecar_to_children") or {}).get("edges", []):
            item = _parse_media(edge.get("node") or {})
            if item:
                result.items.append(item)

    if not result.items:
        raise ValueError("no media in GQL response")
    return result


# ── method 2: embed page ───────────────────────────────────────────────────────

def _embed_media(shortcode: str, cookie_header: str | None = None, real_cookies: dict[str, str] | None = None) -> MediaResult:
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned"
    hdr = cookie_header or ("; ".join(f"{k}={v}" for k, v in real_cookies.items()) if real_cookies else None)
    headers = {**WEB_HEADERS, **({"Cookie": hdr} if hdr else {})}
    raw = _get(embed_url, headers).decode(errors="replace")

    m = CONTEXT_JSON_RE.search(raw)
    if not m:
        raise ValueError("contextJSON not found in embed page")

    context_str = json.loads(f'"{m.group(1)}"')
    ctx = json.loads(context_str)

    node = (ctx.get("gql_data") or {}).get("shortcode_media")
    if not node:
        raise ValueError("shortcode_media not found in contextJSON")

    caption = ""
    edges = (node.get("edge_media_to_caption") or {}).get("edges", [])
    if edges:
        caption = (edges[0].get("node") or {}).get("text", "")

    result = MediaResult(caption=caption or None)
    typename = node.get("__typename", "")

    if typename in ("GraphVideo", "XDTGraphVideo", "GraphImage", "XDTGraphImage"):
        item = _parse_media(node)
        if item:
            result.items.append(item)
    elif typename in ("GraphSidecar", "XDTGraphSidecar"):
        for edge in (node.get("edge_sidecar_to_children") or {}).get("edges", []):
            item = _parse_media(edge.get("node") or {})
            if item:
                result.items.append(item)

    if not result.items:
        raise ValueError("no media in embed response")
    return result


# ── method 3: IGram ────────────────────────────────────────────────────────────

def _igram_server_time() -> int:
    try:
        raw = _get(f"https://{IGRAM_API_BASE}/msec")
        data = json.loads(raw)
        return int(data["msec"] * 1000)
    except Exception:
        return int(time.time() * 1000)


def _igram_sign(partial: dict, ts: int) -> str:
    json_str = json.dumps(partial, sort_keys=True, separators=(",", ":"))
    data = json_str + str(ts)
    mac = hmac.new(IGRAM_HMAC_KEY, data.encode(), hashlib.sha256)
    return mac.hexdigest()


def _igram_payload(params: dict) -> bytes:
    now_ms = int(time.time() * 1000)
    server_ms = _igram_server_time()
    drift = server_ms - now_ms
    correction = drift if abs(drift) >= 60000 else 0
    ts = now_ms + correction

    partial = {"_sc": 0, "_ef": 0, "_df": 0, **params}
    sig = _igram_sign(partial, ts)

    final = {**partial, "ts": ts, "_ts": IGRAM_STATIC_TS, "_tsc": correction, "_sv": 2, "_s": sig}
    return json.dumps(final).encode()


def _get_cdn_url(igram_url: str) -> str:
    parsed = urllib.parse.urlparse(igram_url)
    params = urllib.parse.parse_qs(parsed.query)
    return params.get("uri", [""])[0] or igram_url


def _igram_media(shortcode: str) -> MediaResult:
    content_url = f"https://www.instagram.com/p/{shortcode}/"
    payload = _igram_payload({"target_url": content_url})

    headers = {
        "Content-Type": "application/json",
        **IGRAM_EXTRA_HEADERS,
    }
    raw = _post(f"https://{IGRAM_HOSTNAME}/api/convert", payload, headers)
    data = json.loads(raw)

    items_raw = data if isinstance(data, list) else [data]
    if isinstance(data, dict) and data.get("success") is False:
        raise ValueError("IGram: unavailable")

    result = MediaResult()
    for obj in items_raw:
        urls = obj.get("url", [])
        if not urls:
            continue
        url_obj = urls[0]
        cdn_url = _get_cdn_url(url_obj.get("url", ""))
        if not cdn_url:
            continue
        ext = url_obj.get("ext", "")
        if ext == "mp4":
            result.items.append(MediaItem(urls=[cdn_url], type="video"))
        else:
            result.items.append(MediaItem(urls=[cdn_url], type="photo"))

    if not result.items:
        raise ValueError("no media from IGram")
    return result


# ── stories: IGram story endpoint ─────────────────────────────────────────────

def _igram_story_media(story_url: str) -> MediaResult:
    payload = _igram_payload({"url": story_url})
    headers = {
        "Content-Type": "application/json",
        **IGRAM_EXTRA_HEADERS,
    }
    raw = _post(f"https://{IGRAM_HOSTNAME}/api/v1/instagram/story", payload, headers)
    data = json.loads(raw)

    result_list = data.get("result", [])
    if not result_list:
        raise ValueError("IGram story: no results")

    result = MediaResult()
    for item in result_list:
        video_versions = item.get("video_versions", [])
        image_versions = item.get("image_versions2", {}).get("candidates", [])
        if video_versions:
            best = max(video_versions, key=lambda v: v.get("width", 0))
            url = best.get("url")
            if url:
                result.items.append(MediaItem(urls=[url], type="video"))
        elif image_versions:
            best = max(image_versions, key=lambda v: v.get("width", 0))
            url = best.get("url")
            if url:
                result.items.append(MediaItem(urls=[url], type="photo"))

    if not result.items:
        raise ValueError("no media from IGram story")
    return result


# ── share URL redirect ──────────────────────────────────────────────────────────

def _resolve_share_url(share_url: str) -> str:
    req = urllib.request.Request(share_url, headers=WEB_HEADERS, method="GET")
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    with opener.open(req, timeout=15) as resp:
        return resp.url


# ── method 4: yt-dlp ──────────────────────────────────────────────────────────

def _ytdlp_media(shortcode: str, cookies_file: str | None = None) -> MediaResult:
    url = f"https://www.instagram.com/p/{shortcode}/"
    ydl_opts: dict = {"quiet": True, "no_warnings": True, "skip_download": True}
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = info.get("entries") or [info]
    result = MediaResult()
    for entry in entries:
        video_url = entry.get("url") or next(
            (f["url"] for f in reversed(entry.get("formats", [])) if f.get("url")), None
        )
        if video_url:
            result.items.append(MediaItem(urls=[video_url], type="video"))
        elif entry.get("thumbnail"):
            result.items.append(MediaItem(urls=[entry["thumbnail"]], type="photo"))

    if not result.items:
        raise ValueError("no media from yt-dlp")
    return result


# ── public entry point ─────────────────────────────────────────────────────────

def extract(url: str) -> MediaResult:
    from config import config

    # share URLs: resolve redirect first, then re-dispatch
    if SHARE_RE.search(url):
        try:
            resolved = _resolve_share_url(url)
            logger.info("Instagram share URL resolved to: %s", resolved)
            url = resolved
        except Exception as exc:
            raise RuntimeError(f"failed to resolve Instagram share URL: {exc}") from exc

    # stories: single IGram story endpoint, no fallback chain
    m_story = STORY_RE.search(url)
    if m_story:
        return _igram_story_media(url)

    m = SHORTCODE_RE.search(url)
    if not m:
        raise ValueError(f"could not extract Instagram shortcode from: {url}")
    shortcode = m.group(1)

    cookies_file = config.instagram_cookies_file
    cookie_hdr: str | None = None
    real_cookies: dict[str, str] | None = None
    if cookies_file and os.path.exists(cookies_file):
        try:
            cookie_hdr, real_cookies = _load_ig_cookies(cookies_file)
        except Exception as exc:
            logger.warning("Failed to load Instagram cookies: %s", exc)

    errors: list[str] = []
    for method_name, method in [
        ("GQL", lambda: _gql_media(shortcode, real_cookies)),
        ("embed", lambda: _embed_media(shortcode, real_cookies=real_cookies)),
        ("IGram", lambda: _igram_media(shortcode)),
        ("yt-dlp", lambda: _ytdlp_media(shortcode, cookies_file)),
    ]:
        try:
            result = method()
            logger.info("Instagram %s method succeeded for %s", method_name, shortcode)
            return result
        except Exception as exc:
            logger.warning("Instagram %s method failed: %s", method_name, exc)
            errors.append(f"{method_name}: {exc}")

    raise RuntimeError(f"all Instagram methods failed for {shortcode}: {'; '.join(errors)}")
