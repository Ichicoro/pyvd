from __future__ import annotations
import re
import urllib.parse

URL_RE = re.compile(r"https?://\S+|(?<!\w)(?:www\.)?\w[\w.-]*/\S*")

_ALLOWED_PARAMS: dict[str, set[str]] = {
    "youtube.com": {"v", "t", "list", "index"},
    "youtu.be": {"t"},
}


def clean_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    bare = (parsed.hostname or "").removeprefix("www.")
    allowed = next((v for k, v in _ALLOWED_PARAMS.items() if bare == k or bare.endswith("." + k)), set())
    qs = {k: v for k, v in urllib.parse.parse_qsl(parsed.query) if k in allowed}
    cleaned = parsed._replace(query=urllib.parse.urlencode(qs), fragment="")
    return urllib.parse.urlunparse(cleaned)
