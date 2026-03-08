"""
renderer_svg.py
---------------
Convert the final room rectangle layout into a professional architectural SVG.

Visual conventions
------------------
- Scale:        60 px / metre
- Walls:        exterior 4 px black, internal partition 2 px dark grey
- Room fills:   colour-coded by type (see ROOM_COLORS)
- Labels:       room name (bold) + area in m²
- Doors:        quarter-circle arc + door-leaf line in the shared wall
- Windows:      three parallel cyan lines in a gap on the exterior wall face
- Balconies:    dashed green outline (open-to-sky)
- Passage:      diagonal hatch + width label
- North arrow:  top-right corner
- Scale bar:    bottom-right
- Compliance:   red overlay on failing rooms
"""

from __future__ import annotations

import html
import math
from typing import Any, Dict, List, Optional

import networkx as nx

from floorplan_engine.room_geometry_solver import (
    is_exterior,
    shared_edge_length,
)

# ─── Visual constants ──────────────────────────────────────────────────────────
PX_PER_M    = 60       # scale factor
MARGIN_PX   = 50       # canvas margin around the flat
WALL_EXT    = 4        # exterior wall stroke width (px)
WALL_INT    = 1.5      # internal partition stroke width (px)
FONT_MAIN   = 10       # room label font size (px)
FONT_SMALL  = 8        # area sub-label font size (px)
DOOR_R_M    = 0.80     # door swing radius (metres)

# Room-type → (fill colour, stroke colour)
ROOM_COLORS: Dict[str, tuple] = {
    "entry":    ("#f1f5f9", "#94a3b8"),
    "living":   ("#dbeafe", "#3b82f6"),
    "dining":   ("#e0f2fe", "#0ea5e9"),
    "kitchen":  ("#fef9c3", "#ca8a04"),
    "bedroom":  ("#dcfce7", "#16a34a"),
    "bathroom": ("#f3e8ff", "#9333ea"),
    "passage":  ("#e2e8f0", "#64748b"),
    "balcony":  ("#f0fdf4", "#4ade80"),
    "utility":  ("#fff7ed", "#f97316"),
    "room":     ("#f8fafc", "#94a3b8"),
}

COMPLIANCE_FAIL_FILL   = "rgba(239,68,68,0.18)"
COMPLIANCE_FAIL_STROKE = "#ef4444"


# ─── Coordinate helpers ────────────────────────────────────────────────────────

def _m2p(metres: float) -> float:
    """Convert metres → pixels."""
    return metres * PX_PER_M


def _rx(x_m: float) -> float:
    """Room x (bottom-left) in metres → SVG x-pixel (top-left origin)."""
    return MARGIN_PX + _m2p(x_m)


def _ry(y_m: float, unit_d: float) -> float:
    """Room y (bottom-left, south=0) in metres → SVG y-pixel (top=north)."""
    return MARGIN_PX + _m2p(unit_d - y_m)


def _ry_top(y_m: float, h_m: float, unit_d: float) -> float:
    """Top edge of a room rect in SVG pixel space."""
    return _ry(y_m + h_m, unit_d)


# ─── SVG element builders ──────────────────────────────────────────────────────

def _rect_elem(
    x_px: float, y_px: float, w_px: float, h_px: float,
    fill: str, stroke: str, sw: float,
    extra: str = "",
    rx: float = 0,
) -> str:
    return (
        f'<rect x="{x_px:.1f}" y="{y_px:.1f}" '
        f'width="{w_px:.1f}" height="{h_px:.1f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
        f'rx="{rx}" {extra}/>\n'
    )


def _text_elem(
    x_px: float, y_px: float, text: str,
    font_size: int = FONT_MAIN,
    weight: str = "normal",
    fill: str = "#1e293b",
    anchor: str = "middle",
) -> str:
    return (
        f'<text x="{x_px:.1f}" y="{y_px:.1f}" '
        f'font-family="Inter,Arial,sans-serif" font-size="{font_size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
        f'dominant-baseline="middle">{html.escape(text)}</text>\n'
    )


