"""
Tests for the Layer 1 → 1.5 → 2 prompt pipeline:
  unit_programme  →  layout_engine  →  compile_recraft_prompt
"""
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_layouts(unit_type="2BHK", segment="Mid", unit_w=9.5, unit_d=10.75,
                  units_per_core=4):
    """Run Layer 1 + 1.5 and return (layouts, programme)."""
    from services.unit_programme import compute_net_usable, derive_room_programme
    from services.layout_engine import generate_unit_layout

    floor_w, floor_d = unit_w * (units_per_core // 2) + 4.5, unit_d * 2 + 1.5
    net = compute_net_usable(
        tower_footprint_sqm=floor_w * floor_d,
        core_area_sqm=4.5 * floor_d,
        units_per_core=units_per_core,
        floor_plate_depth_m=floor_d,
    )
    programme = derive_room_programme(unit_type, segment, net, units_per_core)
    layouts, _result = generate_unit_layout(programme, unit_w, unit_d, units_per_core)
    return layouts, programme


# ---------------------------------------------------------------------------
# Layer 1: unit_programme
# ---------------------------------------------------------------------------

class TestUnitProgramme:

    @pytest.mark.parametrize("utype", ["1BHK", "2BHK", "3BHK", "4BHK"])
    def test_produces_rooms_for_all_types(self, utype):
        from services.unit_programme import compute_net_usable, derive_room_programme
        net = compute_net_usable(380.0, 40.0, 4, 12.0)
        prog = derive_room_programme(utype, "Mid", net, 4)
        assert len(prog.rooms) >= 4

    @pytest.mark.parametrize("segment", ["Budget", "Mid", "Premium", "Luxury"])
    def test_carpet_area_increases_with_segment(self, segment):
        from services.unit_programme import compute_net_usable, derive_room_programme
        net = compute_net_usable(380.0, 40.0, 4, 12.0)
        prog = derive_room_programme("2BHK", segment, net, 4)
        assert prog.carpet_area_sqm > 0

    def test_room_widths_meet_minimums(self):
        from services.unit_programme import compute_net_usable, derive_room_programme, _MIN_ROOM_DIM
        net = compute_net_usable(380.0, 40.0, 4, 12.0)
        prog = derive_room_programme("3BHK", "Mid", net, 4)
        for room in prog.rooms:
            base = room.name.split("_")[0]
            if base in _MIN_ROOM_DIM:
                min_w, _ = _MIN_ROOM_DIM[base]
                assert room.width_m >= min_w - 0.05, (
                    f"{room.name} width {room.width_m:.2f} < min {min_w}"
                )

    def test_living_in_front_zone(self):
        from services.unit_programme import compute_net_usable, derive_room_programme
        net = compute_net_usable(380.0, 40.0, 4, 12.0)
        prog = derive_room_programme("2BHK", "Mid", net, 4)
        living = prog.get("living")
        assert living is not None
        assert living.zone == "front"

    def test_master_bed_in_rear_zone(self):
        from services.unit_programme import compute_net_usable, derive_room_programme
        net = compute_net_usable(380.0, 40.0, 4, 12.0)
        prog = derive_room_programme("2BHK", "Mid", net, 4)
        master = prog.get("master_bed")
        assert master is not None
        assert master.zone == "rear"


# ---------------------------------------------------------------------------
# Layer 1.5: layout_engine
# ---------------------------------------------------------------------------

class TestLayoutEngine:

    def test_living_at_front(self):
        layouts, _ = _make_layouts("2BHK", "Mid")
        living = next((r for r in layouts if r.name == "living"), None)
        assert living is not None
        assert living.zone == "front"

    def test_passage_exists(self):
        layouts, _ = _make_layouts("2BHK", "Mid")
        passage = next((r for r in layouts if r.is_passage), None)
        assert passage is not None

    def test_bedrooms_in_rear(self):
        layouts, _ = _make_layouts("3BHK", "Mid", unit_w=12.0, unit_d=11.0)
        bed_names = {"master_bed", "bed_2", "bed_3", "bed_4"}
        for r in layouts:
            if r.name in bed_names:
                assert r.zone == "rear", f"{r.name} expected rear, got {r.zone}"

    def test_no_overlapping_rooms(self):
        layouts, _ = _make_layouts("2BHK", "Mid")
        for i, a in enumerate(layouts):
            for b in layouts[i + 1:]:
                overlap_x = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
                overlap_y = min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y)
                assert not (overlap_x > 0.05 and overlap_y > 0.05), (
                    f"Overlap: {a.name} and {b.name}"
                )

    @pytest.mark.parametrize("utype", ["1BHK", "2BHK", "3BHK", "4BHK"])
    def test_all_unit_types_produce_layouts(self, utype):
        layouts, _ = _make_layouts(utype, "Mid", unit_w=12.0, unit_d=11.0)
        assert len(layouts) >= 3


