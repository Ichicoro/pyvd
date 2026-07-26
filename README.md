# pyvd

Telegram bot that downloads media from social platforms and sends it back to you. Also exposes an HTTP API on port 5868 for external clients.

Supports Twitter/X, Instagram, Bluesky, Tumblr, Threads, Pixiv, YouTube/Shorts, and TikTok.

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
| `PIXIV_COOKIES_FILE` | Path to Netscape-format cookies file for Pixiv (required for R-18 works) |
| `MAX_FILE_SIZE_MB` | Skip files larger than this (default: `50`) |
| `SIGNAL_SERVICE` / `SIGNAL_PHONE_NUMBER` / `SIGNAL_ALLOWED_IDS` | Enables the Signal bot — see [Signal bot](#signal-bot-optional) below |

#### Getting a cookies file

Instagram (and some TikTok content) requires a logged-in session to fetch reliably.

1. Install the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) browser extension.
2. Log into instagram.com (or tiktok.com) in that browser — make sure you're actually signed in, not just sitting on the login page.
3. Click the extension while on the site and export cookies for that domain to a file, e.g. `insta_cookies.txt`.
4. Point `INSTAGRAM_COOKIES_FILE` (or `TIKTOK_COOKIES_FILE`) at that file's path.

For Instagram specifically, double-check the exported file contains a `sessionid` cookie for `.instagram.com` — without it you're not actually authenticated, and downloads will silently behave as if logged out. Cookies expire periodically; re-export when downloads start failing.

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

## Signal bot (optional)

pyvd can also run as a Signal bot alongside the Telegram bot, watching DMs and group messages for supported URLs. This uses [`signalbot`](https://pypi.org/project/signalbot/), which talks to a [`signal-cli-rest-api`](https://github.com/bbernhard/signal-cli-rest-api) sidecar rather than Signal's servers directly — the sidecar is already wired up in `docker-compose.yml`.

**1. Register or link a phone number**

The sidecar container needs a registered Signal account before the bot can use it. With the stack running (`docker compose up -d`), either:

- **Link as a secondary device** (easiest — reuses your existing Signal account):
  ```bash
  curl "http://localhost:8080/v1/qrcodelink?device_name=pyvd"
  ```
  Open the returned URL in a browser to render the QR code, then scan it from Signal's "Link a device" screen on your phone.
- **Register a new number**: follow the sidecar's [registration docs](https://github.com/bbernhard/signal-cli-rest-api#registration) (requires SMS/voice verification).

**2. Configure**

```
SIGNAL_SERVICE=signal-cli-rest-api:8080
SIGNAL_PHONE_NUMBER=+15551234567   # the number registered/linked above
SIGNAL_ALLOWED_IDS=+15551234567    # optional: comma-separated phone numbers/UUIDs allowed to DM the bot
```

Both `SIGNAL_SERVICE` and `SIGNAL_PHONE_NUMBER` must be set for the Signal bot to start; otherwise pyvd runs Telegram-only. `SIGNAL_ALLOWED_IDS` gates direct messages — group messages are accepted from any member, so add the bot's number to a group to enable it there.

**3. Restart**

```bash
docker compose up -d
```

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
