"""Tests for floor plan image prompt builder (compressed + visual tokens)."""
import base64
import unittest


SAMPLE_LAYOUT = {
    "core": {"x": 10.0, "y": 0.0, "w": 4.5, "h": 12.0, "stairs": 2, "lifts": 2, "lobby": True},
    "corridor": {"x": 0.0, "y": 5.25, "w": 24.0, "h": 1.5},
    "units": [
        {
            "id": "U1",
            "type": "3BHK",
            "carpet_area_sqm": 92.5,
            "side": "north",
            "x": 0.0,
            "y": 0.0,
            "w": 10.0,
            "h": 6.0,
            "rooms": [
                {"type": "LIVING", "x": 1.0, "y": 3.0, "w": 5.5, "h": 4.0},
                {"type": "BEDROOM", "x": 1.0, "y": 0.5, "w": 4.0, "h": 3.5},
                {"type": "KITCHEN", "x": 6.5, "y": 3.0, "w": 3.5, "h": 3.0},
                {"type": "TOILET", "x": 6.5, "y": 0.5, "w": 2.0, "h": 2.5},
            ],
        },
        {
            "id": "U2",
            "type": "2BHK",
            "carpet_area_sqm": 65.0,
            "side": "south",
            "x": 14.0,
            "y": 0.0,
            "w": 10.0,
            "h": 6.0,
            "rooms": [
                {"type": "LIVING", "x": 15.0, "y": 3.0, "w": 4.5, "h": 3.5},
                {"type": "BEDROOM", "x": 15.0, "y": 0.5, "w": 3.5, "h": 3.0},
                {"type": "KITCHEN", "x": 19.5, "y": 3.0, "w": 3.0, "h": 2.5},
            ],
        },
    ],
}

SAMPLE_METRICS = {
    "footprintSqm": 288.0,
    "floorLengthM": 24.0,
    "floorDepthM": 12.0,
    "nUnitsPerFloor": 2,
    "nFloors": 16,
    "efficiencyPct": 92.3,
    "nLifts": 2,
    "nStairs": 2,
}


class TestBuildVisualTokens(unittest.TestCase):

    def test_contains_spatial_hints(self):
        from services.floor_plan_image_prompt import build_visual_tokens
        t = build_visual_tokens(SAMPLE_LAYOUT)
        assert "living" in t
        assert "x" in t or "m" in t
        assert "u1-" in t or "unit1" in t

    def test_no_xy_emits_flag(self):
        from services.floor_plan_image_prompt import build_visual_tokens
        t = build_visual_tokens({
            "units": [{"type": "2BHK", "rooms": [{"type": "living", "w": 4, "h": 3}]}],
        })
        assert "noXY" in t


class TestBuildArchitecturalPrompt(unittest.TestCase):

    def test_returns_nonempty_string(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert isinstance(result, str)
        assert len(result) > 40

    def test_concise_word_budget(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        n_words = len(result.split())
        assert n_words < 260, f"prompt too long: {n_words} words"

    def test_contains_key_terms(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert "24" in result
        assert "12" in result
        assert "CAD" in result or "cad" in result.lower()
        assert "no 3d" in result.lower()

    def test_design_brief_ignored_in_prompt(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(
            SAMPLE_LAYOUT, SAMPLE_METRICS, design_brief="Corner master with extra light"
        )
        assert "Corner master" not in result

    def test_no_presentation_content(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert "marble" not in result.lower()
        assert "sofa" not in result.lower()


class TestScoreGeneratedImages(unittest.TestCase):

    def test_picks_non_none(self):
        from services.floor_plan_image_prompt import score_generated_images
        raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2000
        b64 = base64.b64encode(raw).decode()
        best, meta = score_generated_images([None, b64, b64], SAMPLE_LAYOUT)
        assert best == b64
        assert meta.get("picked_index") in (1, 2)


if __name__ == "__main__":
    unittest.main()
