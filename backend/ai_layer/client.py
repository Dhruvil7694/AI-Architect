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
    max_tokens: int = 1024,
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
            max_tokens=max_tokens,
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


try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore


def call_claude(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: float = 60.0,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> Optional[str]:
    """
    Call Anthropic Claude Messages API. Returns raw response text or None on failure.
    """
    if anthropic is None:
        logger.warning("anthropic package not installed; Claude calls will no-op.")
        return None

    from ai_layer.config import get_ai_config
    config = get_ai_config()
    api_key = config.claude_api_key
    if not api_key:
        logger.debug("CLAUDE_API_KEY not set; skipping Claude call.")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    start = time.monotonic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning("Claude API call failed after %.2fs: %s", elapsed, type(e).__name__, exc_info=False)
        return None

    elapsed = time.monotonic() - start
    if not response.content:
        logger.warning("Claude returned empty content.")
        return None

    text = response.content[0].text.strip()
    usage = getattr(response, "usage", None)
    if usage:
        logger.info(
            "Claude model=%s usage: input_tokens=%s output_tokens=%s (%.2fs)",
            model, getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None), elapsed,
        )
    return text


def call_llm(
    model_choice: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: float = 60.0,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> Optional[str]:
    """
    Unified LLM dispatcher. Routes to Claude or OpenAI based on model_choice.

    model_choice: "claude" → call_claude, "gpt-4o" → call_openai
    """
    if model_choice == "claude":
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        return call_claude(
            model=config.claude_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        return call_openai(
            model=model_choice,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=timeout_s,
            temperature=temperature,
            rate_limit_kind="interpreter",
            max_tokens=max_tokens,
        )


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
