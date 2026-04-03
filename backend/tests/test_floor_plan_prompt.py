"""Tests for the GDCR-aware floor plan prompt builder."""

import pytest


def test_build_system_prompt_contains_gdcr_rules():
    """System prompt must include GDCR room minimums and architectural principles."""
    from services.ai_floor_plan_prompt import build_system_prompt
    prompt = build_system_prompt()
    # Must contain GDCR room minimums
    assert "9.5" in prompt  # living room min area
    assert "2.7" in prompt  # master bedroom min width
    assert "5.5" in prompt  # kitchen min area
    # Must contain architectural principles
    assert "Entry sequence" in prompt or "entry sequence" in prompt.lower()
    assert "Wet zone" in prompt or "wet zone" in prompt.lower()
    assert "ventilation" in prompt.lower()


def test_build_system_prompt_contains_role():
    """System prompt starts with GDCR-compliant architect role for Surat."""
    from services.ai_floor_plan_prompt import build_system_prompt
    prompt = build_system_prompt()
    assert "GDCR" in prompt
    assert "Surat" in prompt or "SUDA" in prompt


def test_build_system_prompt_requests_room_level_output():
    """System prompt asks for room-level geometry, not just unit envelopes."""
    from services.ai_floor_plan_prompt import build_system_prompt
    prompt = build_system_prompt()
    assert "rooms" in prompt.lower()
    # Must NOT say 'no interior rooms needed' (old prompt)
    assert "no interior rooms needed" not in prompt.lower()


def test_build_user_prompt_includes_floor_params():
    """User prompt includes floor plate dimensions and unit mix."""
    from services.ai_floor_plan_prompt import build_user_prompt
    prompt = build_user_prompt(
        floor_width_m=31.4,
        floor_depth_m=14.0,
        n_floors=12,
        building_height_m=36.0,
        units_per_core=4,
        segment="mid",
        unit_mix=["2BHK", "3BHK"],
        n_lifts=2,
        n_stairs=2,
    )
    assert "31.4" in prompt
    assert "14.0" in prompt
    assert "2BHK" in prompt
    assert "3BHK" in prompt


def test_room_program_completeness():
    """ROOM_PROGRAMS has entries for 1BHK, 2BHK, 3BHK, 4BHK with correct room counts."""
    from services.ai_floor_plan_prompt import ROOM_PROGRAMS
    assert "1BHK" in ROOM_PROGRAMS
    assert "2BHK" in ROOM_PROGRAMS
    assert "3BHK" in ROOM_PROGRAMS
    assert "4BHK" in ROOM_PROGRAMS
    # 2BHK should have: foyer, living, kitchen, utility, bedroom1, bedroom2, bathroom, toilet, balcony
    assert len(ROOM_PROGRAMS["2BHK"]) >= 9
    # 3BHK should have: foyer, living_dining, kitchen, utility, bed1, bed2, bed3, bath1, bath2, toilet, balcony
    assert len(ROOM_PROGRAMS["3BHK"]) >= 11


def test_gdcr_minimums_dict():
    """GDCR_ROOM_MINIMUMS dict has correct values per spec."""
    from services.ai_floor_plan_prompt import GDCR_ROOM_MINIMUMS
    assert GDCR_ROOM_MINIMUMS["living"] == {"min_area": 9.5, "min_width": 3.0}
    assert GDCR_ROOM_MINIMUMS["bedroom"] == {"min_area": 9.5, "min_width": 2.7}
    assert GDCR_ROOM_MINIMUMS["bedroom2"] == {"min_area": 7.5, "min_width": 2.5}
    assert GDCR_ROOM_MINIMUMS["kitchen"] == {"min_area": 5.5, "min_width": 1.8}
    assert GDCR_ROOM_MINIMUMS["bathroom"] == {"min_area": 2.16, "min_width": 1.2}
    assert GDCR_ROOM_MINIMUMS["toilet"] == {"min_area": 1.65, "min_width": 1.1}
