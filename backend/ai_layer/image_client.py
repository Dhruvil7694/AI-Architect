"""
ai_layer/image_client.py — DALL-E 3 image generation wrapper.

Returns base64-encoded PNG or None on any failure. Never raises.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import openai
except ImportError:
    openai = None  # type: ignore

from ai_layer.config import get_ai_config


def generate_image(
    prompt: str,
    size: str = "1792x1024",
    quality: str = "hd",
    style: str = "natural",
) -> Optional[str]:
    """
    Call DALL-E 3 and return base64-encoded PNG.

    Returns None on failure (timeout, content policy, API error, missing key).
    Logs the error but does not raise.
    """
    config = get_ai_config()
    api_key = config.api_key
    if not api_key:
        logger.debug("OPENAI_API_KEY not set; skipping DALL-E call.")
        return None

    if openai is None:
        logger.warning("openai package not installed; DALL-E calls will no-op.")
        return None

    client = openai.OpenAI(api_key=api_key)
    timeout_s = config.dalle_timeout_s
    start = time.monotonic()

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            style=style,
            response_format="b64_json",
            n=1,
            timeout=timeout_s,
        )
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning(
            "DALL-E 3 call failed after %.2fs: %s", elapsed, type(e).__name__,
            exc_info=False,
        )
        return None

    elapsed = time.monotonic() - start

    if not response.data:
        logger.warning("DALL-E 3 returned empty data after %.2fs.", elapsed)
        return None

    b64 = response.data[0].b64_json
    if not b64:
        logger.warning("DALL-E 3 returned empty b64_json after %.2fs.", elapsed)
        return None

    logger.info(
        "DALL-E 3 image generated in %.2fs (size=%s, quality=%s, style=%s)",
        elapsed, size, quality, style,
    )
    return b64
