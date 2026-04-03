"""Tests for expanded floor plan validator — room completeness + GDCR enforcement."""

import pytest
from copy import deepcopy


def _make_unit(unit_id="U1", unit_type="2BHK", side="south",
               x=0, y=0, w=10, h=6, rooms=None, balcony=None):
    """Helper to build a unit dict."""
    return {
        "id": unit_id, "type": unit_type, "side": side,
        "x": x, "y": y, "w": w, "h": h,
        "rooms": rooms or [],
        "balcony": balcony,
    }


def _make_room(room_id, room_type, x, y, w, h):
    return {"id": room_id, "type": room_type, "x": x, "y": y, "w": w, "h": h}


def _make_layout(units, core=None, corridor=None):
    return {
        "core": core or {"x": 10, "y": 0, "w": 4, "h": 12, "stairs": [], "lifts": [], "lobby": {"x": 10, "y": 5, "w": 4, "h": 2}},
        "corridor": corridor or {"x": 0, "y": 5.25, "w": 20, "h": 1.5},
        "units": units,
    }


def test_room_completeness_pass():
    """2BHK with all required rooms passes completeness check."""
    from services.ai_floor_plan_validator import check_room_completeness
    rooms = [
        _make_room("R1", "foyer", 0, 0, 2, 1.5),
        _make_room("R2", "living", 2, 0, 4, 3),
        _make_room("R3", "kitchen", 6, 0, 3, 3),
        _make_room("R4", "utility", 6, 3, 2, 1.8),
        _make_room("R5", "bedroom", 0, 3, 5, 3),
        _make_room("R6", "bathroom", 0, 1.5, 2, 1.8),
        _make_room("R7", "bedroom2", 5, 3, 4, 3),
        _make_room("R8", "toilet", 8, 3, 1.5, 1.8),
    ]
    unit = _make_unit(rooms=rooms)
    errors = check_room_completeness(unit)
    assert errors == []


def test_room_completeness_missing_rooms():
    """2BHK missing bedroom2 and toilet triggers errors."""
    from services.ai_floor_plan_validator import check_room_completeness
    rooms = [
        _make_room("R1", "foyer", 0, 0, 2, 1.5),
        _make_room("R2", "living", 2, 0, 4, 3),
        _make_room("R3", "kitchen", 6, 0, 3, 3),
        _make_room("R4", "bedroom", 0, 3, 5, 3),
        _make_room("R5", "bathroom", 0, 1.5, 2, 1.8),
    ]
    unit = _make_unit(rooms=rooms)
    errors = check_room_completeness(unit)
    assert len(errors) > 0
    assert any("bedroom2" in e.lower() or "toilet" in e.lower() for e in errors)


def test_room_completeness_empty_unit():
    """Unit with no rooms at all triggers error."""
    from services.ai_floor_plan_validator import check_room_completeness
    unit = _make_unit(rooms=[])
    errors = check_room_completeness(unit)
    assert len(errors) > 0


def test_gdcr_area_enforcement_clamps_small_room():
    """Room below GDCR minimum area gets clamped up."""
    from services.ai_floor_plan_validator import enforce_gdcr_minimums
    rooms = [_make_room("R1", "living", 0, 0, 2.5, 3.0)]  # 7.5 sqm < 9.5
    adjusted, warnings = enforce_gdcr_minimums(rooms)
    area = adjusted[0]["w"] * adjusted[0]["h"]
    assert area >= 9.5
    assert len(warnings) > 0


def test_gdcr_width_enforcement_clamps_narrow_room():
    """Room below GDCR minimum width gets width clamped."""
    from services.ai_floor_plan_validator import enforce_gdcr_minimums
    rooms = [_make_room("R1", "kitchen", 0, 0, 1.5, 4.0)]  # width 1.5 < 1.8
    adjusted, warnings = enforce_gdcr_minimums(rooms)
    assert adjusted[0]["w"] >= 1.8
    assert len(warnings) > 0


def test_ventilation_check_habitable_on_exterior():
    """Living room touching exterior wall (y=0 for south unit) passes ventilation."""
    from services.ai_floor_plan_validator import check_ventilation
    unit = _make_unit(side="south", y=0, h=6)
    rooms = [_make_room("R1", "living", 0, 0, 4, 3)]  # y=0 touches south exterior
    errors = check_ventilation(unit, rooms)
    assert errors == []


def test_ventilation_check_landlocked_room_fails():
    """Living room not touching any exterior wall triggers ventilation error."""
    from services.ai_floor_plan_validator import check_ventilation
    unit = _make_unit(side="south", x=5, y=0, w=10, h=6)
    # Living room at interior position — doesn't touch any exterior edge
    rooms = [_make_room("R1", "living", 7, 2, 3, 2)]
    errors = check_ventilation(unit, rooms)
    assert len(errors) > 0
