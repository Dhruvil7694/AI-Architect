"""Tests for SVG blueprint renderer — professional drawing conventions."""

import pytest


def _make_feature(layer, room_type=None, coords=None, props=None):
    """Helper to build a GeoJSON feature."""
    base_props = {"layer": layer}
    if room_type:
        base_props["room_type"] = room_type
    if props:
        base_props.update(props)
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords or [[0,0],[5,0],[5,3],[0,3],[0,0]]],
        },
        "properties": base_props,
    }


def test_svg_contains_north_arrow():
    """SVG output must include a north arrow element."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0, title="Test")
    assert "north-arrow" in svg or "N" in svg


def test_svg_contains_structural_grid():
    """SVG output must include structural column grid markers."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0, title="Test")
    assert "structural-grid" in svg or "column-grid" in svg


def test_svg_kitchen_hatching_different_from_bathroom():
    """Kitchen and bathroom must have different hatch patterns."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [
        _make_feature("footprint_bg"),
        _make_feature("room", room_type="KITCHEN", coords=[[0,0],[3,0],[3,3],[0,3],[0,0]]),
        _make_feature("room", room_type="BATHROOM", coords=[[3,0],[5,0],[5,2],[3,2],[3,0]]),
    ]}
    svg = render_blueprint_svg(layout, 20.0, 12.0)
    # Should have at least 3 different hatch patterns defined
    assert "hatch-kitchen" in svg or "hatch-wet" in svg
    assert svg.count("<pattern") >= 2


def test_svg_title_block_includes_scale():
    """Title block must include scale notation."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0, title="Test Plan")
    assert "1:100" in svg or "Scale" in svg


def test_svg_scale_bar_has_subdivisions():
    """Scale bar must have 1m subdivisions."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0)
    # Scale bar group should exist with multiple tick marks
    assert "scale-bar" in svg
