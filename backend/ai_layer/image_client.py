"""
ai_layer/image_client.py — Image generation wrappers (DALL-E 3, Imagen, Recraft, etc.).

Returns base64-encoded PNG or None on any failure. Never raises.
"""
from __future__ import annotations

import base64
import binascii
import logging
import time
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)

try:
    import openai
except ImportError:
    openai = None  # type: ignore

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
    from ai_layer.config import get_ai_config

    config = get_ai_config()
    api_key = config.api_key
    if not api_key:
        logger.debug("OPENAI_API_KEY not set; skipping DALL-E call.")
        return None

    if openai is None:
        logger.warning("openai package not installed; DALL-E calls will no-op.")
        return None

    client = openai.OpenAI(api_key=api_key)
    timeout_s = getattr(config, "dalle_timeout_s", 30.0)
    start = time.monotonic()

    try:
        response = client.images.generate(
            model=getattr(config, "dalle_model", "dall-e-3"),
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


def generate_image_gemini(
    prompt: str,
    api_key: str,
    model: str = "imagen-4.0-generate-001",
    timeout_s: float = 120.0,
) -> Optional[str]:
    """
    Generate an image via Google Imagen 4 using the google-genai SDK.

    Returns base64-encoded PNG or None on failure. Never raises.
    Available models:
      "imagen-4.0-generate-001"       — Imagen 4 standard (best quality)
      "imagen-4.0-fast-generate-001"  — Imagen 4 Fast (cheaper, faster)
    """
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("google-genai not installed; Imagen calls will no-op.")
        return None

    import base64
    start = time.monotonic()
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_images(
            model=model,
            prompt=prompt,
            config=genai_types.GenerateImagesConfig(
                number_of_images=1,
                safety_filter_level="block_only_high",
                person_generation="dont_allow",
                output_mime_type="image/png",
            ),
        )
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning(
            "Imagen call failed after %.2fs: %s — %s", elapsed, type(e).__name__, e,
            exc_info=False,
        )
        return None

    elapsed = time.monotonic() - start

    if not response.generated_images:
        logger.warning("Imagen returned no images after %.2fs.", elapsed)
        return None

    raw = response.generated_images[0].image.image_bytes
    if not raw:
        logger.warning("Imagen: empty image_bytes after %.2fs.", elapsed)
        return None

    logger.info("Imagen image generated in %.2fs (model=%s)", elapsed, model)
    return base64.b64encode(raw).decode()


RECRAFT_IMAGES_URL = "https://external.api.recraft.ai/v1/images/generations"


def _parse_recraft_response(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Return (b64_json_or_none, url_or_none) for first image."""
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None, None
    first = data[0]
    if not isinstance(first, dict):
        return None, None
    b64 = first.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        return b64.strip(), None
    url = first.get("url")
    if isinstance(url, str) and url.strip():
        return None, url.strip()
    return None, None


def generate_image_recraft(
    prompt: str,
    api_key: str,
    *,
    model: str = "recraftv4",
    size: str = "16:9",
    n: int = 1,
    style: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    timeout_s: float = 120.0,
) -> Optional[str]:
    """
    Recraft external API — https://external.api.recraft.ai/v1/images/generations

    Prefers response_format=b64_json; falls back to downloading url if needed.
    ``style`` and ``negative_prompt`` are sent only for recraftv2/recraftv3 models
    (Recraft compatibility table). V4 relies on the main ``prompt`` for constraints.
    """
    key = (api_key or "").strip()
    if not key:
        logger.debug("RECRAFT_API_KEY empty; skipping Recraft call.")
        return None

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed; Recraft calls will no-op.")
        return None

    body: Dict[str, Any] = {
        "prompt": prompt[:8000],
        "model": model,
        "size": size,
        "n": min(max(int(n), 1), 6),
        "response_format": "b64_json",
    }
    mlow = model.lower()
    # Per Recraft API compatibility table: style + negative_prompt apply to V2/V3
    # (V4 examples use prompt + model only; extras may be ignored or rejected.)
    if negative_prompt and ("recraftv2" in mlow or "recraftv3" in mlow):
        body["negative_prompt"] = negative_prompt[:2000]
    if style and ("recraftv2" in mlow or "recraftv3" in mlow):
        body["style"] = style

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(RECRAFT_IMAGES_URL, headers=headers, json=body)
            if resp.status_code >= 400:
                snippet = (resp.text or "")[:500]
                logger.warning(
                    "Recraft HTTP %s: %s",
                    resp.status_code,
                    snippet,
                )
                return None
            payload = resp.json()
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning(
            "Recraft request failed after %.2fs: %s",
            elapsed,
            type(e).__name__,
            exc_info=False,
        )
        return None

    elapsed = time.monotonic() - start
    b64, url = _parse_recraft_response(payload)
    if b64:
        try:
            base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            logger.warning("Recraft returned invalid base64 after %.2fs.", elapsed)
            return None
        logger.info(
            "Recraft image generated in %.2fs (model=%s, size=%s)",
            elapsed,
            model,
            size,
        )
        return b64

    if url:
        try:
            with httpx.Client(timeout=60.0) as dl:
                img = dl.get(url)
                img.raise_for_status()
                out = base64.b64encode(img.content).decode()
                logger.info(
                    "Recraft image downloaded in %.2fs (model=%s, url)",
                    time.monotonic() - start,
                    model,
                )
                return out
        except Exception as e:
            logger.warning("Recraft image URL fetch failed: %s", type(e).__name__, exc_info=False)
            return None

    logger.warning("Recraft response had no b64_json or url after %.2fs.", elapsed)
    return None
