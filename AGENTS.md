# pyvd

Telegram bot + HTTP API that downloads media from social platforms and delivers it back to the user via Telegram.

## What it does

Send any supported URL to the bot in a Telegram chat. The bot downloads the media and sends it back as a video, photo, audio, or document. Albums (up to 10 items) are sent as media groups.

An HTTP API (port 5868) lets external clients trigger downloads via an API key.

## Supported platforms

| Platform | Extractor | Method |
|---|---|---|
| Twitter/X | `twitter.py` | fxtwitter API |
| Instagram | `instagram.py` | GQL → embed page → IGram → yt-dlp (fallback chain) |
| Bluesky | `bluesky.py` | AT Protocol public API |
| Tumblr | `tumblr.py` | Tumblr API |
| Threads | `threads.py` | embed page scrape (BeautifulSoup) |
| Pixiv | `pixiv.py` | Pixiv AJAX API (optional cookies for R-18) |
| YouTube / Shorts | — | yt-dlp |
| TikTok | — | yt-dlp (optional cookies) |

Instagram share URLs (`/share/...`) are resolved via redirect before extraction. Instagram stories use the IGram story endpoint directly.

Twitter URLs are replied to with a nitter URL (`nitter.py`).

## Architecture

```
main.py          entry point — wires Telegram bot + HTTP server
config.py        Config dataclass, loaded from env
handlers.py      Telegram command/message handlers + download_and_deliver()
server.py        aiohttp HTTP server on port 5868
extractors.py    Extractor registry — maps URL patterns to extractor modules
downloader.py    download_blocking() / download() — wraps yt-dlp and custom extractors
models.py        MediaItem, MediaResult dataclasses
imgutil.py       lossless photo re-compression for Telegram's 10MB sendPhoto cap
db.py            SQLite — stores user_id ↔ api_key
```

Telegram enforces a 10MB limit on `sendPhoto` uploads, independent of `MAX_FILE_SIZE_MB`. Before sending, oversized photos go through `imgutil.compress_photo`: lossless re-encode first (stripped metadata, optimized entropy coding), then JPEG quality reduction, then downscaling as a last resort — always as a photo, never falling back to a document except in the (practically unreachable) case where compression itself fails.

Downloads run in a thread (`asyncio.to_thread`) to avoid blocking the event loop. Each download gets a unique session directory under `DOWNLOAD_DIR`; it is deleted after delivery.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | yes | — | Telegram bot token |
| `TUMBLR_API_KEY` | no | — | Tumblr v2 API key |
| `ALLOWED_USER_IDS` | no | — | Comma-separated Telegram user IDs; if set, all other users are ignored |
| `INSTAGRAM_COOKIES_FILE` | no | — | Path to Netscape-format cookies for Instagram |
| `TIKTOK_COOKIES_FILE` | no | — | Path to Netscape-format cookies for TikTok |
| `PIXIV_COOKIES_FILE` | no | — | Path to Netscape-format cookies for Pixiv (needed for R-18 works) |
| `DOWNLOAD_DIR` | no | `/tmp/pyvd` | Temp directory for downloads |
| `MAX_FILE_SIZE_MB` | no | `50` | Files larger than this are skipped |
| `DB_PATH` | no | `pyvd.db` | SQLite database path |

Copy `.env.example` to `.env` and fill in at minimum `BOT_TOKEN`.

## Running

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit as needed
python main.py
```

## Docker

```bash
docker compose up -d
```

The compose file mounts a `db_data` volume at `/data` and sets `DB_PATH=/data/pyvd.db`. Port 5868 is exposed.

## HTTP API

The bot exposes a REST endpoint so external clients can trigger downloads.

**`POST /api/download`**

Headers:
- `Authorization: <api_key>`

Body (JSON):
```json
{ "url": "https://...", "wait": false, "as_document": false }
```
`wait` blocks the response until delivery finishes (default fire-and-forget). `as_document` skips photo compression and sends everything as an uncompressed document at original quality (default sends photos/videos normally, compressed to fit Telegram's caps as needed).

Responses:
- `200 OK` — media delivered to the user's Telegram chat
- `400` — missing/invalid request body
- `401` — missing Authorization header
- `403` — invalid or unauthorized API key
- `422` — unsupported URL or no media found
- `500` — download failed

Users obtain an API key via `/apikey` in Telegram and can rotate it with `/resetapikey`.

## Adding an extractor

1. Create `myplatform.py` with an `extract(url: str) -> MediaResult` function.
2. Add an `Extractor` entry to `EXTRACTORS` in `extractors.py` with a URL `pattern` and `extract=myplatform.extract`.
3. Optionally set `reply_url` (callable that returns a string caption for the reply) or `cookies_file`.

For platforms where yt-dlp works without a custom extractor, just add the `Extractor` with only a `pattern` — `extract` and `url_transform` default to `None` and yt-dlp handles it.

## Telegram commands

| Command | Description |
|---|---|
| `/apikey` | Show (or generate) the user's HTTP API key |
| `/resetapikey` | Rotate the API key; old key is immediately invalidated |

Any non-command message containing URLs is processed automatically.
