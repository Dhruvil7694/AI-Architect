"""
ai_layer/config.py — Feature flags, model names, token limits.

All AI behavior is gated by env-based flags. API key from .env only (OPENAI_API_KEY).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Load .env from backend root so OPENAI_API_KEY is available even without Django
def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
        # backend/ai_layer/config.py -> backend/.env
        _backend_dir = Path(__file__).resolve().parent.parent
        load_dotenv(_backend_dir / ".env")
    except ImportError:
        pass


_load_dotenv_if_available()


@dataclass
class AIConfig:
    """Central config for the AI layer. Read from environment."""

    # Feature flags
    advisor_enabled: bool = False
    evaluator_enabled: bool = False
    constraint_interpreter_enabled: bool = False

    # Model names (env overrides)
    advisor_model: str = "gpt-4o-mini"
    evaluator_model: str = "gpt-4o-mini"
    interpreter_model: str = "gpt-4o-mini"

    # Token limits
    advisor_input_max_tokens: int = 500
    evaluator_input_max_tokens: int = 800
    interpreter_input_max_tokens: int = 4000

    # Timeouts (seconds)
    advisor_timeout_s: float = 10.0
    evaluator_timeout_s: float = 15.0
    interpreter_timeout_s: float = 30.0

    # Temperature (0 = deterministic)
    temperature: float = 0.0

    # API key from env only
    @property
    def api_key(self) -> Optional[str]:
        return os.environ.get("OPENAI_API_KEY")

    def has_api_key(self) -> bool:
        return bool(self.api_key)


def get_ai_config() -> AIConfig:
    """Build AIConfig from environment. Feature flags default off."""
    return AIConfig(
        advisor_enabled=_bool_env("AI_ADVISOR_ENABLED", False),
        evaluator_enabled=_bool_env("AI_EVALUATOR_ENABLED", False),
        constraint_interpreter_enabled=_bool_env("AI_CONSTRAINT_INTERPRETER_ENABLED", False),
        advisor_model=os.environ.get("OPENAI_ADVISOR_MODEL", "gpt-4o-mini"),
        evaluator_model=os.environ.get("OPENAI_EVALUATOR_MODEL", "gpt-4o-mini"),
        interpreter_model=os.environ.get("OPENAI_INTERPRETER_MODEL", "gpt-4o-mini"),
        advisor_input_max_tokens=_int_env("AI_ADVISOR_INPUT_MAX_TOKENS", 500),
        evaluator_input_max_tokens=_int_env("AI_EVALUATOR_INPUT_MAX_TOKENS", 800),
        interpreter_input_max_tokens=_int_env("AI_INTERPRETER_INPUT_MAX_TOKENS", 4000),
        advisor_timeout_s=_float_env("AI_ADVISOR_TIMEOUT_S", 10.0),
        evaluator_timeout_s=_float_env("AI_EVALUATOR_TIMEOUT_S", 15.0),
        interpreter_timeout_s=_float_env("AI_INTERPRETER_TIMEOUT_S", 30.0),
        temperature=_float_env("OPENAI_TEMPERATURE", 0.0),
    )


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
