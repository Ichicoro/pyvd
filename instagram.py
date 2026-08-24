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

    if not config.apify_token:
        logger.debug("APIFY_TOKEN not set — using legacy Instagram chain")
        return instagram_legacy.extract(url)

    try:
        apify_result = instagram_apify.extract(url)
    except Exception as exc:
        logger.warning("Instagram Apify method failed, falling back: %s", exc)
        return instagram_legacy.extract(url)

    # The actor serves photos at 640px and only ever returns a carousel's first
    # slide, so once a post turns out to be photos the legacy extractor is the
    # better source — full resolution, every slide. Videos stay on the actor.
    if apify_result.items and all(item.type == "photo" for item in apify_result.items):
        try:
            legacy_result = instagram_legacy.extract_fast(url)
        except Exception as exc:
            logger.warning("Legacy upgrade failed for photo post, keeping Apify media: %s", exc)
        else:
            logger.info(
                "Instagram photo post — using legacy extractor (%d item(s), full resolution)",
                len(legacy_result.items),
            )
            return legacy_result

    return apify_result
