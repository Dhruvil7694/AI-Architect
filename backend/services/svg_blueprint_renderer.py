"""
services/svg_blueprint_renderer.py
-------------------------------------
Render a GeoJSON FloorPlanLayout FeatureCollection as a clean black & white
architectural SVG blueprint.

All coordinates in the input GeoJSON are in local metres (origin 0,0).
The SVG uses a Y-flip (SVG Y grows down, architecture Y grows up).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape


# ---- SVG layout constants ----
MARGIN = 2.0       # metres margin around floor plate for dimension lines
SCALE = 40.0       # pixels per metre (40px/m = good detail)
FONT_ROOM = 8      # px — room labels
FONT_UNIT = 10     # px — unit type labels
FONT_DIM = 6       # px — dimension text

# ---- Layer render order (bottom to top) ----
LAYER_ORDER = [
    "footprint_bg", "corridor", "core", "balcony", "room",
    "wall", "door_opening", "door_arc", "door", "window",
    "stair", "stair_tread", "stair_arrow",
    "lift", "lift_door", "lobby",
]

# ---- Hatch pattern IDs ----
HATCH_WET = "hatch-wet"
HATCH_STAIR = "hatch-stair"

# Room types that get wet-area hatching
WET_ROOMS = {"BATHROOM", "TOILET", "KITCHEN", "UTILITY"}

# Room types rendered with a light-grey tint (circulation / service)
CIRC_ROOMS = {"FOYER", "PASSAGE"}


def render_blueprint_svg(
    layout: Dict[str, Any],
    floor_width_m: float,
    floor_depth_m: float,
    title: str = "",
) -> str:
    """
    Render a GeoJSON FeatureCollection as an architectural SVG blueprint.

    Returns a complete SVG string.
    """
    features = layout.get("features", [])
    if not features:
        return _empty_svg(floor_width_m, floor_depth_m, title)

    # SVG dimensions
    svg_w = (floor_width_m + 2 * MARGIN) * SCALE
    svg_h = (floor_depth_m + 2 * MARGIN) * SCALE

    parts: List[str] = []
    parts.append(_svg_header(svg_w, svg_h))
    parts.append(_svg_defs())

    # Group features by layer
    by_layer: Dict[str, List[Dict]] = {}
    for f in features:
        layer = f.get("properties", {}).get("layer", "unknown")
        by_layer.setdefault(layer, []).append(f)

    # Render layers in order
    for layer in LAYER_ORDER:
        layer_features = by_layer.get(layer, [])
        if not layer_features:
            continue
        parts.append(f'  <g class="layer-{layer}">')
        for feat in layer_features:
            parts.append(_render_feature(feat, layer, floor_depth_m))
        parts.append("  </g>")

    # Room labels
    parts.append('  <g class="labels">')
    for feat in by_layer.get("room", []):
        parts.append(_render_room_label(feat, floor_depth_m))
    for feat in by_layer.get("unit", []):
        parts.append(_render_unit_label(feat, floor_depth_m))
    parts.append("  </g>")

    # Structural column grid (rendered behind labels)
    parts.insert(3, _render_structural_grid(floor_width_m, floor_depth_m))

    # Dimension lines
    parts.append(_render_dimensions(floor_width_m, floor_depth_m))

    # Scale bar
    parts.append(_render_scale_bar(floor_width_m, floor_depth_m))

    # North arrow
    parts.append(_render_north_arrow(floor_width_m, floor_depth_m))

    # Title block
    if title:
        parts.append(_render_title(title, svg_w, svg_h))

    parts.append("</svg>")
    return "\n".join(parts)


# ---- SVG scaffolding ----

def _svg_header(w: float, h: float) -> str:
    # width/height omitted intentionally — the viewBox drives intrinsic ratio
    # and the frontend zoom container scales the SVG via CSS transform.
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w:.0f} {h:.0f}" '
        f'width="{w:.0f}" height="{h:.0f}" '
        f'style="display:block;background:#fff">\n'
    )


def _svg_defs() -> str:
    """SVG defs: distinct hatch patterns per room type + markers."""
    return """\
  <defs>
    <pattern id="hatch-wet" patternUnits="userSpaceOnUse" width="6" height="6"
             patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="6" stroke="#b0c4de" stroke-width="0.6"/>
      <line x1="3" y1="0" x2="3" y2="6" stroke="#b0c4de" stroke-width="0.4"/>
    </pattern>
    <pattern id="hatch-kitchen" patternUnits="userSpaceOnUse" width="6" height="6"
             patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="6" stroke="#e8c090" stroke-width="0.6"/>
    </pattern>
    <pattern id="hatch-utility" patternUnits="userSpaceOnUse" width="4" height="4">
      <circle cx="2" cy="2" r="0.6" fill="#ccc"/>
    </pattern>
    <pattern id="hatch-stair" patternUnits="userSpaceOnUse" width="4" height="8">
      <line x1="0" y1="0" x2="4" y2="0" stroke="#666" stroke-width="0.5"/>
      <line x1="0" y1="4" x2="4" y2="4" stroke="#666" stroke-width="0.5"/>
    </pattern>
    <marker id="arrow-stair" markerWidth="6" markerHeight="6"
            refX="3" refY="3" orient="auto">
      <path d="M0,0 L0,6 L6,3 Z" fill="#444"/>
    </marker>
  </defs>"""


def _empty_svg(w: float, h: float, title: str) -> str:
    sw, sh = (w + 2 * MARGIN) * SCALE, (h + 2 * MARGIN) * SCALE
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sw:.0f} {sh:.0f}" '
        f'width="{sw:.0f}" height="{sh:.0f}" style="background:#fff">'
        f'<text x="{sw/2}" y="{sh/2}" text-anchor="middle" font-size="14" '
        f'fill="#999">No floor plan data</text></svg>'
    )


# ---- Coordinate transform ----

def _to_svg(x: float, y: float, floor_depth_m: float) -> Tuple[float, float]:
    """Convert local-metre coords to SVG coords (Y-flip + margin offset)."""
    sx = (x + MARGIN) * SCALE
    sy = (floor_depth_m - y + MARGIN) * SCALE
    return sx, sy


def _polygon_to_svg_path(coords: List[List[float]], floor_depth_m: float) -> str:
    """Convert a GeoJSON polygon ring to an SVG path string."""
    if not coords or len(coords) < 3:
        return ""
    pts = [_to_svg(c[0], c[1], floor_depth_m) for c in coords]
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for px, py in pts[1:]:
        d += f" L{px:.1f},{py:.1f}"
    d += " Z"
    return d


# ---- Feature rendering ----

def _render_feature(feat: Dict, layer: str, floor_depth_m: float) -> str:
    """Render a single GeoJSON feature as SVG."""
    if layer == "door_arc":
        return _render_door_arc(feat, floor_depth_m)
    if layer == "stair_arrow":
        return _render_stair_arrow(feat, floor_depth_m)

    geom = feat.get("geometry", {})
    props = feat.get("properties", {})
    coords_list = geom.get("coordinates", [])

    if geom.get("type") != "Polygon" or not coords_list:
        return ""

    ring = coords_list[0]
    path = _polygon_to_svg_path(ring, floor_depth_m)
    if not path:
        return ""

    style = _get_style(layer, props)
    return f'    <path d="{path}" {style}/>'


def _render_stair_arrow(feat: Dict, floor_depth_m: float) -> str:
    """Render a stair flight-direction arrow as an SVG line with arrowhead."""
    geom = feat.get("geometry", {})
    coords = geom.get("coordinates", [])
    if len(coords) < 2:
        return ""
    x1, y1 = _to_svg(coords[0][0], coords[0][1], floor_depth_m)
    x2, y2 = _to_svg(coords[1][0], coords[1][1], floor_depth_m)
    return (
        f'    <line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="#444" stroke-width="1" '
        f'marker-end="url(#arrow-stair)"/>'
    )


def _render_door_arc(feat: Dict, floor_depth_m: float) -> str:
    """
    Render a door arc as a smooth SVG sector path using stored arc metadata.

    Coordinate math (Y-up, 0°=east, CCW positive):
      In SVG (Y-down) the Y component of any arc point is negated, so:
        svg_point = (cx + r*cos(θ),  scy - r*sin(θ))
      Sweep direction also flips: CCW in math (Δθ>0) → CCW in SVG (sweep=0)
                                  CW  in math (Δθ<0) → CW  in SVG (sweep=1)
    """
    props = feat.get("properties", {})
    cx    = props.get("arc_cx")
    cy    = props.get("arc_cy")
    r     = props.get("arc_r")
    s_deg = props.get("arc_start")
    e_deg = props.get("arc_end")

    if cx is None or r is None or r <= 0:
        return ""

    scx, scy = _to_svg(cx, cy, floor_depth_m)
    r_px = r * SCALE

    sa = math.radians(s_deg)
    ea = math.radians(e_deg)

    # Arc start/end in SVG px (Y-flip: negate sin)
    ax1 = scx + r_px * math.cos(sa)
    ay1 = scy - r_px * math.sin(sa)
    ax2 = scx + r_px * math.cos(ea)
    ay2 = scy - r_px * math.sin(ea)

    delta = e_deg - s_deg
    # CCW in math (delta>0) → CCW in SVG (sweep=0)
    # CW  in math (delta<0) → CW  in SVG (sweep=1)
    sweep = 0 if delta > 0 else 1
    large = 1 if abs(delta) > 180 else 0

    d = (
        f"M{scx:.1f},{scy:.1f} "
        f"L{ax1:.1f},{ay1:.1f} "
        f"A{r_px:.1f},{r_px:.1f} 0 {large},{sweep} {ax2:.1f},{ay2:.1f} "
        f"Z"
    )
    return (
        f'    <path d="{d}" '
        f'fill="rgba(0,0,0,0.04)" stroke="#555" stroke-width="0.6"/>'
    )


def _get_style(layer: str, props: Dict) -> str:
    """Get SVG style attributes for a layer."""
    if layer == "footprint_bg":
        # White floor plate with a bold perimeter line
        return 'fill="#ffffff" stroke="#000" stroke-width="2.5"'
    elif layer == "corridor":
        # Light grey shared circulation
        return 'fill="#ebebeb" stroke="#aaa" stroke-width="0.5"'
    elif layer == "core":
        return 'fill="#d8d8d8" stroke="#555" stroke-width="1"'
    elif layer == "stair":
        return f'fill="url(#{HATCH_STAIR})" stroke="#444" stroke-width="1"'
    elif layer == "lift":
        return 'fill="#333" stroke="#000" stroke-width="1"'
    elif layer == "lobby":
        return 'fill="none" stroke="#666" stroke-width="0.8" stroke-dasharray="4 2"'
    elif layer == "room":
        room_type = props.get("room_type", "").upper()
        if room_type in ("BATHROOM", "TOILET"):
            return 'fill="url(#hatch-wet)" stroke="#444" stroke-width="0.5"'
        if room_type == "KITCHEN":
            return 'fill="url(#hatch-kitchen)" stroke="#444" stroke-width="0.5"'
        if room_type == "UTILITY":
            return 'fill="url(#hatch-utility)" stroke="#444" stroke-width="0.4"'
        if room_type in CIRC_ROOMS:
            return 'fill="#f0f0f0" stroke="#444" stroke-width="0.4"'
        return 'fill="#ffffff" stroke="#444" stroke-width="0.4"'
    elif layer == "wall":
        wall_type = props.get("wall_type", "external")
        if wall_type == "internal":
            return 'fill="#333" stroke="#222" stroke-width="0.3"'
        if wall_type == "entry":
            return 'fill="#222" stroke="#000" stroke-width="0.4"'
        if wall_type == "parapet":
            return 'fill="#555" stroke="#444" stroke-width="0.2"'
        # External walls — solid and heavy
        return 'fill="#111" stroke="#000" stroke-width="0.6"'
    elif layer == "door_opening":
        # White rectangle punched over the wall to create a visible gap
        return 'fill="#ffffff" stroke="none"'
    elif layer == "door":
        # Door leaf — thin dark panel
        return 'fill="#444" stroke="#222" stroke-width="0.3"'
    elif layer == "window":
        # Classic window: narrow bright-blue glass line on the wall face
        return 'fill="#cde8ff" stroke="#4a90d9" stroke-width="1"'
    elif layer == "balcony":
        return 'fill="none" stroke="#555" stroke-width="0.8" stroke-dasharray="4 2"'
    elif layer == "stair_tread":
        return 'fill="#555" stroke="none"'
    elif layer == "lift_door":
        return 'fill="#fff" stroke="#fff" stroke-width="1"'
    elif layer == "unit":
        # No unit outline — walls make the boundary clear
        return 'fill="none" stroke="none"'
    return 'fill="none" stroke="#ccc" stroke-width="0.5"'


# ---- Labels ----

def _render_room_label(feat: Dict, floor_depth_m: float) -> str:
    """
    Render a three-line room label at the room centroid:
      Line 1 — room name (bold)
      Line 2 — W × D in metres  (e.g. "3.30 × 3.52")
      Line 3 — area in m²

    Skips small rooms (< 1.5 m²) to avoid clutter.
    """
    props = feat.get("properties", {})
    geom = feat.get("geometry", {})
    coords = geom.get("coordinates", [[]])[0]
    if len(coords) < 3:
        return ""

    area = props.get("area_sqm", 0) or 0
    if area < 1.5:
        return ""

    cx = sum(c[0] for c in coords) / len(coords)
    cy = sum(c[1] for c in coords) / len(coords)
    sx, sy = _to_svg(cx, cy, floor_depth_m)

    label = props.get("label", props.get("room_type", ""))
    w_m   = props.get("width_m")
    d_m   = props.get("depth_m")
    line_h = FONT_ROOM + 2

    # Three-line label: name / W×D / area
    # Offset so the block is vertically centred on the centroid
    n_lines = 1 + (1 if (w_m and d_m) else 0) + (1 if area else 0)
    y0 = sy - (n_lines - 1) * line_h / 2

    name_el = (
        f'      <tspan x="{sx:.1f}" y="{y0:.1f}" font-weight="600">'
        f'{xml_escape(str(label))}</tspan>'
    )
    dim_el = ""
    if w_m and d_m:
        dim_el = (
            f'      <tspan x="{sx:.1f}" dy="{line_h}" '
            f'font-size="{FONT_ROOM - 1}" fill="#444">'
            f'{w_m:.2f} \u00d7 {d_m:.2f} m</tspan>'
        )
    area_el = ""
    if area:
        area_el = (
            f'      <tspan x="{sx:.1f}" dy="{line_h}" '
            f'font-size="{FONT_ROOM - 1}" fill="#666">'
            f'{area:.1f} m\u00b2</tspan>'
        )

    return (
        f'    <text x="{sx:.1f}" y="{y0:.1f}" text-anchor="middle" '
        f'font-size="{FONT_ROOM}" font-family="Arial,sans-serif" fill="#222">'
        f'{name_el}{dim_el}{area_el}</text>'
    )


def _render_unit_label(feat: Dict, floor_depth_m: float) -> str:
    """Render a bold unit-type label at the centre of the unit footprint."""
    props = feat.get("properties", {})
    geom = feat.get("geometry", {})
    coords = geom.get("coordinates", [[]])[0]
    if len(coords) < 3:
        return ""

    cx = sum(c[0] for c in coords) / len(coords)
    cy = sum(c[1] for c in coords) / len(coords)
    sx, sy = _to_svg(cx, cy, floor_depth_m)

    utype = props.get("unit_type", "")
    uid   = props.get("unit_id", "")
    carpet = props.get("carpet_area_sqm")
    label = f"{uid} ({utype})" if uid and utype else (utype or uid)
    sub   = f"Carpet {carpet:.0f} m²" if carpet else ""

    lines = [
        f'    <text text-anchor="middle" font-family="Arial,sans-serif" fill="#111">',
        f'      <tspan x="{sx:.1f}" y="{sy:.1f}" font-size="{FONT_UNIT}" '
        f'font-weight="bold">{xml_escape(str(label))}</tspan>',
    ]
    if sub:
        lines.append(
            f'      <tspan x="{sx:.1f}" dy="{FONT_UNIT + 1}" '
            f'font-size="{FONT_UNIT - 1}" fill="#555">{xml_escape(sub)}</tspan>'
        )
    lines.append("    </text>")
    return "\n".join(lines)


# ---- Dimension lines ----

def _render_dimensions(floor_width_m: float, floor_depth_m: float) -> str:
    """Render overall dimension lines along exterior edges."""
    lines: List[str] = []
    lines.append('  <g class="dimensions" stroke="#000" stroke-width="0.5" fill="#000">')

    # Bottom dimension (width)
    y_dim = -MARGIN * 0.5
    x0, y0 = _to_svg(0, y_dim, floor_depth_m)
    x1, y1 = _to_svg(floor_width_m, y_dim, floor_depth_m)
    lines.append(f'    <line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}"/>')
    # Ticks
    for x in [0, floor_width_m]:
        sx, sy = _to_svg(x, y_dim, floor_depth_m)
        lines.append(f'    <line x1="{sx:.1f}" y1="{sy-4:.1f}" x2="{sx:.1f}" y2="{sy+4:.1f}"/>')
    # Label
    mx = (x0 + x1) / 2
    lines.append(
        f'    <text x="{mx:.1f}" y="{y0 - 6:.1f}" text-anchor="middle" '
        f'font-size="{FONT_DIM}" font-family="Arial,sans-serif">'
        f'{floor_width_m:.1f} m</text>'
    )

    # Left dimension (depth)
    x_dim = -MARGIN * 0.5
    x0, y0 = _to_svg(x_dim, 0, floor_depth_m)
    x1, y1 = _to_svg(x_dim, floor_depth_m, floor_depth_m)
    lines.append(f'    <line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}"/>')
    for y in [0, floor_depth_m]:
        sx, sy = _to_svg(x_dim, y, floor_depth_m)
        lines.append(f'    <line x1="{sx-4:.1f}" y1="{sy:.1f}" x2="{sx+4:.1f}" y2="{sy:.1f}"/>')
    my = (y0 + y1) / 2
    lines.append(
        f'    <text x="{x0 - 8:.1f}" y="{my:.1f}" text-anchor="middle" '
        f'font-size="{FONT_DIM}" font-family="Arial,sans-serif" '
        f'transform="rotate(-90 {x0 - 8:.1f} {my:.1f})">'
        f'{floor_depth_m:.1f} m</text>'
    )

    lines.append("  </g>")
    return "\n".join(lines)


# ---- Scale bar ----

def _render_scale_bar(floor_width_m: float, floor_depth_m: float) -> str:
    """Render a scale bar at bottom-left with 1m subdivisions."""
    bar_m = 5.0 if floor_width_m > 15 else 2.0
    x0, y0 = _to_svg(0, -MARGIN * 0.8, floor_depth_m)
    bar_px = bar_m * SCALE

    parts = ['  <g class="scale-bar">']
    # Main bar
    parts.append(
        f'    <line x1="{x0:.1f}" y1="{y0:.1f}" '
        f'x2="{x0 + bar_px:.1f}" y2="{y0:.1f}" '
        f'stroke="#000" stroke-width="1.5"/>'
    )
    # End ticks + 1m subdivision ticks
    for i in range(int(bar_m) + 1):
        tick_x = x0 + i * SCALE
        tick_h = 5 if i == 0 or i == int(bar_m) else 3
        parts.append(
            f'    <line x1="{tick_x:.1f}" y1="{y0 - tick_h:.1f}" '
            f'x2="{tick_x:.1f}" y2="{y0 + tick_h:.1f}" stroke="#000" stroke-width="1"/>'
        )
    # Label
    parts.append(
        f'    <text x="{x0 + bar_px / 2:.1f}" y="{y0 + 14:.1f}" '
        f'text-anchor="middle" font-size="{FONT_DIM}" '
        f'font-family="Arial,sans-serif">{bar_m:.0f} m</text>'
    )
    parts.append('  </g>')
    return "\n".join(parts)


# ---- North arrow ----

def _render_north_arrow(floor_width_m: float, floor_depth_m: float) -> str:
    """Render a north arrow at the top-right corner."""
    ax, ay = _to_svg(floor_width_m + MARGIN * 0.6, floor_depth_m - 0.5, floor_depth_m)
    arrow_h = 25  # px
    return (
        f'  <g class="north-arrow" transform="translate({ax:.0f},{ay:.0f})">\n'
        f'    <line x1="0" y1="{arrow_h}" x2="0" y2="0" stroke="#333" stroke-width="1.5"/>\n'
        f'    <polygon points="-5,8 0,0 5,8" fill="#333"/>\n'
        f'    <text x="0" y="-5" text-anchor="middle" font-size="10" '
        f'font-weight="bold" font-family="Arial,sans-serif" fill="#333">N</text>\n'
        f'  </g>'
    )


# ---- Structural column grid ----

def _render_structural_grid(floor_width_m: float, floor_depth_m: float,
                             grid_m: float = 4.5) -> str:
    """Render structural column grid as dashed lines with small circles at intersections."""
    lines = ['  <g class="structural-grid column-grid">']

    # Vertical grid lines
    x = 0.0
    while x <= floor_width_m + 0.01:
        sx0, sy0 = _to_svg(x, 0, floor_depth_m)
        sx1, sy1 = _to_svg(x, floor_depth_m, floor_depth_m)
        lines.append(
            f'    <line x1="{sx0:.1f}" y1="{sy0:.1f}" x2="{sx1:.1f}" y2="{sy1:.1f}" '
            f'stroke="#ccc" stroke-width="0.3" stroke-dasharray="4 4"/>'
        )
        x += grid_m

    # Horizontal grid lines
    y = 0.0
    while y <= floor_depth_m + 0.01:
        sx0, sy0 = _to_svg(0, y, floor_depth_m)
        sx1, sy1 = _to_svg(floor_width_m, y, floor_depth_m)
        lines.append(
            f'    <line x1="{sx0:.1f}" y1="{sy0:.1f}" x2="{sx1:.1f}" y2="{sy1:.1f}" '
            f'stroke="#ccc" stroke-width="0.3" stroke-dasharray="4 4"/>'
        )
        y += grid_m

    # Column circles at intersections
    x = 0.0
    while x <= floor_width_m + 0.01:
        y = 0.0
        while y <= floor_depth_m + 0.01:
            sx, sy = _to_svg(x, y, floor_depth_m)
            lines.append(
                f'    <circle cx="{sx:.1f}" cy="{sy:.1f}" r="3" '
                f'fill="none" stroke="#999" stroke-width="0.5" stroke-dasharray="2 2"/>'
            )
            y += grid_m
        x += grid_m

    lines.append('  </g>')
    return "\n".join(lines)


# ---- Title block ----

def _render_title(title: str, svg_w: float, svg_h: float) -> str:
    title_with_scale = f"{title} — Scale 1:100" if "Scale" not in title else title
    return (
        f'  <text x="{svg_w - 10:.1f}" y="{svg_h - 10:.1f}" '
        f'text-anchor="end" font-size="10" font-weight="bold" '
        f'font-family="Arial,sans-serif" fill="#333">'
        f'{xml_escape(title_with_scale)}</text>'
    )
