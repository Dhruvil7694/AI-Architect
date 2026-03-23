import pytest
from architecture.models.building_types import (
    BuildingType,
    get_building_type,
    get_permissible_building_types,
)

def test_get_building_type_1():
    bt = get_building_type(1)
    assert bt.id == 1
    assert bt.max_floors == 3
    assert bt.max_height_m == 10.0
    assert bt.lift_required is False

def test_get_building_type_2():
    bt = get_building_type(2)
    assert bt.id == 2
    assert bt.max_floors == 5
    assert bt.lift_required is True
    assert bt.fire_stair_required is True

def test_get_building_type_3():
    bt = get_building_type(3)
    assert bt.id == 3
    assert bt.fire_stair_required is True
    assert bt.refuge_area_required is True

def test_get_building_type_invalid():
    with pytest.raises(ValueError, match="Unknown building type"):
        get_building_type(99)

def test_permissible_types_narrow_road():
    """9m road -> only type 1 is feasible (min_road_width_m=9.0)."""
    types = get_permissible_building_types(road_width_m=9.0)
    ids = [t.id for t in types]
    assert 1 in ids
    assert 2 not in ids
    assert 3 not in ids

def test_permissible_types_wide_road():
    """30m road -> all types feasible."""
    types = get_permissible_building_types(road_width_m=30.0)
    assert len(types) == 3

def test_max_floors_capped_by_road():
    """Type 3 on 18m road -> max 30m height = 10 floors, not 23."""
    types = get_permissible_building_types(road_width_m=18.0)
    t3 = next(t for t in types if t.id == 3)
    assert t3.effective_max_floors <= 10
