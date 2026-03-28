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

    # Floor plan generation
    floor_plan_model: str = "gpt-4o"
    floor_plan_timeout_s: float = 45.0
    floor_plan_max_tokens: int = 4096

    # Plot exploration scenario generation
    exploration_model: str = "gpt-4o"
    exploration_timeout_s: float = 30.0
    exploration_max_tokens: int = 2048

    # AI site plan generation
    site_plan_model: str = "gpt-4o"
    site_plan_timeout_s: float = 45.0
    site_plan_max_tokens: int = 4096
    site_plan_max_retries: int = 5

    # Claude / model toggle
    floor_plan_ai_model: str = "claude"  # "claude" | "gpt-4o"
    claude_model: str = "claude-sonnet-4-6"
    claude_timeout_s: float = 60.0
    claude_max_tokens: int = 8192

    # Floor plan preview image (HF text-to-image; separate from layout pipeline)
    hf_image_model: str = "black-forest-labs/FLUX.1-schnell"
    hf_image_timeout_s: float = 120.0

    # DALL-E 3 floor plan image generation
    floor_plan_image_enabled: bool = True
    dalle_model: str = "dall-e-3"
    dalle_size: str = "1792x1024"
    dalle_quality: str = "hd"
    dalle_timeout_s: float = 30.0

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

    @property
    def claude_api_key(self) -> Optional[str]:
        return os.environ.get("CLAUDE_API_KEY")

    def has_claude_api_key(self) -> bool:
        return bool(self.claude_api_key)

    @property
    def huggingface_api_token(self) -> Optional[str]:
        return (
            os.environ.get("HUGGINGFACE_API_TOKEN")
            or os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        )


def get_ai_config() -> AIConfig:
    """
    Build AIConfig from environment.

    Feature flags default to True when OPENAI_API_KEY is set (auto-enable on
    key presence).  Explicit env vars still override: set AI_ADVISOR_ENABLED=0
    to disable even when the key is present.
    """
    key_present = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    default_on = key_present  # auto-enable all features when key is present
    return AIConfig(
        advisor_enabled=_bool_env("AI_ADVISOR_ENABLED", default_on),
        evaluator_enabled=_bool_env("AI_EVALUATOR_ENABLED", default_on),
        constraint_interpreter_enabled=_bool_env("AI_CONSTRAINT_INTERPRETER_ENABLED", default_on),
        advisor_model=os.environ.get("OPENAI_ADVISOR_MODEL", "gpt-4o-mini"),
        evaluator_model=os.environ.get("OPENAI_EVALUATOR_MODEL", "gpt-4o-mini"),
        interpreter_model=os.environ.get("OPENAI_INTERPRETER_MODEL", "gpt-4o-mini"),
        floor_plan_model=os.environ.get("OPENAI_FLOOR_PLAN_MODEL", "gpt-4o"),
        floor_plan_timeout_s=_float_env("AI_FLOOR_PLAN_TIMEOUT_S", 60.0),
        floor_plan_max_tokens=_int_env("AI_FLOOR_PLAN_MAX_TOKENS", 8192),
        exploration_model=os.environ.get("OPENAI_EXPLORATION_MODEL", "gpt-4o"),
        exploration_timeout_s=_float_env("AI_EXPLORATION_TIMEOUT_S", 30.0),
        exploration_max_tokens=_int_env("AI_EXPLORATION_MAX_TOKENS", 2048),
        site_plan_model=os.environ.get("OPENAI_SITE_PLAN_MODEL", "gpt-4o"),
        site_plan_timeout_s=_float_env("AI_SITE_PLAN_TIMEOUT_S", 45.0),
        site_plan_max_tokens=_int_env("AI_SITE_PLAN_MAX_TOKENS", 4096),
        site_plan_max_retries=_int_env("AI_SITE_PLAN_MAX_RETRIES", 5),
        advisor_input_max_tokens=_int_env("AI_ADVISOR_INPUT_MAX_TOKENS", 500),
        evaluator_input_max_tokens=_int_env("AI_EVALUATOR_INPUT_MAX_TOKENS", 800),
        interpreter_input_max_tokens=_int_env("AI_INTERPRETER_INPUT_MAX_TOKENS", 4000),
        advisor_timeout_s=_float_env("AI_ADVISOR_TIMEOUT_S", 10.0),
        evaluator_timeout_s=_float_env("AI_EVALUATOR_TIMEOUT_S", 15.0),
        interpreter_timeout_s=_float_env("AI_INTERPRETER_TIMEOUT_S", 30.0),
        temperature=_float_env("OPENAI_TEMPERATURE", 0.0),
        floor_plan_ai_model=os.environ.get("FLOOR_PLAN_AI_MODEL", "claude"),
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        claude_timeout_s=_float_env("CLAUDE_TIMEOUT_S", 60.0),
        claude_max_tokens=_int_env("CLAUDE_MAX_TOKENS", 8192),
        hf_image_model=os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell"),
        hf_image_timeout_s=_float_env("HF_IMAGE_TIMEOUT_S", 120.0),
        floor_plan_image_enabled=_bool_env("FLOOR_PLAN_IMAGE_ENABLED", True),
        dalle_model=os.environ.get("DALLE_MODEL", "dall-e-3"),
        dalle_size=os.environ.get("DALLE_SIZE", "1792x1024"),
        dalle_quality=os.environ.get("DALLE_QUALITY", "hd"),
        dalle_timeout_s=_float_env("DALLE_TIMEOUT_S", 30.0),
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
