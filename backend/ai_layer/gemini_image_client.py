"""
Gemini native image generation (Nano Banana family) via REST generateContent.

Returns base64-encoded image bytes (no data URL prefix), identical contract to
ai_layer.image_client.generate_image. Never raises.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _b64_from_response(payload: Dict[str, Any]) -> Optional[str]:
    for cand in payload.get("candidates") or []:
        parts = (cand.get("content") or {}).get("parts") or []
        for part in parts:
            idata = part.get("inlineData") or part.get("inline_data")
            if idata:
                data = idata.get("data")
                if data:
                    return str(data)
    return None


def generate_image_gemini(
    prompt: str,
    api_key: str,
    model: str,
    timeout_s: float = 120.0,
) -> Optional[str]:
    """
    Call Gemini image model; return base64 image or None on failure.
    """
    if not api_key or not prompt:
        logger.debug("Gemini image: missing api_key or prompt.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    bodies = [
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": "16:9",
                    "imageSize": "1K",
                },
            },
        },
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        },
        {"contents": [{"parts": [{"text": prompt}]}]},
    ]

    last_http_err = ""
    for body in bodies:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace") if e.fp else ""
            last_http_err = f"{e.code} {err[:600]}"
            logger.warning("Gemini image HTTP error (will retry simpler body): %s", last_http_err)
            continue
        except Exception as e:
            logger.warning("Gemini image request failed: %s", type(e).__name__, exc_info=False)
            return None

        b64 = _b64_from_response(payload)
        if b64:
            logger.info("Gemini image generated (model=%s)", model)
            return b64
        logger.warning(
            "Gemini image: no inline image (keys=%s)",
            list(payload.keys()),
        )

    if last_http_err:
        logger.warning("Gemini image exhausted retries; last error: %s", last_http_err)
    return None
