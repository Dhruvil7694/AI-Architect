"""Tests for floor plan image prompt builder."""
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
            "rooms": [
                {"type": "LIVING", "w": 5.5, "h": 4.0, "position": "north-west"},
                {"type": "BEDROOM", "w": 4.0, "h": 3.5, "position": "north-east"},
                {"type": "KITCHEN", "w": 3.5, "h": 3.0, "position": "south-east"},
                {"type": "TOILET", "w": 2.0, "h": 2.5, "position": "south-west"},
            ],
        },
        {
            "id": "U2",
            "type": "2BHK",
            "carpet_area_sqm": 65.0,
            "side": "south",
            "rooms": [
                {"type": "LIVING", "w": 4.5, "h": 3.5, "position": "south-west"},
                {"type": "BEDROOM", "w": 3.5, "h": 3.0, "position": "south-east"},
                {"type": "KITCHEN", "w": 3.0, "h": 2.5, "position": "north-east"},
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


class TestBuildArchitecturalPrompt(unittest.TestCase):

    def test_returns_nonempty_string(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_key_architectural_terms(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert "black and white" in result.lower() or "line drawing" in result.lower()
        assert "24.0" in result  # floor length
        assert "12.0" in result  # floor depth
        assert "3BHK" in result
        assert "2BHK" in result

    def test_contains_scale_and_title(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS, segment="premium")
        assert "1:100" in result
        assert "Premium" in result


class TestBuildPresentationPrompt(unittest.TestCase):

    def test_returns_nonempty_string(self):
        from services.floor_plan_image_prompt import build_presentation_prompt
        result = build_presentation_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_furnishing_language(self):
        from services.floor_plan_image_prompt import build_presentation_prompt
        result = build_presentation_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS, segment="luxury")
        assert "marble" in result.lower() or "luxury" in result.lower()

    def test_budget_segment_uses_basic_finishes(self):
        from services.floor_plan_image_prompt import build_presentation_prompt
        result = build_presentation_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS, segment="budget")
        assert "laminate" in result.lower() or "basic" in result.lower()


if __name__ == "__main__":
    unittest.main()