def _door_symbol(
    r: Dict, adj_r: Dict, unit_d: float,
) -> str:
    """
    Draw a door between two adjacent rooms.
    Detects which wall is shared, places a gap + leaf line + quarter-circle arc.
    """
    tol = 0.05
    svg = ""
    door_r_px = _m2p(DOOR_R_M)

    # Check right wall of r → left wall of adj_r
    if abs((r["x"] + r["w"]) - adj_r["x"]) < tol:
        # Shared vertical edge at x = r["x"]+r["w"]
        shared_y0 = max(r["y"], adj_r["y"])
        shared_y1 = min(r["y"] + r["h"], adj_r["y"] + adj_r["h"])
        if shared_y1 - shared_y0 < 0.6:
            return ""
        mid_y = (shared_y0 + shared_y1) / 2
        wall_x_px = _rx(r["x"] + r["w"])
        mid_y_px  = _ry(mid_y, unit_d)
        svg += (
            f'<line x1="{wall_x_px:.1f}" y1="{mid_y_px - door_r_px/2:.1f}" '
            f'x2="{wall_x_px:.1f}" y2="{mid_y_px + door_r_px/2:.1f}" '
            f'stroke="white" stroke-width="4"/>\n'
        )
        svg += (
            f'<path d="M{wall_x_px:.1f},{mid_y_px:.1f} '
            f'L{wall_x_px - door_r_px:.1f},{mid_y_px:.1f} '
            f'A{door_r_px:.1f},{door_r_px:.1f} 0 0,1 '
            f'{wall_x_px:.1f},{mid_y_px - door_r_px:.1f}" '
            f'fill="none" stroke="#475569" stroke-width="1"/>\n'
        )

    # Check top wall of r → bottom wall of adj_r
    elif abs((r["y"] + r["h"]) - adj_r["y"]) < tol:
        shared_x0 = max(r["x"], adj_r["x"])
        shared_x1 = min(r["x"] + r["w"], adj_r["x"] + adj_r["w"])
        if shared_x1 - shared_x0 < 0.6:
            return ""
        mid_x = (shared_x0 + shared_x1) / 2
        mid_x_px  = _rx(mid_x)
        wall_y_px = _ry_top(r["y"], r["h"], unit_d)   # top of lower room
        svg += (
            f'<line x1="{mid_x_px - door_r_px/2:.1f}" y1="{wall_y_px:.1f}" '
            f'x2="{mid_x_px + door_r_px/2:.1f}" y2="{wall_y_px:.1f}" '
            f'stroke="white" stroke-width="4"/>\n'
        )
        svg += (
            f'<path d="M{mid_x_px:.1f},{wall_y_px:.1f} '
            f'L{mid_x_px:.1f},{wall_y_px - door_r_px:.1f} '
            f'A{door_r_px:.1f},{door_r_px:.1f} 0 0,0 '
            f'{mid_x_px + door_r_px:.1f},{wall_y_px:.1f}" '
            f'fill="none" stroke="#475569" stroke-width="1"/>\n'
        )

    return svg


