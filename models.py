from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class MediaItem:
    urls: list[str]
    type: str  # "video", "photo", "audio"
    thumbnail_url: str | None = None
    width: int = 0
    height: int = 0


@dataclass
class MediaResult:
    items: list[MediaItem] = field(default_factory=list)
    caption: str | None = None
