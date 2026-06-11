# pyvd

Telegram bot that downloads media from social platforms and sends it back to you. Also exposes an HTTP API on port 5868 for external clients.

Supports Twitter/X, Instagram, Bluesky, Tumblr, Threads, YouTube/Shorts, and TikTok.

Send a URL → get back a video, photo, or album. That's it.

## Self-hosting with Docker Compose

**1. Get a bot token**

Create a bot via [@BotFather](https://t.me/BotFather) and copy the token.

**2. Configure**

Create `.env` and set at minimum:

```
BOT_TOKEN=your_token_here
```

Optional vars:

| Variable | Description |
|---|---|
| `TUMBLR_API_KEY` | Tumblr v2 API key (required for Tumblr support) |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs to whitelist |
| `INSTAGRAM_COOKIES_FILE` | Path to Netscape-format cookies file for Instagram |
| `TIKTOK_COOKIES_FILE` | Path to Netscape-format cookies file for TikTok |
| `MAX_FILE_SIZE_MB` | Skip files larger than this (default: `50`) |

**3. Run**

```bash
docker compose up -d
```

**4. Updates**

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

Data (SQLite DB) persists in a named volume `db_data`. Downloads are ephemeral and live in `/tmp/pyvd` inside the container.

## HTTP API

The bot generates an API key per user (stored in SQLite). External clients can trigger downloads by hitting port 5868 with their key.

For now, there's only one endpoint: `/api/download`, which accepts a JSON body:

```json
{ "url": "https://twitter.com/user/status/1234567890" }
```

and requires an `Authorization` header with the API key: `Authorization: your_api_key_here`

TODO: Rate limiting?

## Running without Docker

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cat "BOT_TOKEN=123545" > .env  # fill in BOT_TOKEN
python main.py
```

Requires Python 3.11+ and `ffmpeg` on the system.