def _window_symbol(
    r: Dict, unit_w: float, unit_d: float,
) -> str:
    """Three parallel cyan lines in a gap on the exterior wall face."""
    svg = ""
    tol = 0.15
    win_gap_m  = min(r["w"] * 0.5, 1.2)
    win_gap_px = _m2p(win_gap_m)
    line_gap   = 3   # px between parallel lines

    def _h_window(wall_y_px: float, cx_px: float) -> str:
        s = f'<line x1="{cx_px - win_gap_px/2:.1f}" y1="{wall_y_px:.1f}" '
        s += f'x2="{cx_px + win_gap_px/2:.1f}" y2="{wall_y_px:.1f}" '
        s += 'stroke="white" stroke-width="4"/>\n'
        for k in (-1, 0, 1):
            s += (f'<line x1="{cx_px - win_gap_px/2:.1f}" y1="{wall_y_px + k*line_gap:.1f}" '
                  f'x2="{cx_px + win_gap_px/2:.1f}" y2="{wall_y_px + k*line_gap:.1f}" '
                  f'stroke="#06b6d4" stroke-width="1"/>\n')
        return s

    def _v_window(wall_x_px: float, cy_px: float) -> str:
        win_h_px = _m2p(min(r["h"] * 0.5, 1.2))
        s = f'<line x1="{wall_x_px:.1f}" y1="{cy_px - win_h_px/2:.1f}" '
        s += f'x2="{wall_x_px:.1f}" y2="{cy_px + win_h_px/2:.1f}" '
        s += 'stroke="white" stroke-width="4"/>\n'
        for k in (-1, 0, 1):
            s += (f'<line x1="{wall_x_px + k*line_gap:.1f}" y1="{cy_px - win_h_px/2:.1f}" '
                  f'x2="{wall_x_px + k*line_gap:.1f}" y2="{cy_px + win_h_px/2:.1f}" '
                  f'stroke="#06b6d4" stroke-width="1"/>\n')
        return s

    cx_px = _rx(r["x"] + r["w"] / 2)
    cy_px = _ry(r["y"] + r["h"] / 2, unit_d)

    if r["y"] <= tol:                         # south face
        svg += _h_window(_ry(r["y"], unit_d), cx_px)
    if r["y"] + r["h"] >= unit_d - tol:      # north face
        svg += _h_window(_ry(r["y"] + r["h"], unit_d), cx_px)
    if r["x"] <= tol:                         # west face
        svg += _v_window(_rx(r["x"]), cy_px)
    if r["x"] + r["w"] >= unit_w - tol:      # east face
        svg += _v_window(_rx(r["x"] + r["w"]), cy_px)

    return svg


def _hatch_pattern(pid: str, angle: int = 45) -> str:
    """SVG <defs> hatch pattern element."""
    return (
        f'<pattern id="{pid}" width="8" height="8" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate({angle})">'
        f'<line x1="0" y1="0" x2="0" y2="8" stroke="#94a3b8" stroke-width="1" '
        f'stroke-opacity="0.4"/></pattern>'
    )


def _north_arrow(x_px: float, y_px: float, size: float = 30) -> str:
    """Compass rose — simplified N arrow."""
    half = size / 2
    tip  = y_px - size
    return (
        f'<g transform="translate({x_px},{y_px})">'
        f'<polygon points="0,{-size} {half/2},{0} {-half/2},{0}" '
        f'fill="#1e3a8a" opacity="0.85"/>'
        f'<text x="0" y="{-size - 5}" text-anchor="middle" '
        f'font-size="10" font-weight="700" fill="#1e3a8a">N</text>'
        f'</g>\n'
    )


def _scale_bar(x_px: float, y_px: float, metres: float = 3.0) -> str:
    """Horizontal scale bar annotated in metres."""
    w_px = _m2p(metres)
    return (
        f'<g>'
        f'<rect x="{x_px:.1f}" y="{y_px:.1f}" width="{w_px:.1f}" height="5" '
        f'fill="#1e293b"/>'
        f'<text x="{x_px + w_px/2:.1f}" y="{y_px + 16:.1f}" text-anchor="middle" '
        f'font-size="8" fill="#1e293b">{metres} m</text>'
        f'</g>\n'
    )


def _passage_hatch(
    r: Dict, unit_d: float, hatch_id: str,
) -> str:
    x_px = _rx(r["x"])
    y_px = _ry_top(r["y"], r["h"], unit_d)
    w_px = _m2p(r["w"])
    h_px = _m2p(r["h"])
    return (
        f'<rect x="{x_px:.1f}" y="{y_px:.1f}" width="{w_px:.1f}" height="{h_px:.1f}" '
        f'fill="url(#{hatch_id})" stroke="none"/>\n'
    )


