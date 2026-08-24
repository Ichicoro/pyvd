from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    download_dir: str
    max_file_size: int
    instagram_cookies_file: str | None
    apify_token: str | None
    apify_instagram_actor: str
    tiktok_cookies_file: str | None
    pixiv_cookies_file: str | None
    youtube_cookies_file: str | None
    tumblr_api_key: str | None
    db_path: str
    allowed_user_ids: frozenset[int] | None
    signal_service: str | None
    signal_phone_number: str | None
    signal_allowed_ids: frozenset[str] | None
    redlib_service: str | None

    @classmethod
    def load(cls) -> Config:
        token = os.environ.get("BOT_TOKEN")
        if not token:
            raise RuntimeError("BOT_TOKEN environment variable is required")
        raw_allowlist = os.environ.get("ALLOWED_USER_IDS", "").strip()
        allowed_user_ids: frozenset[int] | None = None
        if raw_allowlist:
            allowed_user_ids = frozenset(int(uid) for uid in raw_allowlist.split(",") if uid.strip())
        raw_signal_allowlist = os.environ.get("SIGNAL_ALLOWED_IDS", "").strip()
        signal_allowed_ids: frozenset[str] | None = None
        if raw_signal_allowlist:
            signal_allowed_ids = frozenset(uid.strip() for uid in raw_signal_allowlist.split(",") if uid.strip())
        return cls(
            bot_token=token,
            download_dir=os.environ.get("DOWNLOAD_DIR", "/tmp/pyvd"),
            max_file_size=int(os.environ.get("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024,
            instagram_cookies_file=os.environ.get("INSTAGRAM_COOKIES_FILE"),
            apify_token=os.environ.get("APIFY_TOKEN") or None,
            apify_instagram_actor=os.environ.get("APIFY_INSTAGRAM_ACTOR", "mGz1tKemfhpbQTkBv"),
            tiktok_cookies_file=os.environ.get("TIKTOK_COOKIES_FILE"),
            pixiv_cookies_file=os.environ.get("PIXIV_COOKIES_FILE"),
            youtube_cookies_file=os.environ.get("YOUTUBE_COOKIES_FILE"),
            tumblr_api_key=os.environ.get("TUMBLR_API_KEY"),
            db_path=os.environ.get("DB_PATH", "pyvd.db"),
            allowed_user_ids=allowed_user_ids,
            signal_service=os.environ.get("SIGNAL_SERVICE") or None,
            signal_phone_number=os.environ.get("SIGNAL_PHONE_NUMBER") or None,
            signal_allowed_ids=signal_allowed_ids,
            redlib_service=os.environ.get("REDLIB_SERVICE") or None,
        )


config = Config.load()
