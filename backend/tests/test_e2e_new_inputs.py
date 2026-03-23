# backend/tests/test_e2e_new_inputs.py
"""
End-to-end test: new inputs -> pipeline -> sellable area in response.
Tests the complete model chain without needing a database.
"""
import pytest
from architecture.models.building_types import get_building_type, get_permissible_building_types
from architecture.models.core_config import get_core_config, compute_required_footprint_for_core
from architecture.models.sellable_area import (
    compute_sellable_area,
    interpolate_sellable_per_yard,
    compute_rca_from_flat_area,
)


class TestNewInputsE2E:
    def test_building_type_constrains_floors(self):
        bt1 = get_building_type(1)
        bt3 = get_building_type(3)
        assert bt1.max_floors < bt3.max_floors
        assert bt1.lift_required is False
        assert bt3.fire_stair_required is True

    def test_core_config_drives_footprint(self):
        fp2 = compute_required_footprint_for_core(2, "3BHK", 30.0)
        fp6 = compute_required_footprint_for_core(6, "3BHK", 30.0)
        # 6 units/core needs a bigger footprint than 2 units/core
        assert fp6.estimated_floor_area_sqm > fp2.estimated_floor_area_sqm

    def test_sellable_ratios_match_client_examples(self):
        # Client example 1: FSI 3.6 -> 54/yard
        assert interpolate_sellable_per_yard(3.6) == pytest.approx(54.0, abs=0.1)
        # Client example 2: 4000 yards x 54 = 216,000 sqft
        s = compute_sellable_area(4000.0, 3.6)
        assert s.total_sellable_sqft == pytest.approx(216000.0, rel=0.01)

    def test_rca_matches_client_example(self):
        rca = compute_rca_from_flat_area(1960.0, ratio=0.55)
        assert rca == pytest.approx(1078.0, abs=1.0)

    def test_segment_affects_efficiency(self):
        s_budget = compute_sellable_area(4000.0, 3.6, 1960.0, "budget")
        s_luxury = compute_sellable_area(4000.0, 3.6, 1960.0, "luxury")
        assert s_budget.estimated_rca_per_flat_sqft > s_luxury.estimated_rca_per_flat_sqft

    def test_building_type_road_width_filtering(self):
        """9m road only allows Type 1 (low-rise)."""
        types = get_permissible_building_types(road_width_m=9.0)
        ids = [t.id for t in types]
        assert 1 in ids
        assert 2 not in ids

    def test_core_footprint_end_core_vs_double(self):
        """2 units/core uses END_CORE, 4 uses DOUBLE_LOADED."""
        fp2 = compute_required_footprint_for_core(2, "2BHK", 30.0)
        fp4 = compute_required_footprint_for_core(4, "2BHK", 30.0)
        assert fp2.core_pattern == "END_CORE"
        assert fp4.core_pattern == "DOUBLE_LOADED"

    def test_all_fsi_ratios_are_monotonic(self):
        """Higher FSI -> higher sellable/yard (monotonically increasing)."""
        fsi_values = [1.8, 2.7, 3.0, 3.6, 4.0]
        sellable_values = [interpolate_sellable_per_yard(f) for f in fsi_values]
        for i in range(1, len(sellable_values)):
            assert sellable_values[i] >= sellable_values[i - 1], (
                f"Sellable should be monotonic: FSI {fsi_values[i]} -> "
                f"{sellable_values[i]} < {sellable_values[i-1]}"
            )
