from services.core_engine import (
    LIFT_SHAFT_D,
    STAIR_D,
    build_core_layout,
)


def _rects_overlap(a, b):
    return not (
        a["x"] + a["w"] <= b["x"]
        or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"]
        or b["y"] + b["h"] <= a["y"]
    )


def test_build_core_layout_centers_core_and_counts_components():
    core = build_core_layout(
        floor_width=30.0,
        floor_depth=20.0,
        n_lifts=2,
        n_stairs=2,
    )

    assert round(core["x"] + core["w"] / 2.0, 2) == 15.0
    assert round(core["y"] + core["h"] / 2.0, 2) == 10.0
    assert len(core["lifts"]) == 2
    assert len(core["stairs"]) == 2
    assert core["lobby"]["h"] > 0


def test_build_core_layout_has_no_component_overlaps():
    core = build_core_layout(
        floor_width=28.0,
        floor_depth=22.0,
        n_lifts=2,
        n_stairs=1,
    )

    components = core["lifts"] + core["stairs"] + [core["lobby"]]
    for i, a in enumerate(components):
        for b in components[i + 1 :]:
            assert not _rects_overlap(a, b)

    for lift in core["lifts"]:
        assert lift["h"] == LIFT_SHAFT_D
    for stair in core["stairs"]:
        assert stair["h"] == STAIR_D
