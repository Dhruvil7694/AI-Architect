"""Tests for floor plan preview image prompt (no network)."""

from __future__ import annotations


def test_build_prompt_includes_dimensions_and_metrics():
    from services.floor_plan_preview_image_service import build_floor_plan_image_prompt

    # 10 ft x 12 ft box in DXF feet → ~3.05 x 3.66 m
    footprint = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [10, 0], [10, 12], [0, 12], [0, 0]]],
    }
    payload = {
        "footprint": footprint,
        "n_floors": 10,
        "building_height_m": 30.0,
        "units_per_core": 4,
        "segment": "premium",
        "unit_mix": ["2BHK", "3BHK"],
        "storey_height_m": 3.0,
        "plot_area_sqm": 500.0,
        "design_brief": "Corner units with cross-ventilation",
        "design_notes": "Double-loaded corridor",
        "ai_metrics": {
            "efficiencyPct": 72.5,
            "nUnitsPerFloor": 8,
            "netBuaSqm": 620.0,
            "nLifts": 2,
            "nStairs": 2,
        },
    }
    p = build_floor_plan_image_prompt(payload)
    assert "Professional architectural floor plan" in p
    assert "premium" in p
    assert "2BHK" in p or "3BHK" in p
    assert "Corner units" in p
    assert "Double-loaded" in p
    assert "72.5" in p or "efficiency" in p.lower()
