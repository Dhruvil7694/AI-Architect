"""Tests for ai_layer/client.py — Claude client + unified call_llm."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_call_claude_returns_none_without_key():
    """call_claude returns None when CLAUDE_API_KEY is not set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CLAUDE_API_KEY", None)
        from ai_layer.client import call_claude
        result = call_claude(
            model="claude-sonnet-4-6",
            system_prompt="test",
            user_prompt="test",
        )
        assert result is None


def test_call_claude_returns_text_on_success():
    """call_claude returns message text when API call succeeds."""
    mock_client_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"units": []}')]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_client_instance.messages.create.return_value = mock_response

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client_instance

    with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test"}):
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            from importlib import reload
            import ai_layer.client as client_mod
            reload(client_mod)
            result = client_mod.call_claude(
                model="claude-sonnet-4-6",
                system_prompt="You are an architect",
                user_prompt="Generate layout",
                max_tokens=8192,
            )
            assert result == '{"units": []}'


def test_call_llm_routes_to_claude():
    """call_llm with model='claude' routes to call_claude."""
    import ai_layer.client as client_mod
    with patch.object(client_mod, "call_claude", return_value='{"test": true}') as mock_claude:
        result = client_mod.call_llm(
            model_choice="claude",
            system_prompt="sys",
            user_prompt="usr",
        )
        mock_claude.assert_called_once()
        assert result == '{"test": true}'


def test_call_llm_routes_to_openai():
    """call_llm with model='gpt-4o' routes to call_openai."""
    import ai_layer.client as client_mod
    with patch.object(client_mod, "call_openai", return_value='{"test": true}') as mock_openai:
        result = client_mod.call_llm(
            model_choice="gpt-4o",
            system_prompt="sys",
            user_prompt="usr",
        )
        mock_openai.assert_called_once()
        assert result == '{"test": true}'
