"""
residential_layout/composer.py — compose_unit(zone, frame, template) pure function.

Deterministic slicing: depth budget, width budget, full-width LIVING/BEDROOM,
back-corner TOILET/KITCHEN, entry door centred. No mutation; no orchestrator in this module.
"""

from __future__ import annotations

from typing import List, Tuple, Optional

from shapely.geometry import Polygon, LineString

from floor_skeleton.models import UnitZone
from residential_layout.errors import (
    UnitZoneTooSmallError,
    LayoutCompositionError,
)
from residential_layout.frames import ComposerFrame
from residential_layout.models import UnitLayoutContract, RoomInstance
from residential_layout.templates import UnitTemplate, MARGIN_FRONTAGE_M

_TOL = 1e-6


def _band_depth_to_world(
    frame: ComposerFrame,
    band: float,
    depth: float,
) -> Tuple[float, float]:
    """Convert (band, depth) in local coords to (x, y) world."""
    ox, oy = frame.origin[0], frame.origin[1]
    rx, ry = frame.repeat_axis[0], frame.repeat_axis[1]
    dx, dy = frame.depth_axis[0], frame.depth_axis[1]
    x = ox + band * rx + depth * dx
    y = oy + band * ry + depth * dy
    return (x, y)


def _rect_to_polygon(
    frame: ComposerFrame,
    b0: float,
    b1: float,
    d0: float,
    d1: float,
) -> Polygon:
    """Rectangle (band [b0,b1], depth [d0,d1]) as Shapely polygon in world coords."""
    p0 = _band_depth_to_world(frame, b0, d0)
    p1 = _band_depth_to_world(frame, b1, d0)
    p2 = _band_depth_to_world(frame, b1, d1)
    p3 = _band_depth_to_world(frame, b0, d1)
    return Polygon([p0, p1, p2, p3])


def _segment_to_world(
    frame: ComposerFrame,
    b0: float,
    d0: float,
    b1: float,
    d1: float,
) -> LineString:
    """Line segment in (band,depth) to world LineString."""
    return LineString([
        _band_depth_to_world(frame, b0, d0),
        _band_depth_to_world(frame, b1, d1),
    ])


def _shared_boundary_length(poly_a: Polygon, poly_b: Polygon) -> float:
    """Length of shared boundary between two polygons."""
    if poly_a.is_empty or poly_b.is_empty:
        return 0.0
    try:
        inter = poly_a.boundary.intersection(poly_b.boundary)
    except Exception:
        return 0.0
    if inter.is_empty:
        return 0.0
    return inter.length


def _point_to_line_distance(
    axis: str,
    k: float,
    pt: Tuple[float, float],
) -> float:
    """Distance from pt to axis-aligned line (axis, k)."""
    if axis == "x":
        return abs(pt[0] - k)
    return abs(pt[1] - k)


def _edge_on_wet_line(
    room_poly: Polygon,
    wet_wall_line: Tuple[str, float],
) -> bool:
    """True if at least one edge of room_poly lies on wet_wall_line within tolerance."""
    axis, k = wet_wall_line[0], wet_wall_line[1]
    for i in range(len(room_poly.exterior.coords) - 1):
        p1 = room_poly.exterior.coords[i]
        p2 = room_poly.exterior.coords[i + 1]
        d1 = _point_to_line_distance(axis, k, p1)
        d2 = _point_to_line_distance(axis, k, p2)
        if d1 < _TOL and d2 < _TOL:
            return True
    return False