# ─── Main renderer ─────────────────────────────────────────────────────────────

def render_svg(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
    compliance_report: Optional[Dict[str, Any]] = None,
    title: str = "Flat Floor Plan",
) -> str:
    """
    Convert optimised room rectangles into a standalone SVG string.

    Parameters
    ----------
    G                  : annotated topology graph
    rects              : room_id → {x, y, w, h} (metres)
    unit_w, unit_d     : flat outer dimensions (metres)
    compliance_report  : output of compliance_validator.validate()
    title              : SVG title element text

    Returns
    -------
    svg_str : complete standalone SVG document string
    """
    canvas_w = int(_m2p(unit_w) + 2 * MARGIN_PX)
    canvas_h = int(_m2p(unit_d) + 2 * MARGIN_PX)

    # Collect failing room ids for red overlay
    fail_rooms: set = set()
    if compliance_report:
        for issue in compliance_report.get("fails", []):
            rid = issue.get("room", "").split("–")[0].split("∩")[0].strip()
            if rid in rects:
                fail_rooms.add(rid)

    body = ""

    # ── Defs ──────────────────────────────────────────────────────────────────
    defs = '<defs>\n'
    defs += _hatch_pattern("passageHatch", 45)
    defs += _hatch_pattern("balconyHatch", 135)
    defs += '</defs>\n'

    # ── Flat bounding box (exterior wall) ─────────────────────────────────────
    body += _rect_elem(
        MARGIN_PX, MARGIN_PX,
        _m2p(unit_w), _m2p(unit_d),
        fill="#f8fafc", stroke="#0f172a", sw=WALL_EXT,
    )

    # ── Room rectangles ───────────────────────────────────────────────────────
    for nid, r in rects.items():
        data = G.nodes.get(nid, {})
        rt   = data.get("room_type", "room")
        fill_c, strk_c = ROOM_COLORS.get(rt, ROOM_COLORS["room"])

        x_px = _rx(r["x"])
        y_px = _ry_top(r["y"], r["h"], unit_d)
        w_px = _m2p(r["w"])
        h_px = _m2p(r["h"])

        # Balcony dashed outline
        extra = 'stroke-dasharray="6 3"' if rt == "balcony" else ""
        body += _rect_elem(x_px, y_px, w_px, h_px, fill_c, strk_c, WALL_INT, extra)

        # Passage diagonal hatch overlay
        if rt == "passage":
            body += _passage_hatch(r, unit_d, "passageHatch")

        # Compliance fail overlay
        if nid in fail_rooms:
            body += _rect_elem(
                x_px, y_px, w_px, h_px,
                COMPLIANCE_FAIL_FILL, COMPLIANCE_FAIL_STROKE, 2,
                'stroke-dasharray="4 2"',
            )

        # Window symbols on exterior rooms
        if data.get("exterior", False) or rt == "balcony":
            body += _window_symbol(r, unit_w, unit_d)

    # ── Internal partition lines between adjacent rooms ────────────────────────
    drawn_edges = set()
    for u, v in G.edges():
        edge_key = (min(u, v), max(u, v))
        if edge_key in drawn_edges:
            continue
        drawn_edges.add(edge_key)
        if u not in rects or v not in rects:
            continue
        ru, rv = rects[u], rects[v]
        tol = 0.05

        # Vertical shared wall
        if abs((ru["x"] + ru["w"]) - rv["x"]) < tol or abs((rv["x"] + rv["w"]) - ru["x"]) < tol:
            wx = (ru["x"] + ru["w"]) if abs((ru["x"] + ru["w"]) - rv["x"]) < tol else rv["x"] + rv["w"]
            sy0 = max(ru["y"], rv["y"])
            sy1 = min(ru["y"] + ru["h"], rv["y"] + rv["h"])
            if sy1 > sy0:
                x_p  = _rx(wx)
                y0_p = _ry(sy1, unit_d)
                y1_p = _ry(sy0, unit_d)
                body += f'<line x1="{x_p:.1f}" y1="{y0_p:.1f}" x2="{x_p:.1f}" y2="{y1_p:.1f}" stroke="#64748b" stroke-width="{WALL_INT}"/>\n'

        # Horizontal shared wall
        elif abs((ru["y"] + ru["h"]) - rv["y"]) < tol or abs((rv["y"] + rv["h"]) - ru["y"]) < tol:
            wy = (ru["y"] + ru["h"]) if abs((ru["y"] + ru["h"]) - rv["y"]) < tol else rv["y"] + rv["h"]
            sx0 = max(ru["x"], rv["x"])
            sx1 = min(ru["x"] + ru["w"], rv["x"] + rv["w"])
            if sx1 > sx0:
                x0_p = _rx(sx0)
                x1_p = _rx(sx1)
                y_p  = _ry(wy, unit_d)
                body += f'<line x1="{x0_p:.1f}" y1="{y_p:.1f}" x2="{x1_p:.1f}" y2="{y_p:.1f}" stroke="#64748b" stroke-width="{WALL_INT}"/>\n'

    # ── Doors ─────────────────────────────────────────────────────────────────
    drawn_doors = set()
    for u, v in G.edges():
        edge_key = (min(u, v), max(u, v))
        if edge_key in drawn_doors:
            continue
        drawn_doors.add(edge_key)
        if u not in rects or v not in rects:
            continue
        body += _door_symbol(rects[u], rects[v], unit_d)

    # ── Room labels ────────────────────────────────────────────────────────────
    for nid, r in rects.items():
        cx_px = _rx(r["x"] + r["w"] / 2)
        cy_px = _ry(r["y"] + r["h"] / 2, unit_d)

        # Room name — title-case, shortened for small rooms
        label = nid.replace("_", " ").title()
        if r["w"] * r["h"] < 3.5:
            label = label[:10]  # truncate for tiny rooms

        area_txt = f"{r['w'] * r['h']:.1f} m²"

        body += _text_elem(cx_px, cy_px - 7, label, FONT_MAIN, "600")
        body += _text_elem(cx_px, cy_px + 7, area_txt, FONT_SMALL, "normal", "#374151")

        # Passage width annotation
        if G.nodes.get(nid, {}).get("room_type") == "passage":
            w_label = f"w={min(r['w'], r['h']):.2f} m"
            body += _text_elem(cx_px, cy_px + 18, w_label, 7, "normal", "#475569")

    # ── Compliance annotation bar (top) ──────────────────────────────────────
    if compliance_report:
        fc = compliance_report.get("fail_count", 0)
        wc = compliance_report.get("warn_count", 0)
        colour = "#15803d" if fc == 0 else "#dc2626"
        badge  = f"GDCR: {'ALL PASS' if fc == 0 else f'{fc} FAIL  {wc} WARN'}"
        body += _text_elem(
            canvas_w / 2, MARGIN_PX / 2, badge,
            11, "700", colour,
        )

    # ── North arrow + scale bar ───────────────────────────────────────────────
    body += _north_arrow(canvas_w - MARGIN_PX + 15, MARGIN_PX + 45)
    body += _scale_bar(canvas_w - MARGIN_PX - _m2p(3) - 5, canvas_h - MARGIN_PX + 15)

    # ── Title ─────────────────────────────────────────────────────────────────
    body += _text_elem(MARGIN_PX, canvas_h - MARGIN_PX + 20, title, 10, "500", "#64748b", "start")

    # ── Assemble SVG document ─────────────────────────────────────────────────
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{canvas_w}" height="{canvas_h}" '
        f'viewBox="0 0 {canvas_w} {canvas_h}">\n'
        f'<title>{html.escape(title)}</title>\n'
        f'{defs}'
        f'<rect width="{canvas_w}" height="{canvas_h}" fill="#f8fafc"/>\n'
        f'{body}'
        f'</svg>\n'
    )
    return svg
