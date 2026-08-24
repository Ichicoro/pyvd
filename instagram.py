"""Instagram dispatcher: Apify actor first, legacy cookie-based chain as fallback."""
from __future__ import annotations
import logging

import instagram_apify
import instagram_legacy
from models import MediaResult

logger = logging.getLogger(__name__)

# re-exported for anything still poking at the old module's internals
SHORTCODE_RE = instagram_legacy.SHORTCODE_RE
STORY_RE = instagram_legacy.STORY_RE
SHARE_RE = instagram_legacy.SHARE_RE


def extract(url: str) -> MediaResult:
    from config import config

    if config.apify_token:
        try:
            return instagram_apify.extract(url)
        except Exception as exc:
            logger.warning("Instagram Apify method failed, falling back: %s", exc)
    else:
        logger.debug("APIFY_TOKEN not set — using legacy Instagram chain")

    return instagram_legacy.extract(url)
