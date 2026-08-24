# pyvd

Telegram bot that downloads media from social platforms and sends it back to you. Also exposes an HTTP API on port 5868 for external clients.

Supports Twitter/X, Instagram, Bluesky, Tumblr, Threads, Pixiv, Reddit, RedGifs, YouTube/Shorts, and TikTok.

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
| `APIFY_TOKEN` | Apify API token — enables the Apify Instagram actor (primary Instagram path) |
| `APIFY_INSTAGRAM_ACTOR` | Apify actor id for Instagram (default `mGz1tKemfhpbQTkBv`, shahidirfan/Instagram-Video-Downloader) |
| `INSTAGRAM_COOKIES_FILE` | Path to Netscape-format cookies file for Instagram (legacy fallback chain) |
| `TIKTOK_COOKIES_FILE` | Path to Netscape-format cookies file for TikTok |
| `PIXIV_COOKIES_FILE` | Path to Netscape-format cookies file for Pixiv (required for R-18 works) |
| `YOUTUBE_COOKIES_FILE` | Path to Netscape-format cookies file for YouTube (optional, for age-gated/private content) |
| `MAX_FILE_SIZE_MB` | Skip files larger than this (default: `50`) |
| `SIGNAL_SERVICE` / `SIGNAL_PHONE_NUMBER` / `SIGNAL_ALLOWED_IDS` | Enables the Signal bot — see [Signal bot](#signal-bot-optional) below |
| `REDLIB_SERVICE` | `host:port` of a self-hosted [Redlib](https://github.com/redlib-org/redlib) instance for Reddit support (the bundled `docker-compose.yml` runs one at `redlib:8080`). Tried before the public instance fallback list, since public instances are frequently behind bot-challenge walls. |

#### Getting a cookies file

Instagram downloads go through the Apify actor when `APIFY_TOKEN` is set — posts, Reels, IGTV and stories, photos and videos alike. The old cookie-based chain stays as a fallback for anything the actor can't fetch.

Instagram (and some TikTok/YouTube content) requires a logged-in session to fetch reliably.

1. Install the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) browser extension.
2. Log into instagram.com (or tiktok.com / youtube.com) in that browser — make sure you're actually signed in, not just sitting on the login page.
3. Click the extension while on the site and export cookies for that domain to a file, e.g. `insta_cookies.txt`.
4. Point `INSTAGRAM_COOKIES_FILE` (or `TIKTOK_COOKIES_FILE` / `YOUTUBE_COOKIES_FILE`) at that file's path.

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

- **Reuse an existing host `signal-cli` account** (if you already have one registered/linked on the machine): set `SIGNAL_CLI_DATA_DIR` to its config dir (absolute path, typically `/home/youruser/.local/share/signal-cli`) and the sidecar bind-mounts it instead of using its own volume. The container runs signal-cli as uid 1000 and chowns the directory on startup, so this is cleanest when your host user is also uid 1000. Only one process may use an account at a time — once the sidecar is running, stop invoking `signal-cli` on the host against that account, or you'll corrupt the session state.
- **Link as a secondary device** (reuses your Signal account without touching the host install):
  ```bash
  curl "http://localhost:8080/v1/qrcodelink?device_name=pyvd"
  ```
  Open the returned URL in a browser to render the QR code, then scan it from Signal's "Link a device" screen on your phone. Note that `docker-compose.yml` doesn't publish the sidecar's port, so run this from inside the network — `docker compose exec signal-cli-rest-api curl -s "localhost:8080/v1/qrcodelink?device_name=pyvd"` — or add a temporary `ports:` mapping.
- **Register a new number**: follow the sidecar's [registration docs](https://github.com/bbernhard/signal-cli-rest-api#registration) (requires SMS/voice verification).

**2. Configure**

```
SIGNAL_SERVICE=signal-cli-rest-api:8080
SIGNAL_PHONE_NUMBER=+15551234567   # the number registered/linked above
SIGNAL_ALLOWED_IDS=+15551234567    # optional: comma-separated phone numbers/UUIDs allowed to DM the bot
```

Both `SIGNAL_SERVICE` and `SIGNAL_PHONE_NUMBER` must be set for the Signal bot to start; otherwise pyvd runs Telegram-only. `SIGNAL_ALLOWED_IDS` gates the *sender* everywhere — in DMs and in groups alike. Add the bot's number to a group to enable it there; members not on the allowlist are ignored. Leaving `SIGNAL_ALLOWED_IDS` unset lets anyone use the bot.

**Use UUIDs in `SIGNAL_ALLOWED_IDS`, not phone numbers.** Senders who have Signal's phone number privacy enabled arrive with no number attached, so a `+number` entry never matches and their messages are dropped silently — the bot simply doesn't respond. To find someone's UUID, have them DM the bot once, then list the contacts signal-cli has seen:

```bash
docker compose exec signal-cli-rest-api curl -s localhost:8080/v1/contacts/+15551234567 | jq '.[] | {uuid, username, name: .profile.given_name}'
```

Match on `username` or profile name and add that `uuid` to the allowlist.

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

Optional fields:

| Field | Description |
|---|---|
| `wait` | Wait for delivery before responding (default: `false`, fire-and-forget) |
| `as_document` | Send media as uncompressed documents at original quality instead of photos/videos (default: `false`) |

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
