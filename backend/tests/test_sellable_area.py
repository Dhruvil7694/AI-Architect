import pytest
from architecture.models.sellable_area import (
    interpolate_sellable_per_yard,
    compute_sellable_area,
    compute_rca_from_flat_area,
    compute_rca_from_rooms,
    SellableAreaSummary,
)

def test_exact_fsi_ratio():
    """FSI 3.6 → exactly 54 sellable/yard."""
    ratio = interpolate_sellable_per_yard(fsi=3.6)
    assert ratio == pytest.approx(54.0, abs=0.1)

def test_interpolated_fsi_ratio():
    """FSI 3.0 → interpolated between 42 (2.7) and 54 (3.6)."""
    ratio = interpolate_sellable_per_yard(fsi=3.0)
    assert 42.0 < ratio < 54.0

def test_sellable_area_4000_yard_fsi_3_6():
    """Client example: 4000 yard plot, FSI 3.6 → 216,000 sqft sellable."""
    result = compute_sellable_area(
        plot_area_sq_yards=4000.0,
        achieved_fsi=3.6,
    )
    assert result.total_sellable_sqft == pytest.approx(216000.0, rel=0.01)

def test_rca_from_flat_area():
    """Client example: 1960 sqft flat × 0.55 = 1078 sqft RCA."""
    rca = compute_rca_from_flat_area(flat_total_sqft=1960.0, ratio=0.55)
    assert rca == pytest.approx(1078.0, abs=1.0)

def test_rca_from_rooms():
    """RCA = sum of internal room areas (wall-to-wall)."""
    room_areas = [120.0, 100.0, 80.0, 35.0, 25.0]  # sqft
    rca = compute_rca_from_rooms(room_areas_sqft=room_areas)
    assert rca == pytest.approx(360.0)

def test_sellable_summary_complete():
    """Full summary includes sellable, RCA, efficiency."""
    summary = compute_sellable_area(
        plot_area_sq_yards=4000.0,
        achieved_fsi=3.6,
        flat_total_sqft=1960.0,
        segment="mid",
    )
    assert summary.total_sellable_sqft > 0
    assert summary.estimated_rca_per_flat_sqft > 0
    assert summary.efficiency_ratio > 0
