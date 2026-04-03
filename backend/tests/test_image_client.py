"""Tests for DALL-E 3 image client."""
import unittest
from unittest.mock import patch, MagicMock


class TestGenerateImage(unittest.TestCase):
    """Test generate_image function."""

    @patch("ai_layer.image_client.openai")
    @patch("ai_layer.config.get_ai_config")
    def test_returns_base64_on_success(self, mock_config, mock_openai):
        mock_config.return_value.api_key = "sk-test"
        mock_config.return_value.dalle_timeout_s = 30.0
        mock_response = MagicMock()
        mock_response.data = [MagicMock(b64_json="iVBORw0KGgoAAAANS==")]
        mock_openai.OpenAI.return_value.images.generate.return_value = mock_response

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt", size="1792x1024", quality="hd", style="natural")

        assert result == "iVBORw0KGgoAAAANS=="
        mock_openai.OpenAI.return_value.images.generate.assert_called_once()

    @patch("ai_layer.image_client.openai")
    @patch("ai_layer.config.get_ai_config")
    def test_returns_none_on_api_error(self, mock_config, mock_openai):
        mock_config.return_value.api_key = "sk-test"
        mock_config.return_value.dalle_timeout_s = 30.0
        mock_openai.OpenAI.return_value.images.generate.side_effect = Exception("API error")

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt")

        assert result is None

    @patch("ai_layer.config.get_ai_config")
    def test_returns_none_when_no_api_key(self, mock_config):
        mock_config.return_value.api_key = None

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt")

        assert result is None

    @patch("ai_layer.image_client.openai")
    @patch("ai_layer.config.get_ai_config")
    def test_returns_none_on_empty_response(self, mock_config, mock_openai):
        mock_config.return_value.api_key = "sk-test"
        mock_config.return_value.dalle_timeout_s = 30.0
        mock_response = MagicMock()
        mock_response.data = []
        mock_openai.OpenAI.return_value.images.generate.return_value = mock_response

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt")

        assert result is None


if __name__ == "__main__":
    unittest.main()
