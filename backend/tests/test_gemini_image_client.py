"""Tests for Gemini native image client (Nano Banana REST)."""
import json
import unittest
from unittest.mock import patch, MagicMock


class TestGeminiImageClient(unittest.TestCase):
    def test_returns_b64_when_inline_data_present(self):
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"inlineData": {"mimeType": "image/png", "data": "QUJD"}},
                        ]
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_resp
        mock_cm.__exit__.return_value = False

        with patch("ai_layer.gemini_image_client.urllib.request.urlopen", return_value=mock_cm):
            from ai_layer.gemini_image_client import generate_image_gemini

            out = generate_image_gemini("prompt", "fake-key", "gemini-2.5-flash-image", timeout_s=5.0)
        assert out == "QUJD"

    def test_returns_none_without_key(self):
        from ai_layer.gemini_image_client import generate_image_gemini

        assert generate_image_gemini("x", "", "m", 5.0) is None


if __name__ == "__main__":
    unittest.main()
