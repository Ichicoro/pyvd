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
    tiktok_cookies_file: str | None
    tumblr_api_key: str | None

    @classmethod
    def load(cls) -> Config:
        token = os.environ.get("BOT_TOKEN")
        if not token:
            raise RuntimeError("BOT_TOKEN environment variable is required")
        return cls(
            bot_token=token,
            download_dir=os.environ.get("DOWNLOAD_DIR", "/tmp/pygovd"),
            max_file_size=int(os.environ.get("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024,
            tiktok_cookies_file=os.environ.get("TIKTOK_COOKIES_FILE"),
            tumblr_api_key=os.environ.get("TUMBLR_API_KEY"),
        )


config = Config.load()
