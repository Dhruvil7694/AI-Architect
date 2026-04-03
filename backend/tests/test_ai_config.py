"""Tests for ai_layer/config.py — Claude + model toggle support."""

import os
import pytest
from unittest.mock import patch


def test_config_has_claude_api_key():
    """AIConfig exposes claude_api_key from environment."""
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test-123"}):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.claude_api_key == "sk-test-123"


def test_config_floor_plan_model_default():
    """Default floor plan AI model is 'claude'."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FLOOR_PLAN_AI_MODEL", None)
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_ai_model == "claude"


def test_config_floor_plan_model_env_override():
    """FLOOR_PLAN_AI_MODEL env var overrides default."""
    with patch.dict(os.environ, {"FLOOR_PLAN_AI_MODEL": "gpt-4o"}):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_ai_model == "gpt-4o"


def test_config_floor_plan_max_tokens_increased():
    """Floor plan max tokens default is 8192 (up from 4096)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_FLOOR_PLAN_MAX_TOKENS", None)
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_max_tokens == 8192


def test_config_floor_plan_timeout_increased():
    """Floor plan timeout default is 60s (up from 45s)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_FLOOR_PLAN_TIMEOUT_S", None)
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_timeout_s == 60.0
