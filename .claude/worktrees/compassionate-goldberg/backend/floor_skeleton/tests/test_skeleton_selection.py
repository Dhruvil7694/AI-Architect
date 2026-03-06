"""
Phase 1 FloorSkeleton selection and scoring regression tests.

These tests freeze the behaviour of the deterministic scoring tuple used
by `floor_skeleton.skeleton_evaluator.select_best`, so future changes to
area weighting, efficiency weighting, or label tie-break order must be
made explicitly by updating these expectations.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from shapely.geometry import box as shapely_box

from floor_skeleton.models import (
    FloorSkeleton,
    UnitZone,
    AXIS_DEPTH_DOMINANT,
    LABEL_END_CORE_LEFT,
    LABEL_END_CORE_RIGHT,
    LABEL_CENTER_CORE,
)
from floor_skeleton.skeleton_evaluator import select_best


def _make_stub_skeleton(
    *,
    unit_area_sqm: float,
    efficiency_ratio: float,
    placement_label: str,
    n_zones: int = 1,
) -> FloorSkeleton:
    """
    Build a minimal FloorSkeleton suitable for select_best():
      - area_summary["unit_area_sqm"] controls absolute usable area
      - efficiency_ratio controls secondary ordering
      - placement_label feeds into LABEL_ORDER-based tie-breaks
    Geometry is a simple 10×10 slab with n_zones identical UnitZone rectangles.
    """
    fp = shapely_box(0, 0, 10, 10)
    core = shapely_box(0, 0, 2, 10)

    zones: list[UnitZone] = []
    for band_id in range(n_zones):
        # Each zone is a simple 4×5 rectangle inside the footprint.
        poly = shapely_box(2, band_id * 5, 6, band_id * 5 + 5)
        zones.append(
            UnitZone(
                band_id=band_id,
                polygon=poly,
                orientation_axis=AXIS_DEPTH_DOMINANT,
                zone_width_m=4.0,
                zone_depth_m=5.0,
            )
        )

    return FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=None,
        unit_zones=zones,
        pattern_used="DOUBLE_LOADED",
        placement_label=placement_label,
        area_summary={"unit_area_sqm": unit_area_sqm},
        efficiency_ratio=efficiency_ratio,
        is_geometry_valid=True,
        passes_min_unit_guard=True,
        is_architecturally_viable=True,
        audit_log=[],
    )


class TestSkeletonSelectBestScoring(SimpleTestCase):
    """
    select_best must primarily favour higher absolute unit_area_sqm, then
    higher efficiency_ratio, then number of zones, and finally placement label
    order (LABEL_ORDER) as the last tie-breaker.
    """

    def test_prefers_higher_unit_area_then_efficiency(self) -> None:
        # Three candidates:
        #   s_small   : lowest unit area, highest efficiency
        #   s_medium  : medium unit area, medium efficiency
        #   s_large   : highest unit area, lowest efficiency
        #
        # select_best should pick s_large because absolute usable area is the
        # primary optimisation axis, even if its efficiency is slightly lower.
        s_small = _make_stub_skeleton(
            unit_area_sqm=80.0,
            efficiency_ratio=0.45,
            placement_label=LABEL_CENTER_CORE,
        )
        s_medium = _make_stub_skeleton(
            unit_area_sqm=100.0,
            efficiency_ratio=0.40,
            placement_label=LABEL_END_CORE_RIGHT,
        )
        s_large = _make_stub_skeleton(
            unit_area_sqm=120.0,
            efficiency_ratio=0.38,
            placement_label=LABEL_END_CORE_LEFT,
        )

        best = select_best([s_medium, s_small, s_large])
        assert best is not None
        self.assertIs(best, s_large)
        self.assertEqual(best.area_summary["unit_area_sqm"], 120.0)
        self.assertAlmostEqual(best.efficiency_ratio, 0.38)

    def test_label_tie_breaker_uses_label_order(self) -> None:
        # Two candidates with identical unit_area and efficiency; tie must be
        # broken using LABEL_ORDER priority:
        #   LABEL_END_CORE_LEFT  (higher priority)
        #   LABEL_CENTER_CORE    (lower priority)
        s_left = _make_stub_skeleton(
            unit_area_sqm=100.0,
            efficiency_ratio=0.40,
            placement_label=LABEL_END_CORE_LEFT,
        )
        s_center = _make_stub_skeleton(
            unit_area_sqm=100.0,
            efficiency_ratio=0.40,
            placement_label=LABEL_CENTER_CORE,
        )

        best = select_best([s_center, s_left])
        assert best is not None
        self.assertIs(best, s_left)
        self.assertEqual(best.placement_label, LABEL_END_CORE_LEFT)

    def test_stable_under_input_permutation(self) -> None:
        # Re-ordering the input list must not change the selected best skeleton.
        s_a = _make_stub_skeleton(
            unit_area_sqm=90.0,
            efficiency_ratio=0.42,
            placement_label=LABEL_END_CORE_RIGHT,
        )
        s_b = _make_stub_skeleton(
            unit_area_sqm=110.0,
            efficiency_ratio=0.39,
            placement_label=LABEL_END_CORE_LEFT,
        )
        s_c = _make_stub_skeleton(
            unit_area_sqm=105.0,
            efficiency_ratio=0.41,
            placement_label=LABEL_CENTER_CORE,
        )

        best1 = select_best([s_a, s_b, s_c])
        best2 = select_best([s_c, s_a, s_b])
        best3 = select_best([s_b, s_c, s_a])

        # All three invocations must pick the same object instance.
        assert best1 is not None and best2 is not None and best3 is not None
        self.assertIs(best1, s_b)
        self.assertIs(best2, s_b)
        self.assertIs(best3, s_b)

