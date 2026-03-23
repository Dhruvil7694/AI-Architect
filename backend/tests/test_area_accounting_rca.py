import pytest
from area_accounting.floor_area import (
    FloorAreaBreakdown,
    compute_floor_area_breakdown_with_rca_estimate,
)

def test_rca_estimate_from_unit_areas():
    """When wall engine is not used, estimate RCA from unit envelope area x ratio."""
    breakdown = compute_floor_area_breakdown_with_rca_estimate(
        gross_built_up_sqm=200.0,
        core_area_sqm=15.0,
        corridor_area_sqm=10.0,
        unit_envelope_areas_sqm=[50.0, 50.0, 40.0, 35.0],
        segment="mid",
    )
    assert breakdown.rera_carpet_area_total_sqm > 0
    assert len(breakdown.carpet_per_unit) == 4
    # Each unit RCA should be ~55% of its envelope area
    assert breakdown.carpet_per_unit[0] == pytest.approx(50.0 * 0.55, rel=0.01)

def test_rca_efficiency_ratio_luxury():
    """Luxury segment has 0.45 efficiency (more walls, thicker finishes)."""
    breakdown = compute_floor_area_breakdown_with_rca_estimate(
        gross_built_up_sqm=200.0,
        core_area_sqm=15.0,
        corridor_area_sqm=10.0,
        unit_envelope_areas_sqm=[80.0, 80.0],
        segment="luxury",
    )
    assert breakdown.carpet_per_unit[0] == pytest.approx(80.0 * 0.45, rel=0.01)