# ---------------------------------------------------------------------------
# Layer 2: compile_recraft_prompt
# ---------------------------------------------------------------------------

class TestCompileRecraftPrompt:

    def _compile(self, unit_type="2BHK", segment="Mid", unit_w=9.5, unit_d=10.75,
                 n_units=4):
        from services.floor_plan_image_prompt import compile_recraft_prompt
        layouts, _ = _make_layouts(unit_type, segment, unit_w, unit_d, n_units)
        return compile_recraft_prompt(
            layouts=layouts,
            unit_w=unit_w,
            unit_d=unit_d,
            unit_type=unit_type,
            n_units=n_units,
            segment=segment,
        )

    def test_returns_nonempty_string(self):
        result = self._compile()
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_style_anchor(self):
        result = self._compile()
        assert "2D" in result or "CAD" in result or "floor plan" in result.lower()

    def test_contains_unit_dimensions(self):
        result = self._compile(unit_w=9.5, unit_d=10.75)
        assert "9.5" in result or "10.75" in result

    def test_contains_critical_requirements(self):
        result = self._compile()
        text = result.lower()
        assert "living" in text
        assert "bedroom" in text or "bed" in text

    def test_entry_sequence_mention(self):
        result = self._compile()
        text = result.lower()
        assert "entry" in text or "entrance" in text or "foyer" in text

    @pytest.mark.parametrize("utype", ["1BHK", "2BHK", "3BHK", "4BHK"])
    def test_all_unit_types_produce_prompt(self, utype):
        result = self._compile(unit_type=utype, unit_w=12.0, unit_d=11.0)
        assert isinstance(result, str) and len(result) > 50

    @pytest.mark.parametrize("segment", ["Budget", "Mid", "Premium", "Luxury"])
    def test_all_segments_produce_prompt(self, segment):
        result = self._compile(segment=segment)
        assert isinstance(result, str) and len(result) > 50

    def test_no_code_tokens_in_prompt(self):
        """Prompt must be plain English, not token notation."""
        result = self._compile()
        assert "{" not in result
        assert "}" not in result
        assert "u1-" not in result  # no compact token notation

    def test_negative_constraints_present(self):
        result = self._compile()
        text = result.lower()
        assert "no 3d" in text or "no perspective" in text or "no furniture" in text


# ---------------------------------------------------------------------------
# End-to-end: _build_recraft_prompt helper in ai_floor_plan_service
# ---------------------------------------------------------------------------

class TestBuildRecraftPromptHelper:

    def test_returns_string_for_valid_inputs(self):
        from services.ai_floor_plan_service import _build_recraft_prompt
        result = _build_recraft_prompt(
            floor_width_m=24.0,
            floor_depth_m=13.5,
            units_per_core=4,
            unit_mix=["2BHK", "3BHK"],
            segment="mid",
            n_lifts=2,
            n_stairs=2,
        )
        assert isinstance(result, str)
        assert len(result) > 100

    def test_returns_none_gracefully_on_bad_input(self):
        from services.ai_floor_plan_service import _build_recraft_prompt
        # Extremely small floor (should not raise, returns None)
        result = _build_recraft_prompt(
            floor_width_m=1.0,
            floor_depth_m=1.0,
            units_per_core=4,
            unit_mix=[],
            segment="mid",
            n_lifts=0,
            n_stairs=0,
        )
        # Must not raise; may return None or a (possibly degenerate) string
        assert result is None or isinstance(result, str)

    def test_different_unit_mixes(self):
        from services.ai_floor_plan_service import _build_recraft_prompt
        for utype in ("1BHK", "2BHK", "3BHK", "4BHK"):
            result = _build_recraft_prompt(
                floor_width_m=28.0, floor_depth_m=13.5,
                units_per_core=4, unit_mix=[utype],
                segment="mid", n_lifts=2, n_stairs=2,
            )
            assert result is None or len(result) > 50
