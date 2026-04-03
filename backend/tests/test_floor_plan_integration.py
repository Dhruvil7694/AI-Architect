"""Integration test: full pipeline from footprint -> GeoJSON + SVG."""

import json
import pytest
from unittest.mock import patch


MOCK_AI_LAYOUT = {
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
                {"id": "U1_R6", "type": "bathroom", "x": 4.5, "y": 3.2, "w": 2.0, "h": 2.05},
                {"id": "U1_R7", "type": "bedroom2", "x": 8.0, "y": 3.2, "w": 3.0, "h": 2.05},
                {"id": "U1_R8", "type": "toilet", "x": 8.0, "y": 0.0, "w": 1.5, "h": 1.8},
            ],
            "balcony": {"x": 0.0, "y": -1.5, "w": 10.0, "h": 1.5}
        },
        {
            "id": "U2", "type": "2BHK", "side": "north",
            "x": 0.0, "y": 6.75, "w": 10.0, "h": 5.25,
            "rooms": [
                {"id": "U2_R1", "type": "foyer", "x": 0.0, "y": 10.5, "w": 2.0, "h": 1.5},
                {"id": "U2_R2", "type": "living", "x": 2.0, "y": 8.8, "w": 4.0, "h": 3.2},
                {"id": "U2_R3", "type": "kitchen", "x": 6.0, "y": 8.8, "w": 3.5, "h": 3.2},
                {"id": "U2_R4", "type": "utility", "x": 6.0, "y": 6.75, "w": 2.0, "h": 2.05},
                {"id": "U2_R5", "type": "bedroom", "x": 0.0, "y": 6.75, "w": 4.5, "h": 3.75},
                {"id": "U2_R6", "type": "bathroom", "x": 4.5, "y": 6.75, "w": 2.0, "h": 2.05},
                {"id": "U2_R7", "type": "bedroom2", "x": 8.0, "y": 6.75, "w": 3.0, "h": 2.05},
                {"id": "U2_R8", "type": "toilet", "x": 8.0, "y": 10.2, "w": 1.5, "h": 1.8},
            ],
            "balcony": {"x": 0.0, "y": 12.0, "w": 10.0, "h": 1.5}
        },
    ],
    "design_notes": "Integration test layout"
}


def test_full_pipeline_produces_valid_output():
    """End-to-end: footprint -> AI mock -> GeoJSON + SVG with all required elements."""
    mock_response = json.dumps(MOCK_AI_LAYOUT)

    with patch("services.ai_floor_plan_service.call_llm", return_value=mock_response):
        with patch(
            "services.ai_floor_plan_service._generate_images_for_model",
            return_value=(None, {"n_generated": 0, "picked_index": None}),
        ):
            from services.ai_floor_plan_service import generate_ai_floor_plan
            result = generate_ai_floor_plan(
                footprint_geojson={
                    "type": "Polygon",
                    "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]
                },
                n_floors=12,
                building_height_m=36.0,
                units_per_core=4,
                segment="mid",
                unit_mix=["2BHK", "2BHK"],
            )

    assert result["status"] == "ok"
    assert result["source"] == "ai"

    # GeoJSON has room features
    features = result["layout"]["features"]
    layers = {f["properties"]["layer"] for f in features}
    assert "room" in layers
    assert "wall" in layers
    assert "window" in layers

    # SVG has professional elements
    svg = result["svg_blueprint"]
    assert "<svg" in svg
    assert "north-arrow" in svg or ">N<" in svg
    assert "structural-grid" in svg or "column-grid" in svg
    assert "scale-bar" in svg
    assert "1:100" in svg

    # Metrics present
    metrics = result["metrics"]
    assert metrics["nUnitsPerFloor"] == 2
    assert metrics["footprintSqm"] > 0


def test_fallback_to_deterministic_when_no_rooms():
    """When AI returns units without rooms, fallback to deterministic layout."""
    no_rooms_layout = json.dumps({
        "core": MOCK_AI_LAYOUT["core"],
        "corridor": MOCK_AI_LAYOUT["corridor"],
        "units": [
            {"id": "U1", "type": "2BHK", "side": "south",
             "x": 0, "y": 0, "w": 10, "h": 5.25},
            {"id": "U2", "type": "2BHK", "side": "north",
             "x": 0, "y": 6.75, "w": 10, "h": 5.25},
        ],
        "design_notes": "No rooms provided"
    })

    with patch("services.ai_floor_plan_service.call_llm", return_value=no_rooms_layout):
        with patch(
            "services.ai_floor_plan_service._generate_images_for_model",
            return_value=(None, {"n_generated": 0, "picked_index": None}),
        ):
            from services.ai_floor_plan_service import generate_ai_floor_plan
            result = generate_ai_floor_plan(
                footprint_geojson={
                    "type": "Polygon",
                    "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]
                },
                n_floors=12,
                building_height_m=36.0,
                units_per_core=2,
                segment="mid",
            )

    # Should still produce valid output via fallback
    assert result["status"] == "ok"
    features = result["layout"]["features"]
    room_features = [f for f in features if f["properties"]["layer"] == "room"]
    assert len(room_features) > 0, "Fallback should produce rooms"
