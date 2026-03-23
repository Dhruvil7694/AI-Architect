import pytest
from architecture.models.building_types import get_permissible_building_types
from architecture.models.core_config import get_core_configs
from architecture.models.sellable_area import compute_sellable_area


class TestFeasibilityNewInputs:
    def test_feasibility_returns_building_types(self):
        types = get_permissible_building_types(road_width_m=18.0)
        assert len(types) > 0
        for bt in types:
            assert hasattr(bt, "effective_max_floors")
            assert bt.effective_max_floors > 0

    def test_feasibility_returns_core_configs(self):
        configs = get_core_configs()
        assert len(configs) == 3
        units = [c.units_per_core for c in configs]
        assert 2 in units
        assert 4 in units
        assert 6 in units

    def test_sellable_estimate_in_feasibility(self):
        summary = compute_sellable_area(
            plot_area_sq_yards=4000.0,
            achieved_fsi=3.6,
            segment="mid",
        )
        assert summary.total_sellable_sqft == pytest.approx(216000.0, rel=0.01)
