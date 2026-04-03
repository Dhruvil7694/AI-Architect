"""
Tests for unit_layout_engine.py
"""

from __future__ import annotations

import pytest
from services.unit_layout_engine import (
    generate_unit_rooms,
    layout_floor,
    _zone_heights,
    _distribute_widths,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _south_unit(uid="U1", utype="2BHK", x=0.0, y=0.0, w=9.5, h=10.75):
    return {"id": uid, "type": utype, "side": "south",
            "x": x, "y": y, "w": w, "h": h}


def _north_unit(uid="U3", utype="2BHK", x=0.0, y=11.5, w=9.5, h=10.75):
    return {"id": uid, "type": utype, "side": "north",
            "x": x, "y": y, "w": w, "h": h}


# ── Zone height tests ─────────────────────────────────────────────────────────

class TestZoneHeights:
    def test_heights_sum_to_unit_depth(self):
        for utype in ("1BHK", "2BHK", "3BHK", "4BHK"):
            bed_h, wet_h, living_h, foyer_h = _zone_heights(10.75, utype, 1.15)
            total = bed_h + wet_h + living_h + foyer_h
            assert abs(total - 10.75) < 0.02, \
                f"{utype}: zone heights {total:.3f} != 10.75"

    def test_zone_a_respects_gdcr_min(self):
        bed_h, _, _, _ = _zone_heights(10.75, "2BHK", 1.0)
        # GDCR master bedroom depth minimum = 3.52 m at budget
        assert bed_h >= 3.52 - 0.05

    def test_zone_c_respects_living_min(self):
        _, wet_h, living_h, foyer_h = _zone_heights(10.75, "2BHK", 1.0)
        # GDCR living min depth = 3.17 m
        assert living_h >= 3.17 - 0.05

    def test_shallow_unit_still_returns_heights(self):
        # Should not raise — instead returns compressed zone heights
        bed_h, wet_h, living_h, foyer_h = _zone_heights(9.0, "2BHK", 1.0)
        assert abs(bed_h + wet_h + living_h + foyer_h - 9.0) < 0.05
        assert bed_h > 0 and wet_h > 0 and living_h > 0 and foyer_h > 0

    def test_very_shallow_unit_still_returns_heights(self):
        bed_h, wet_h, living_h, foyer_h = _zone_heights(8.0, "2BHK", 1.0)
        assert abs(bed_h + wet_h + living_h + foyer_h - 8.0) < 0.05


# ── Width distribution tests ──────────────────────────────────────────────────

class TestDistributeWidths:
    def test_widths_sum_to_unit_w(self):
        spec = [("bedroom", "Bed1", 0.56), ("bedroom2", "Bed2", 0.44)]
        widths = _distribute_widths(spec, 9.5)
        assert abs(sum(widths) - 9.5) < 0.02

    def test_each_room_meets_min_width(self):
        from services.unit_layout_engine import _MIN_W
        spec = [("bathroom", "Bath", 0.38), ("utility", "Util", 0.30),
                ("toilet", "WC", 0.32)]
        widths = _distribute_widths(spec, 9.5)
        for (rtype, *_), w in zip(spec, widths):
            assert w >= _MIN_W[rtype] - 0.02, \
                f"{rtype} width {w:.2f} < min {_MIN_W[rtype]}"

    def test_narrow_unit_still_distributes(self):
        spec = [("living", "Living", 0.62), ("kitchen", "Kitchen", 0.38)]
        widths = _distribute_widths(spec, 5.0)
        assert abs(sum(widths) - 5.0) < 0.02
        assert all(w > 0 for w in widths)


# ── generate_unit_rooms ────────────────────────────────────────────────────────

class TestGenerateUnitRooms:

    def _check_no_overlaps(self, rooms):
        from services.unit_layout_engine import _overlap
        for i, a in enumerate(rooms):
            for b in rooms[i + 1:]:
                assert not _overlap(a, b), \
                    f"Overlap: '{a['name']}' and '{b['name']}'"

    def _check_coverage(self, rooms, uw, uh, min_frac=0.82):
        covered = sum(r["w"] * r["h"] for r in rooms)
        coverage = covered / (uw * uh)
        assert coverage >= min_frac, f"Coverage {coverage:.1%} < {min_frac:.0%}"

    def _check_exterior_bedrooms(self, rooms, unit):
        """All bedroom types must touch the exterior face of the unit."""
        side = unit["side"]
        uy, uh = unit["y"], unit["h"]
        ext_y = uy if side == "south" else uy + uh

        for r in rooms:
            if r["type"] in ("bedroom", "bedroom2"):
                if side == "south":
                    assert abs(r["y"] - ext_y) < 0.05, \
                        f"{r['name']} y={r['y']:.2f} not at exterior y={ext_y}"
                else:
                    room_top = r["y"] + r["h"]
                    assert abs(room_top - ext_y) < 0.05, \
                        f"{r['name']} top={room_top:.2f} not at exterior y={ext_y}"

    def _check_foyer_at_corridor(self, rooms, unit):
        """Foyer must be at the corridor-facing edge of the unit."""
        side = unit["side"]
        uy, uh = unit["y"], unit["h"]

        foyer = next((r for r in rooms if r["type"] == "foyer"), None)
        assert foyer is not None, "No foyer found"

        if side == "south":
            # Corridor face = uy + uh (top of south unit)
            foyer_top = foyer["y"] + foyer["h"]
            assert abs(foyer_top - (uy + uh)) < 0.05, \
                f"Foyer top {foyer_top:.2f} not at corridor face {uy + uh}"
        else:
            # Corridor face = uy (bottom of north unit)
            assert abs(foyer["y"] - uy) < 0.05, \
                f"Foyer y {foyer['y']:.2f} not at corridor face {uy}"

    # ── 2BHK south unit ───────────────────────────────────────────────────────

    def test_2bhk_south_no_overlaps(self):
        unit = _south_unit()
        result = generate_unit_rooms(unit, "mid")
        self._check_no_overlaps(result["rooms"])

    def test_2bhk_south_coverage(self):
        unit = _south_unit()
        result = generate_unit_rooms(unit, "mid")
        self._check_coverage(result["rooms"], unit["w"], unit["h"])

    def test_2bhk_south_bedrooms_on_exterior_wall(self):
        unit = _south_unit()
        result = generate_unit_rooms(unit, "mid")
        self._check_exterior_bedrooms(result["rooms"], unit)

    def test_2bhk_south_foyer_at_corridor_face(self):
        unit = _south_unit()
        result = generate_unit_rooms(unit, "mid")
        self._check_foyer_at_corridor(result["rooms"], unit)

    def test_2bhk_south_has_balcony_outside_unit(self):
        unit = _south_unit()
        result = generate_unit_rooms(unit, "mid")
        assert "balcony" in result, "Missing balcony"
        bal = result["balcony"]
        # Balcony projects below unit (south)
        assert bal["y"] < unit["y"], \
            f"Balcony y={bal['y']:.2f} should be below unit y={unit['y']}"

    # ── 2BHK north unit ───────────────────────────────────────────────────────

    def test_2bhk_north_no_overlaps(self):
        unit = _north_unit()
        result = generate_unit_rooms(unit, "mid")
        self._check_no_overlaps(result["rooms"])

    def test_2bhk_north_bedrooms_on_exterior_wall(self):
        unit = _north_unit()
        result = generate_unit_rooms(unit, "mid")
        self._check_exterior_bedrooms(result["rooms"], unit)

    def test_2bhk_north_foyer_at_corridor_face(self):
        unit = _north_unit()
        result = generate_unit_rooms(unit, "mid")
        self._check_foyer_at_corridor(result["rooms"], unit)

    def test_2bhk_north_has_balcony_above_unit(self):
        unit = _north_unit()
        result = generate_unit_rooms(unit, "mid")
        bal = result["balcony"]
        unit_top = unit["y"] + unit["h"]
        assert bal["y"] >= unit_top - 0.05, \
            f"Balcony y={bal['y']:.2f} should be above unit top={unit_top}"

    # ── All unit types ────────────────────────────────────────────────────────

    @pytest.mark.parametrize("utype", ["1BHK", "2BHK", "3BHK", "4BHK"])
    def test_all_types_south_no_overlaps(self, utype):
        unit = _south_unit(uid="U1", utype=utype, w=12.0, h=11.0)
        result = generate_unit_rooms(unit, "mid")
        self._check_no_overlaps(result["rooms"])

    @pytest.mark.parametrize("utype", ["1BHK", "2BHK", "3BHK", "4BHK"])
    def test_all_types_coverage(self, utype):
        unit = _south_unit(uid="U1", utype=utype, w=12.0, h=11.0)
        result = generate_unit_rooms(unit, "mid")
        self._check_coverage(result["rooms"], unit["w"], unit["h"])

    @pytest.mark.parametrize("segment", ["budget", "mid", "premium", "luxury"])
    def test_all_segments(self, segment):
        unit = _south_unit(w=10.0, h=11.5)
        result = generate_unit_rooms(unit, segment)
        self._check_no_overlaps(result["rooms"])
        self._check_coverage(result["rooms"], unit["w"], unit["h"])

    # ── Room type presence ────────────────────────────────────────────────────

    def test_2bhk_has_expected_room_types(self):
        result = generate_unit_rooms(_south_unit(), "mid")
        types = {r["type"] for r in result["rooms"]}
        assert "bedroom" in types
        assert "bedroom2" in types
        assert "living" in types
        assert "kitchen" in types
        assert "bathroom" in types
        assert "foyer" in types

    def test_3bhk_has_three_bedrooms(self):
        unit = _south_unit(utype="3BHK", w=14.0, h=11.5)
        result = generate_unit_rooms(unit, "mid")
        bed_count = sum(1 for r in result["rooms"]
                        if r["type"] in ("bedroom", "bedroom2"))
        assert bed_count == 3

    # ── GDCR area checks ──────────────────────────────────────────────────────

    def test_living_meets_gdcr_minimum(self):
        result = generate_unit_rooms(_south_unit(w=9.5, h=10.75), "budget")
        living = next(r for r in result["rooms"] if r["type"] == "living")
        assert living["w"] * living["h"] >= 9.5 - 0.2, \
            f"Living area {living['w'] * living['h']:.2f} < GDCR 9.5 m²"

    def test_master_bedroom_meets_gdcr_minimum(self):
        result = generate_unit_rooms(_south_unit(w=9.5, h=10.75), "budget")
        beds = [r for r in result["rooms"] if r["type"] == "bedroom"]
        assert len(beds) >= 1
        assert beds[0]["w"] * beds[0]["h"] >= 9.5 - 0.5, \
            f"Master bed {beds[0]['w'] * beds[0]['h']:.2f} < GDCR 9.5 m²"

    # ── layout_floor convenience function ────────────────────────────────────

    def test_layout_floor_injects_rooms_into_all_units(self):
        floor = {
            "corridor": {"x": 0, "y": 10.75, "w": 24, "h": 1.5},
            "units": [
                _south_unit("U1", "2BHK", 0, 0, 9.5, 10.75),
                _south_unit("U2", "2BHK", 10.5, 0, 9.5, 10.75),
                _north_unit("U3", "2BHK", 0, 12.25, 9.5, 10.75),
                _north_unit("U4", "2BHK", 10.5, 12.25, 9.5, 10.75),
            ],
        }
        result = layout_floor(floor, "mid")
        for u in result["units"]:
            assert "rooms" in u, f"Unit {u['id']} missing rooms"
            assert len(u["rooms"]) >= 5
