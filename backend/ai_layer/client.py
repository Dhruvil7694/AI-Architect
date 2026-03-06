"""
ai_layer/client.py — Shared OpenAI client: timeout, retries, rate limit, logging.

API key from environment only (OPENAI_API_KEY). No keys in code or logs.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Rate limit: simple in-memory window (per process). Plan: 60/min Advisor+Evaluator, 10/min Interpreter.
_rate_limit_advisor_count = 0
_rate_limit_advisor_reset = 0.0
_rate_limit_interpreter_count = 0
_rate_limit_interpreter_reset = 0.0
_RATE_LIMIT_ADVISOR_PER_MIN = 60
_RATE_LIMIT_INTERPRETER_PER_MIN = 10


def _check_rate_limit(kind: str) -> bool:
    """Return True if call is allowed, False if rate limited."""
    global _rate_limit_advisor_count, _rate_limit_advisor_reset
    global _rate_limit_interpreter_count, _rate_limit_interpreter_reset
    now = time.monotonic()
    if kind == "interpreter":
        if now > _rate_limit_interpreter_reset:
            _rate_limit_interpreter_reset = now + 60
            _rate_limit_interpreter_count = 0
        if _rate_limit_interpreter_count >= _RATE_LIMIT_INTERPRETER_PER_MIN:
            return False
        _rate_limit_interpreter_count += 1
    else:
        if now > _rate_limit_advisor_reset:
            _rate_limit_advisor_reset = now + 60
            _rate_limit_advisor_count = 0
        if _rate_limit_advisor_count >= _RATE_LIMIT_ADVISOR_PER_MIN:
            return False
        _rate_limit_advisor_count += 1
    return True


def call_openai(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: float = 15.0,
    temperature: float = 0.0,
    rate_limit_kind: str = "advisor",
) -> Optional[str]:
    """
    Call OpenAI Chat Completions with JSON response. Returns raw response text or None on failure.

    On timeout, API error, or rate limit: returns None. Logs model and token usage only (no bodies).
    """
    try:
        import openai
    except ImportError:
        logger.warning("openai package not installed; AI layer calls will no-op.")
        return None

    from ai_layer.config import get_ai_config
    config = get_ai_config()
    api_key = config.api_key
    if not api_key:
        logger.debug("OPENAI_API_KEY not set; skipping AI call.")
        return None

    if not _check_rate_limit(rate_limit_kind):
        logger.warning("AI rate limit exceeded for %s; skipping call.", rate_limit_kind)
        return None

    client = openai.OpenAI(api_key=api_key)
    start = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=1024,
            response_format={"type": "json_object"} if _supports_json_mode() else None,
            timeout=timeout_s,
        )
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning("OpenAI API call failed after %.2fs: %s", elapsed, type(e).__name__, exc_info=False)
        return None

    elapsed = time.monotonic() - start
    choice = response.choices[0] if response.choices else None
    if not choice or not choice.message or not choice.message.content:
        logger.warning("OpenAI returned empty content.")
        return None

    usage = getattr(response, "usage", None)
    if usage:
        logger.info("OpenAI model=%s usage: prompt_tokens=%s completion_tokens=%s total=%s (%.2fs)",
                    model, getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None),
                    getattr(usage, "total_tokens", None), elapsed)
    return choice.message.content.strip()


def parse_json_response(raw: Optional[str]) -> Optional[dict[str, Any]]:
    """
    Parse response as single JSON object. If any non-JSON text or invalid JSON, return None.
    No attempt to strip markdown or extract JSON from mixed content.
    """
    if not raw or not raw.strip():
        return None
    stripped = raw.strip()
    # Strict: must be a single JSON object from start to end
    if stripped.startswith("```") or "Here is" in stripped[:50].lower():
        return None
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _supports_json_mode() -> bool:
    """Assume OpenAI client supports response_format when available."""
    try:
        import openai
        # Modern openai package supports it
        return True
    except Exception:
        return False
