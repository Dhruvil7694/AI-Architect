"""Tests for DALL-E config fields in AIConfig."""
import os
import unittest
from unittest.mock import patch


class TestDalleConfig(unittest.TestCase):

    def test_default_dalle_fields(self):
        from ai_layer.config import AIConfig
        c = AIConfig()
        assert c.floor_plan_image_enabled is True
        assert c.dalle_model == "dall-e-3"
        assert c.dalle_size == "1792x1024"
        assert c.dalle_quality == "hd"
        assert c.dalle_timeout_s == 30.0

    @patch.dict(os.environ, {"FLOOR_PLAN_IMAGE_ENABLED": "0"})
    def test_image_disabled_via_env(self):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_image_enabled is False

    @patch.dict(os.environ, {"DALLE_SIZE": "1024x1024"})
    def test_dalle_size_override(self):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.dalle_size == "1024x1024"


if __name__ == "__main__":
    unittest.main()