def compose_unit(
    zone: UnitZone,
    frame: ComposerFrame,
    template: UnitTemplate,
) -> UnitLayoutContract:
    """
    Pure function: one zone + frame + template → one UnitLayoutContract or raise.

    No mutation of inputs. All geometry in zone's local frame.
    """
    band_length_m = frame.band_length_m
    band_depth_m = frame.band_depth_m

    # Depth components
    d_living = template.room("LIVING").min_depth_m + MARGIN_FRONTAGE_M
    if "BEDROOM" in template.room_templates:
        d_bed = template.room("BEDROOM").min_depth_m
        d_toilet = template.room("TOILET").min_depth_m
        d_kitchen = template.room("KITCHEN").min_depth_m
        d_back_strip = max(d_toilet, d_kitchen)
        w_toilet = template.room("TOILET").min_width_m
        w_kitchen = template.room("KITCHEN").min_width_m
        base_required_depth = d_living + d_bed + d_back_strip
    else:
        # STUDIO
        d_toilet = template.room("TOILET").min_depth_m
        base_required_depth = d_living + d_toilet
        w_toilet = template.room("TOILET").min_width_m
        w_kitchen = 0.0
        d_bed = 0.0
        d_back_strip = d_toilet

    # 1. Base depth budget (must fit core template without passage).
    if base_required_depth > band_depth_m:
        raise UnitZoneTooSmallError(
            f"Depth budget: required_depth={base_required_depth} > band_depth_m={band_depth_m}",
            template_name=template.name,
            which="depth",
        )

    # 2. Side corridor width: allocate a PASSAGE band along width when possible.
    passage_width_m = 0.0
    # Compute minimum room-side width required by template.
    min_room_width = template.room("LIVING").min_width_m
    if "BEDROOM" in template.room_templates:
        min_room_width = max(min_room_width, template.room("BEDROOM").min_width_m)
    min_room_width = max(min_room_width, w_toilet + w_kitchen)

    max_passage_width = band_length_m - min_room_width
    if max_passage_width >= 1.0 and "BEDROOM" in template.room_templates:
        # Aim for 1.0–1.2 m passage; cap by available slack.
        passage_width_m = min(1.2, max_passage_width)

    room_zone_width_m = band_length_m - passage_width_m

    # 3. Width budget (TOILET + KITCHEN for 1BHK; TOILET only for STUDIO) in ROOM_ZONE.
    if w_toilet + w_kitchen > room_zone_width_m:
        raise LayoutCompositionError(
            f"Width budget: w_toilet + w_kitchen = {w_toilet + w_kitchen} > room_zone_width_m = {room_zone_width_m}",
            reason_code="width_budget_fail",
            template_name=template.name,
        )

    rooms: List[RoomInstance] = []

    # Depth layout: 0 = core (wet wall), band_depth_m = frontage (entry).
    # Back strip at 0..d_back_strip, then BEDROOM, then LIVING at frontage.
    depth_back_end = d_back_strip
    depth_bed_end = depth_back_end + d_bed

    # 3. PASSAGE (side corridor running full depth along one side)
    passage_poly = None
    if passage_width_m > 0.0:
        passage_poly = _rect_to_polygon(
            frame,
            0.0,
            passage_width_m,
            0.0,
            band_depth_m,
        )
        rooms.append(
            RoomInstance(room_type="PASSAGE", polygon=passage_poly, area_sqm=passage_poly.area)
        )

    # Coordinate helpers for ROOM_ZONE (rooms sit to the right of passage).
    band_start_rooms = passage_width_m
    band_end_rooms = band_length_m

    # 4. TOILET (back strip, on wet wall at depth 0, inside ROOM_ZONE)
    toilet_poly = _rect_to_polygon(
        frame,
        band_start_rooms,
        band_start_rooms + w_toilet,
        0.0,
        depth_back_end,
    )
    rooms.append(
        RoomInstance(room_type="TOILET", polygon=toilet_poly, area_sqm=toilet_poly.area)
    )

    # 5. KITCHEN (1BHK only, back strip)
    if "KITCHEN" in template.room_templates:
        kitchen_poly = _rect_to_polygon(
            frame,
            band_start_rooms + w_toilet,
            band_start_rooms + w_toilet + w_kitchen,
            0.0,
            depth_back_end,
        )
        rooms.append(
            RoomInstance(
                room_type="KITCHEN",
                polygon=kitchen_poly,
                area_sqm=kitchen_poly.area,
            )
        )

    # 6. BEDROOM (1BHK only)
    if "BEDROOM" in template.room_templates:
        bed_poly = _rect_to_polygon(
            frame,
            band_start_rooms,
            band_end_rooms,
            depth_back_end,
            depth_bed_end,
        )
        rooms.append(
            RoomInstance(room_type="BEDROOM", polygon=bed_poly, area_sqm=bed_poly.area)
        )

    # 7. LIVING (frontage, entry side at depth = band_depth_m, inside ROOM_ZONE)
    living_poly = _rect_to_polygon(
        frame,
        band_start_rooms,
        band_end_rooms,
        depth_bed_end,
        band_depth_m,
    )
    living_area = living_poly.area
    rooms.append(RoomInstance(room_type="LIVING", polygon=living_poly, area_sqm=living_area))

    # 8. Entry door: centred on LIVING front edge (depth=band_depth_m), length = door_width_m
    door_width_m = template.door_width_m
    half = door_width_m / 2.0
    mid_band = (band_start_rooms + band_end_rooms) / 2.0
    b0 = max(band_start_rooms, mid_band - half)
    b1 = min(band_end_rooms, mid_band + half)
    entry_door_segment = _segment_to_world(frame, b0, band_depth_m, b1, band_depth_m)

    # 9. Validate dimensions (min width/depth and min area after rectangle construction)
    if "BEDROOM" in template.room_templates:
        dims = [
            ("LIVING", room_zone_width_m, d_living),
            ("BEDROOM", room_zone_width_m, d_bed),
            ("TOILET", w_toilet, d_back_strip),
            ("KITCHEN", w_kitchen, d_back_strip),
        ]
    else:
        dims = [
            ("LIVING", room_zone_width_m, d_living),
            ("TOILET", w_toilet, d_back_strip),
        ]
    for rtype, w_design, d_design in dims:
        rt = template.room(rtype)
        if w_design < rt.min_width_m - _TOL or d_design < rt.min_depth_m - _TOL:
            raise LayoutCompositionError(
                f"Room {rtype} below min dimensions: w={w_design} d={d_design}",
                reason_code="room_min_dim_fail",
                template_name=template.name,
                room_type=rtype,
            )
    for ri in rooms:
        # PASSAGE has no template constraints; treat it as circulation only.
        if ri.room_type == "PASSAGE":
            continue
        rt = template.room(ri.room_type)
        if rt.min_area_sqm is not None and ri.area_sqm < rt.min_area_sqm - _TOL:
            raise LayoutCompositionError(
                f"Room {ri.room_type} area {ri.area_sqm} < min_area_sqm {rt.min_area_sqm}",
                reason_code="room_min_dim_fail",
                template_name=template.name,
                room_type=ri.room_type,
            )

    # 10. Connectivity: LIVING touches entry edge; every other room touches
    # LIVING, BEDROOM, PASSAGE, or entry edge.
    entry_edge_poly = Polygon([
        _band_depth_to_world(frame, 0.0, band_depth_m),
        _band_depth_to_world(frame, band_length_m, band_depth_m),
        _band_depth_to_world(frame, band_length_m, band_depth_m - _TOL),
        _band_depth_to_world(frame, 0.0, band_depth_m - _TOL),
    ])
    living_poly_ref = next(r.polygon for r in rooms if r.room_type == "LIVING")
    bed_poly_ref = next((r.polygon for r in rooms if r.room_type == "BEDROOM"), None)
    passage_poly_ref = next((r.polygon for r in rooms if r.room_type == "PASSAGE"), None)
    living_entry = _shared_boundary_length(living_poly_ref, entry_edge_poly)
    if living_entry < _TOL:
        raise LayoutCompositionError(
            "LIVING does not touch entry edge",
            reason_code="connectivity_fail",
            template_name=template.name,
            room_type="LIVING",
        )
    for ri in rooms:
        if ri.room_type == "LIVING":
            continue
        with_living = _shared_boundary_length(ri.polygon, living_poly_ref)
        with_bed = _shared_boundary_length(ri.polygon, bed_poly_ref) if bed_poly_ref else 0.0
        with_passage = _shared_boundary_length(ri.polygon, passage_poly_ref) if passage_poly_ref else 0.0
        with_entry = _shared_boundary_length(ri.polygon, entry_edge_poly)
        if (
            with_living < _TOL
            and with_bed < _TOL
            and with_passage < _TOL
            and with_entry < _TOL
        ):
            raise LayoutCompositionError(
                f"Room {ri.room_type} does not touch LIVING, BEDROOM, or entry edge",
                reason_code="connectivity_fail",
                template_name=template.name,
                room_type=ri.room_type,
            )

    # 11. Wet wall alignment: TOILET and KITCHEN have edge on wet_wall_line
    for ri in rooms:
        if ri.room_type in ("TOILET", "KITCHEN"):
            if not _edge_on_wet_line(ri.polygon, frame.wet_wall_line):
                raise LayoutCompositionError(
                    f"Room {ri.room_type} not aligned to wet_wall_line",
                    reason_code="wet_wall_alignment_fail",
                    template_name=template.name,
                    room_type=ri.room_type,
                )

    # 12. All rooms inside zone (with small tolerance)
    zone_poly = zone.polygon
    zone_buf = zone_poly.buffer(_TOL)
    for ri in rooms:
        if not zone_buf.covers(ri.polygon):
            raise LayoutCompositionError(
                f"Room {ri.room_type} not inside zone",
                reason_code="room_min_dim_fail",
                template_name=template.name,
                room_type=ri.room_type,
            )

    # Output order: keep canonical order for presentation.
    if "BEDROOM" in template.room_templates:
        order = ["LIVING", "PASSAGE", "BEDROOM", "TOILET", "KITCHEN"]
    else:
        order = ["LIVING", "TOILET"]
    ordered_rooms = [next(r for r in rooms if r.room_type == t) for t in order if any(r.room_type == t for r in rooms)]

    return UnitLayoutContract(
        rooms=ordered_rooms,
        entry_door_segment=entry_door_segment,
        unit_id=None,
    )
