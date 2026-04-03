from services.core_engine import build_core_layout
from services.unit_block_engine import CORRIDOR_W, generate_unit_blocks


def _rects_overlap(a, b):
    return not (
        a["x"] + a["w"] <= b["x"]
        or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"]
        or b["y"] + b["h"] <= a["y"]
    )


def test_generate_unit_blocks_produces_north_south_bands():
    core = build_core_layout(
        floor_width=32.0,
        floor_depth=20.0,
        n_lifts=2,
        n_stairs=2,
    )

    result = generate_unit_blocks(
        floor_width=32.0,
        floor_depth=20.0,
        core=core,
        units_per_core=6,
    )
    units = result["units"]

    assert len(units) == 6
    assert sum(1 for u in units if u["side"] == "south") == 3
    assert sum(1 for u in units if u["side"] == "north") == 3
    assert result["corridor"]["h"] == CORRIDOR_W


def test_generate_unit_blocks_respect_core_gap_and_no_overlaps():
    core = build_core_layout(
        floor_width=30.0,
        floor_depth=18.0,
        n_lifts=1,
        n_stairs=2,
    )

    result = generate_unit_blocks(
        floor_width=30.0,
        floor_depth=18.0,
        core=core,
        units_per_core=4,
    )
    units = result["units"]
    corridor = result["corridor"]

    for i, a in enumerate(units):
        assert not _rects_overlap(a, core)
        assert not _rects_overlap(a, corridor)
        for b in units[i + 1 :]:
            assert not _rects_overlap(a, b)
