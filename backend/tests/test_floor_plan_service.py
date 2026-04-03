"""Tests for the refactored AI floor plan service."""

import json
import pytest
from unittest.mock import patch


# A valid AI response with complete room-level layout for 2 units
MOCK_AI_RESPONSE = json.dumps({
    "core": {
        "x": 10.0, "y": 0.0, "w": 4.5, "h": 12.0,
        "stairs": [{"x": 10.23, "y": 6.0, "w": 1.2, "h": 3.5}],
        "lifts": [{"x": 10.23, "y": 0.23, "w": 1.85, "h": 1.8}],
        "lobby": {"x": 10.0, "y": 4.75, "w": 4.5, "h": 2.0}
    },
    "corridor": {"x": 0.0, "y": 5.25, "w": 24.0, "h": 1.5},
    "units": [
        {
            "id": "U1", "type": "2BHK", "side": "south",
            "x": 0.0, "y": 0.0, "w": 10.0, "h": 5.25,
            "rooms": [
                {"id": "U1_R1", "type": "foyer", "x": 0.0, "y": 0.0, "w": 2.0, "h": 1.5},
                {"id": "U1_R2", "type": "living", "x": 2.0, "y": 0.0, "w": 4.0, "h": 3.2},
                {"id": "U1_R3", "type": "kitchen", "x": 6.0, "y": 0.0, "w": 3.5, "h": 3.2},
                {"id": "U1_R4", "type": "utility", "x": 6.0, "y": 3.2, "w": 2.0, "h": 2.05},
                {"id": "U1_R5", "type": "bedroom", "x": 0.0, "y": 1.5, "w": 4.5, "h": 3.75},
                {"id": "U1_R6", "type": "bathroom", "x": 4.5, "y": 3.2, "w": 1.5, "h": 2.05},
                {"id": "U1_R7", "type": "bedroom2", "x": 8.0, "y": 3.2, "w": 2.0, "h": 2.05},
                {"id": "U1_R8", "type": "toilet", "x": 9.5, "y": 0.0, "w": 1.5, "h": 1.8}
            ],
            "balcony": {"x": 0.0, "y": -1.5, "w": 10.0, "h": 1.5}
        },
        {
            "id": "U2", "type": "3BHK", "side": "north",
            "x": 0.0, "y": 6.75, "w": 10.0, "h": 5.25,
            "rooms": [
                {"id": "U2_R1", "type": "foyer", "x": 0.0, "y": 6.75, "w": 2.0, "h": 1.5},
                {"id": "U2_R2", "type": "living", "x": 2.0, "y": 6.75, "w": 3.5, "h": 3.0},
                {"id": "U2_R3", "type": "dining", "x": 5.5, "y": 6.75, "w": 2.5, "h": 3.0},
                {"id": "U2_R4", "type": "kitchen", "x": 8.0, "y": 6.75, "w": 2.0, "h": 3.0},
                {"id": "U2_R5", "type": "utility", "x": 8.0, "y": 9.75, "w": 2.0, "h": 2.25},
                {"id": "U2_R6", "type": "bedroom", "x": 0.0, "y": 8.25, "w": 4.0, "h": 3.75},
                {"id": "U2_R7", "type": "bathroom", "x": 4.0, "y": 9.75, "w": 2.0, "h": 2.25},
                {"id": "U2_R8", "type": "bedroom2", "x": 0.0, "y": 9.75, "w": 3.5, "h": 2.25},
                {"id": "U2_R9", "type": "bathroom", "x": 3.5, "y": 9.75, "w": 1.5, "h": 2.25},
                {"id": "U2_R10", "type": "bedroom2", "x": 6.0, "y": 9.75, "w": 2.0, "h": 2.25},
                {"id": "U2_R11", "type": "toilet", "x": 6.0, "y": 6.75, "w": 2.0, "h": 1.8}
            ],
            "balcony": {"x": 0.0, "y": 12.0, "w": 10.0, "h": 1.5}
        }
    ],
    "design_notes": "Test layout"
})


def test_service_uses_call_llm_not_call_openai():
    """The service should use call_llm (model-agnostic), not call_openai directly."""
    with patch("services.ai_floor_plan_service.call_llm", return_value=MOCK_AI_RESPONSE) as mock_llm:
        with patch("services.ai_floor_plan_service.call_openai", side_effect=AssertionError("Should not be called")):
            with patch(
                "services.ai_floor_plan_service._generate_images_for_model",
                return_value=(None, {"n_generated": 0, "picked_index": None}),
            ):
                from services.ai_floor_plan_service import generate_ai_floor_plan
                result = generate_ai_floor_plan(
                    footprint_geojson={"type": "Polygon", "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]},
                    n_floors=12,
                    building_height_m=36.0,
                    units_per_core=4,
                    segment="mid",
                )
                assert mock_llm.called
                assert result["status"] == "ok"


def test_service_preserves_ai_rooms():
    """The service should keep AI-generated rooms, not replace them with deterministic ones."""
    with patch("services.ai_floor_plan_service.call_llm", return_value=MOCK_AI_RESPONSE):
        with patch(
            "services.ai_floor_plan_service._generate_images_for_model",
            return_value=(None, {"n_generated": 0, "picked_index": None}),
        ):
            from services.ai_floor_plan_service import generate_ai_floor_plan
            result = generate_ai_floor_plan(
                footprint_geojson={"type": "Polygon", "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]},
                n_floors=12,
                building_height_m=36.0,
                units_per_core=4,
                segment="mid",
            )
            # The result should have rooms in the layout
            features = result.get("layout", {}).get("features", [])
            room_features = [f for f in features if f.get("properties", {}).get("layer") == "room"]
            assert len(room_features) > 0, "AI-generated rooms should appear in output"
