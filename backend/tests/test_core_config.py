import pytest
from architecture.models.core_config import (
    CoreConfig,
    get_core_configs,
    get_core_config,
    compute_required_footprint_for_core,
)

def test_get_core_config_2():
    cc = get_core_config(units_per_core=2)
    assert cc.units_per_core == 2
    assert cc.segment == "premium"

def test_get_core_config_4():
    cc = get_core_config(units_per_core=4)
    assert cc.units_per_core == 4
    assert cc.segment == "mid"

def test_get_core_config_6():
    cc = get_core_config(units_per_core=6)
    assert cc.units_per_core == 6
    assert cc.segment == "budget"

def test_get_core_config_invalid():
    with pytest.raises(ValueError):
        get_core_config(units_per_core=5)

def test_footprint_2_units_3bhk():
    """2 units × 3BHK per core needs ~19m corridor + core."""
    result = compute_required_footprint_for_core(
        units_per_core=2,
        unit_type="3BHK",
        building_height_m=30.0,
    )
    assert result.min_footprint_width_m > 0
    assert result.min_footprint_depth_m > 0
    assert result.core_pattern in ("END_CORE", "SINGLE_LOADED", "DOUBLE_LOADED")

def test_footprint_4_units_2bhk():
    """4 units × 2BHK per core — double loaded corridor."""
    result = compute_required_footprint_for_core(
        units_per_core=4,
        unit_type="2BHK",
        building_height_m=30.0,
    )
    assert result.core_pattern == "DOUBLE_LOADED"
    assert result.estimated_floor_area_sqm > 0
