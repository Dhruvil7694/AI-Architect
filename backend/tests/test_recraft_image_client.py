"""Tests for Recraft image API client."""
import base64
import unittest
from unittest.mock import MagicMock, patch


class TestGenerateImageRecraft(unittest.TestCase):

    @patch("httpx.Client")
    def test_returns_b64_when_api_returns_b64_json(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"b64_json": base64.b64encode(b"ok").decode()}],
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from ai_layer.image_client import generate_image_recraft
        out = generate_image_recraft("plan prompt", "rk-test", model="recraftv4", size="16:9")

        assert out == base64.b64encode(b"ok").decode()
        call_kw = mock_client.post.call_args
        assert call_kw[0][0] == "https://external.api.recraft.ai/v1/images/generations"
        body = call_kw[1]["json"]
        assert body["model"] == "recraftv4"
        assert body["size"] == "16:9"
        assert body["response_format"] == "b64_json"
        assert "style" not in body
        assert "negative_prompt" not in body

    @patch("httpx.Client")
    def test_negative_prompt_only_for_v3(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"b64_json": base64.b64encode(b"z").decode()}]}
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from ai_layer.image_client import generate_image_recraft
        generate_image_recraft(
            "p", "key", model="recraftv3", negative_prompt="no blur",
        )
        body = mock_client.post.call_args[1]["json"]
        assert body["negative_prompt"] == "no blur"

    @patch("httpx.Client")
    def test_includes_style_for_v3_model(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"b64_json": base64.b64encode(b"x").decode()}]}
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        from ai_layer.image_client import generate_image_recraft
        generate_image_recraft(
            "p",
            "key",
            model="recraftv3_vector",
            style="vector_illustration",
        )
        body = mock_client.post.call_args[1]["json"]
        assert body["style"] == "vector_illustration"

    @patch("httpx.Client")
    def test_fetches_url_when_no_b64(self, mock_client_cls):
        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"data": [{"url": "https://cdn.example.com/x.png"}]}

        img_resp = MagicMock()
        img_resp.raise_for_status = MagicMock()
        img_resp.content = b"\x89PNG\r\n\x1a\n"

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None

        def post_side_effect(*args, **kwargs):
            return post_resp

        def get_side_effect(url, **kwargs):
            return img_resp

        mock_client.post.side_effect = post_side_effect
        mock_client.get.side_effect = get_side_effect
        mock_client_cls.return_value = mock_client

        from ai_layer.image_client import generate_image_recraft
        out = generate_image_recraft("p", "key")
        assert out is not None
        assert mock_client.get.called

    def test_returns_none_without_key(self):
        from ai_layer.image_client import generate_image_recraft
        assert generate_image_recraft("p", "") is None
        assert generate_image_recraft("p", "   ") is None


if __name__ == "__main__":
    unittest.main()
