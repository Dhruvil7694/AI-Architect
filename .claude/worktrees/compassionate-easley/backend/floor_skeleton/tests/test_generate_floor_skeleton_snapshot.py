"""
Integration snapshot for generate_floor_skeleton() on a realistic footprint.

This test freezes the interaction between:

    validate_core_fit() → generate_floor_skeleton() → evaluate() → select_best()

for a simple 18 m × 12 m slab, without involving placement, DXF, or the full
development pipeline. Only high-signal decision outputs are snapshotted:

    - pattern_used
    - placement_label
    - len(unit_zones)
    - area_summary["unit_area_sqm"]
    - efficiency_ratio

Any future change to candidate generation, evaluator scoring, or pattern
filtering must intentionally update these expectations.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from shapely.geometry import box as shapely_box

from placement_engine.geometry import FootprintCandidate
from placement_engine.geometry.core_fit import validate_core_fit

from floor_skeleton.services import generate_floor_skeleton


class TestGenerateFloorSkeletonSnapshot(SimpleTestCase):
    """
    Single deterministic snapshot for a medium-depth DOUBLE_LOADED slab.
    """

    def test_18x12m_core_fit_and_skeleton_snapshot(self) -> None:
        # Footprint: 18 m (width) × 12 m (depth) rectangle in local metres.
        fp_poly = shapely_box(0.0, 0.0, 18.0, 12.0)

        # FootprintCandidate normally comes from placement in DXF feet; for this
        # test we work entirely in metres and set *_dxf fields equal to metres.
        cand = FootprintCandidate(
            footprint_polygon=fp_poly,
            area_sqft=0.0,          # unused by generate_floor_skeleton
            width_dxf=18.0,
            depth_dxf=12.0,
            width_m=18.0,
            depth_m=12.0,
            orientation_angle_deg=0.0,
            orientation_label="PRIMARY",
            grid_resolution_dxf=1.0,
            source_component_index=0,
        )

        # Use real CoreDimensions via validate_core_fit; this locks how
        # core_pkg_width_m / core_pkg_depth_m are derived for this footprint.
        core_validation = validate_core_fit(
            width_m=18.0,
            depth_m=12.0,
            building_height_m=15.0,
        )

        skeleton = generate_floor_skeleton(cand, core_validation)

        # Snapshot: identity / pattern choice
        self.assertEqual(skeleton.pattern_used, "DOUBLE_LOADED")
        self.assertEqual(skeleton.placement_label, "END_CORE_LEFT")

        # Snapshot: basic structure
        self.assertEqual(len(skeleton.unit_zones), 2)

        # Snapshot: area + efficiency (rounded to fixed precision).
        unit_area = round(skeleton.area_summary.get("unit_area_sqm", 0.0), 4)
        eff = round(skeleton.efficiency_ratio, 3)

        self.assertEqual(unit_area, 159.192)
        self.assertEqual(eff, 0.737)

