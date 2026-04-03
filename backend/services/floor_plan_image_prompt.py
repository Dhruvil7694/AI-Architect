"""
floor_plan_image_prompt.py
---------------------------
Three-layer diffusion-oriented floor plan image prompting:

1. Visual tokens from layout JSON (geometry-aware, compact).
2. Compressed prompt (style + layout + tokens + symbols + negative).
3. Multi-variant scoring helpers (see ai_floor_plan_service).

SVG / GeoJSON remain authoritative; raster is illustrative.
"""
from __future__ import annotations

import base64
import binascii
import logging
import statistics
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# GDCR / NBC thresholds (layout_block hints only)
# ─────────────────────────────────────────────────────────────────────────────

_LIFT_THRESHOLD_M = 10.0
_HIGHRISE_STAIR_M = 15.0
_STD_CORRIDOR_W = 1.5
_NARROW_PLOT_DEPTH_M = 9.0
_COMPACT_ASPECT_RATIO = 1.5


def _derive_layout_strategy(
    floor_w: float,
    floor_d: float,
    n_units: int,
    building_height_m: float,
    units: List[dict],
) -> dict:
    needs_lift = building_height_m > _LIFT_THRESHOLD_M
    n_lifts = 0 if not needs_lift else (2 if n_units >= 4 else 1)
    n_stairs = 2 if building_height_m > _HIGHRISE_STAIR_M else 1
    is_narrow = floor_d < _NARROW_PLOT_DEPTH_M
    aspect_ratio = round(floor_w / max(floor_d, 1.0), 2)
    is_wide_slab = aspect_ratio >= _COMPACT_ASPECT_RATIO

    if n_units <= 2:
        corridor_type = "landing"
        corridor_w = 0.0
    elif is_narrow:
        corridor_type = "single_loaded"
        corridor_w = _STD_CORRIDOR_W
    elif is_wide_slab:
        corridor_type = "double_loaded"
        corridor_w = _STD_CORRIDOR_W
    elif n_units <= 4:
        corridor_type = "double_loaded"
        corridor_w = _STD_CORRIDOR_W
    else:
        corridor_type = "cross"
        corridor_w = _STD_CORRIDOR_W

    north_units = [u for u in units if u.get("side", "north").lower() in ("north", "")]
    south_units = [u for u in units if u.get("side", "north").lower() == "south"]
    if not south_units and n_units >= 2:
        half = n_units // 2
        north_units = units[:half]
        south_units = units[half:]

    return {
        "needs_lift": needs_lift,
        "n_lifts": n_lifts,
        "n_stairs": n_stairs,
        "corridor_type": corridor_type,
        "corridor_w": corridor_w,
        "n_north": len(north_units),
        "n_south": len(south_units),
    }


def _h_band(nx: float) -> str:
    if nx < 0.33:
        return "left"
    if nx > 0.66:
        return "right"
    return "center"


def _v_band(ny: float) -> str:
    if ny < 0.33:
        return "bottom"
    if ny > 0.66:
        return "top"
    return "center"


def _room_slug(rtype: str) -> str:
    t = (rtype or "room").lower().strip().replace(" ", "_")
    aliases = {
        "bedroom2": "bedroom",
        "bath": "bathroom",
        "wc": "toilet",
        "dr": "dining",
        "lr": "living",
    }
    return aliases.get(t, t)[:14]


def _cardinal_neighbor(ra: Tuple[float, ...], rb: Tuple[float, ...]) -> str:
    """Return short phrase: how rb sits relative to ra (metre space, y-up)."""
    ax = float(ra[0]) + float(ra[2]) / 2.0
    ay = float(ra[1]) + float(ra[3]) / 2.0
    bx = float(rb[0]) + float(rb[2]) / 2.0
    by = float(rb[1]) + float(rb[3]) / 2.0
    dx, dy = bx - ax, by - ay
    if abs(dx) >= abs(dy):
        return "east_of" if dx > 0.05 else "west_of" if dx < -0.05 else "aligned_x"
    return "north_of" if dy > 0.05 else "south_of" if dy < -0.05 else "aligned_y"


def build_visual_tokens(ai_layout: dict) -> str:
    """
    Compact spatial string from layout JSON: zones, sizes, grid-normalized bands, adjacency.
    No narrative paragraphs.
    """
    units = ai_layout.get("units") or []
    clauses: List[str] = []
    rects: List[Tuple[float, float, float, float, int, str]] = []

    for ui, unit in enumerate(units):
        ut = _room_slug(str(unit.get("type", "unit")))
        uw = float(unit.get("w", 0))
        uh = float(unit.get("h", 0))
        if uw > 0 and uh > 0:
            clauses.append(f"unit{ui + 1}-{ut}-box-{uw:.1f}x{uh:.1f}m")
        for room in unit.get("rooms") or []:
            rw = float(room.get("w", 0))
            rh = float(room.get("h", 0))
            slug = _room_slug(str(room.get("type", "room")))
            rx = room.get("x")
            ry = room.get("y")
            if rx is None or ry is None:
                clauses.append(f"u{ui + 1}-{slug}-{rw:.1f}x{rh:.1f}m-noXY")
                continue
            rx_f = float(rx)
            ry_f = float(ry)
            rects.append((rx_f, ry_f, rw, rh, ui, slug))

    min_x = min((r[0] for r in rects), default=0.0)
    min_y = min((r[1] for r in rects), default=0.0)
    max_x = max((r[0] + r[2] for r in rects), default=1.0)
    max_y = max((r[1] + r[3] for r in rects), default=1.0)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)

    adj_seen = set()
    by_unit: Dict[int, List[Tuple[float, float, float, float, str]]] = {}
    for rx_f, ry_f, rw, rh, ui, slug in rects:
        by_unit.setdefault(ui, []).append((rx_f, ry_f, rw, rh, slug))

    for ui, rlist in by_unit.items():
        for i, ra in enumerate(rlist):
            best_j = -1
            best_d = 1e18
            ax, ay = ra[0] + ra[2] / 2.0, ra[1] + ra[3] / 2.0
            for j, rb in enumerate(rlist):
                if i == j:
                    continue
                bx, by = rb[0] + rb[2] / 2.0, rb[1] + rb[3] / 2.0
                d = (ax - bx) ** 2 + (ay - by) ** 2
                if d < best_d:
                    best_d = d
                    best_j = j
            if best_j >= 0:
                rb = rlist[best_j]
                key = tuple(sorted([ra[4], rb[4]]))
                pair_key = (ui, key)
                if pair_key in adj_seen:
                    continue
                adj_seen.add(pair_key)
                rel = _cardinal_neighbor(ra[:4], rb[:4])
                clauses.append(f"u{ui + 1}-{ra[4]}-{rel}-{rb[4]}")

    for rx_f, ry_f, rw, rh, ui, slug in rects:
        cx = (rx_f + rw / 2.0 - min_x) / span_x
        cy = (ry_f + rh / 2.0 - min_y) / span_y
        clauses.append(
            f"u{ui + 1}-{slug}-{_h_band(cx)}-{_v_band(cy)}-{rw:.1f}x{rh:.1f}m"
        )

    core = ai_layout.get("core")
    if isinstance(core, dict) and all(k in core for k in ("x", "y", "w", "h")):
        cw = float(core["w"])
        ch = float(core["h"])
        clauses.insert(0, f"core-mid-{cw:.1f}x{ch:.1f}m")

    cor = ai_layout.get("corridor")
    if isinstance(cor, dict) and all(k in cor for k in ("x", "y", "w", "h")):
        clauses.insert(0, f"corridor-{float(cor['w']):.1f}x{float(cor['h']):.1f}m-strip")

    out = ", ".join(clauses)
    max_chars = 1200
    if len(out) > max_chars:
        out = out[: max_chars - 3] + "..."
    return out


def _layout_hint_short(
    floor_w: float,
    floor_d: float,
    n_units: int,
    building_height_m: float,
    units: List[dict],
) -> str:
    s = _derive_layout_strategy(floor_w, floor_d, n_units, building_height_m, units)
    ct = s["corridor_type"]
    if ct == "landing":
        return f"core-landing-{n_units}units-around"
    if ct == "single_loaded":
        return f"single-corridor-{s['corridor_w']}m-{s['n_north']}N-{s['n_south']}S"
    if ct == "double_loaded":
        return f"double-corridor-{s['corridor_w']}m-core-center-{s['n_north']}N-{s['n_south']}S"
    return f"cross-corridor-core-mid-{n_units}units"


def build_architectural_prompt(
    layout: Dict[str, Any],
    metrics: Dict[str, Any],
    segment: str = "mid",
    units_per_core: Optional[int] = None,
    building_height_m: Optional[float] = None,
    design_brief: str = "",
    design_notes: Optional[str] = None,
) -> str:
    """
    Compressed diffusion prompt (~150–220 words target). Visual conditioning from layout JSON.
    design_brief / design_notes accepted for API stability; omitted from prompt text.
    """
    del segment, units_per_core, design_brief, design_notes  # API compat; keep prompt minimal

    floor_w = float(metrics.get("floorLengthM", 24.0))
    floor_d = float(metrics.get("floorWidthM") or metrics.get("floorDepthM", 12.0))
    n_units = int(metrics.get("nUnitsPerFloor", len(layout.get("units", []))))
    n_floors = int(metrics.get("nFloors", 10))
    bh = float(
        building_height_m
        or metrics.get("buildingHeightM")
        or (n_floors * float(metrics.get("storeyHeightM", 3.0)))
    )
    units = layout.get("units", [])

    style_block = (
        "2D architectural floor plan top view black white CAD clean linework "
        "orthographic projection no color no furniture"
    )
    room_block = build_visual_tokens(layout)
    layout_block = (
        f"rectangular floor plan {floor_w}m by {floor_d}m "
        f"{_layout_hint_short(floor_w, floor_d, n_units, bh, units)} "
        "orthogonal grid symmetrical slab"
    )
    symbol_block = (
        "doors with swing arcs windows on outer walls stairs with arrow "
        "lift core labeled room labels with meter dimensions"
    )
    negative_block = "no 3D no perspective no furniture no colors no shadows photorealistic"

    parts = [style_block, layout_block, room_block, symbol_block, negative_block]
    return ", ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-image scoring (heuristic; vision hook can replace later)
# ─────────────────────────────────────────────────────────────────────────────

def _heuristic_score_b64(b64: Optional[str]) -> float:
    if not b64 or len(b64) < 80:
        return -1.0
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return -1.0
    if len(raw) < 400:
        return -1.0
    n = min(len(raw), 65536)
    chunk = raw[:n]
    arr = list(chunk)
    try:
        sd = statistics.pstdev(arr)
    except statistics.StatisticsError:
        sd = 0.0
    return float(sd) + 1e-4 * float(len(raw))


def score_generated_images(
    images: List[Optional[str]],
    ai_layout: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Pick best candidate by byte-variance heuristic (proxy for line detail / non-blank).
    ai_layout reserved for future vision-based re-ranking.
    """
    del ai_layout  # future: vision compare to layout
    meta: Dict[str, Any] = {"scores": [], "picked_index": None}
    best_b64: Optional[str] = None
    best_score = -1.0
    best_i: Optional[int] = None

    for i, img in enumerate(images):
        sc = _heuristic_score_b64(img)
        meta["scores"].append({"index": i, "score": sc})
        if sc > best_score:
            best_score = sc
            best_b64 = img
            best_i = i

    meta["picked_index"] = best_i
    meta["best_score"] = best_score
    if best_i is not None:
        logger.info(
            "[FP:img] score_generated_images picked index=%d score=%.4f (N=%d)",
            best_i,
            best_score,
            len(images),
        )
    else:
        logger.info("[FP:img] score_generated_images no valid candidates (N=%d)", len(images))
    return best_b64, meta


PROMPT_VARIANT_SUFFIXES = (
    "",
    "clean technical drawing",
    "high precision blueprint",
    "minimal architectural plan",
    "sharp linework schematic",
)


# ─────────────────────────────────────────────────────────────────────────────
# Surat-norm Recraft prompt compiler (Layer 2)
# ─────────────────────────────────────────────────────────────────────────────

def compile_recraft_prompt(
    layouts: "List[Any]",  # list[RoomLayout] from layout_engine
    unit_w: float,
    unit_d: float,
    unit_type: str,
    n_units: int,
    segment: str = "Mid",
) -> str:
    """
    Convert a validated RoomLayout list into a T2I-optimised natural language
    prompt for Recraft V4.

    Design principles:
    - Absolute spatial anchors  (coordinates as fractions of W/D)
    - Explicit adjacency chains (room A directly behind room B)
    - Visual density bias       (living = largest, front-dominant)
    - Critical constraint repetition (living first, bedrooms via passage)
    - No token notation — plain architectural English only

    Args:
        layouts:    list[RoomLayout] from layout_engine.generate_unit_layout()
        unit_w:     unit width in metres
        unit_d:     unit depth in metres
        unit_type:  "1BHK" | "2BHK" | "3BHK" | "4BHK"
        n_units:    number of units on this floor plate
        segment:    "Budget" | "Mid" | "Premium" | "Luxury"

    Returns:
        Prompt string ready for Recraft V4 API.
    """
    by_name = {r.name: r for r in layouts}

    def get(name: str):
        return by_name.get(name)

    def norm_x(room) -> float:
        if room is None:
            return 0.5
        return round((room.x + room.width / 2.0) / max(unit_w, 0.01), 2)

    def norm_y(room) -> float:
        if room is None:
            return 0.5
        return round((room.y + room.depth / 2.0) / max(unit_d, 0.01), 2)

    def fmt(room, label: Optional[str] = None) -> str:
        if room is None:
            return ""
        nm = label or room.name.replace("_", " ")
        return f"{nm} ({room.width:.1f}\u00d7{room.depth:.1f}m)"

    living   = get("living")
    powder   = get("powder_room")
    dining   = get("dining")
    kitchen  = get("kitchen")
    utility  = get("utility")
    passage  = get("passage")
    master   = get("master_bed")

    beds = [r for r in layouts
            if r.name.startswith("bed_") or r.name == "master_bed"]
    secondary_beds = [b for b in beds if b.name != "master_bed"]
    n_beds = len(beds)

    segment_desc = {
        "Budget": "standard-finish",
        "Mid": "mid-grade",
        "Premium": "premium",
        "Luxury": "luxury",
    }.get(segment, "mid-grade")

    # ── STYLE ────────────────────────────────────────────────────────────────
    style = (
        "2D architectural floor plan, top-down orthographic view, "
        "black and white CAD linework, no colour, no furniture, no hatching. "
        "Room labels with metre dimensions. Clean technical drawing."
    )

    # ── COMPOSITION ──────────────────────────────────────────────────────────
    composition = (
        f"{n_units} x {unit_type} {segment_desc} apartments flanking a central "
        f"lift core with fire staircase. "
        f"Rectangular floor plate {unit_w * n_units:.0f}m wide by {unit_d:.1f}m deep. "
        f"Each unit is {unit_w:.1f}m wide by {unit_d:.1f}m deep."
    )

    # ── ENTRY + PUBLIC ZONE ───────────────────────────────────────────────────
    liv_desc = fmt(living, "living room") if living else "large living room"
    pr_side = "right" if (powder and living and powder.x > living.x + living.width / 2) else "left"
    pr_desc = fmt(powder, "powder room") if powder else ""
    pr_sentence = (
        f"A small {pr_desc} is placed along the entrance wall on the {pr_side} side, "
        f"directly accessible from the living room, at coordinates ({norm_x(powder):.1f}W, {norm_y(powder):.1f}D)."
        if powder else ""
    )
    liv_coords = f"({norm_x(living):.1f}W, {norm_y(living):.1f}D)" if living else "(0.5W, 0.1D)"

    entry_zone = (
        f"Main entrance at bottom center of each unit (0.5W, 0.0D). "
        f"Entrance opens DIRECTLY into {liv_desc} — "
        f"the living room is the FIRST and LARGEST space visible from entry, "
        f"spanning {living.width:.1f}m ({living.width / unit_w * 100:.0f}% of unit width), "
        f"positioned at {liv_coords}. "
        f"IMPORTANT: Living room must be immediately adjacent to the main entrance. "
        + pr_sentence
    )

    # ── SEMI-PRIVATE ZONE ────────────────────────────────────────────────────
    din_desc  = fmt(dining,  "dining room") if dining else ""
    kit_desc  = fmt(kitchen, "kitchen")     if kitchen else ""
    util_desc = fmt(utility, "utility area") if utility else ""

    if dining and kitchen:
        semi_private = (
            f"{din_desc} directly behind the living room along the vertical axis, "
            f"sharing a full-width wall with the living room, "
            f"at coordinates ({norm_x(dining):.1f}W, {norm_y(dining):.1f}D). "
            f"{kit_desc} directly behind the dining room, flush alignment, "
            f"touching the rear external wall for ventilation, "
            f"at coordinates ({norm_x(kitchen):.1f}W, {norm_y(kitchen):.1f}D). "
            + (f"{util_desc} beside the kitchen at the rear. " if utility else "")
        )
    elif kitchen:
        # 1BHK: integrated kitchen
        semi_private = (
            f"{kit_desc} behind the living area, touching the rear external wall, "
            f"at coordinates ({norm_x(kitchen):.1f}W, {norm_y(kitchen):.1f}D). "
        )
    else:
        semi_private = ""

    # ── CIRCULATION ───────────────────────────────────────────────────────────
    if passage:
        pass_coords_start = f"({norm_x(passage):.1f}W, {norm_y(passage):.1f}D)"
        pass_coords_end   = f"({norm_x(passage):.1f}W, 0.95D)"
        circulation = (
            f"A {passage.width:.1f}m-wide central passage runs along the depth axis "
            f"from the dining zone to the rear of the unit, "
            f"from {pass_coords_start} to {pass_coords_end}. "
            f"ALL bedrooms are accessed ONLY through this passage. "
            f"NO bedroom opens directly into the living room or dining room."
        )
    else:
        circulation = (
            "A central passage connects the main living area to all bedrooms. "
            "No bedroom opens directly into the living room."
        )

    # ── PRIVATE ZONE ─────────────────────────────────────────────────────────
    if master:
        master_desc = fmt(master, "master bedroom")
        master_coords = f"({norm_x(master):.1f}W, {norm_y(master):.1f}D)"
        private_zone = (
            f"{master_desc} at the far rear of the unit with attached bathroom, "
            f"touching the rear external wall, at {master_coords}. "
        )
    else:
        private_zone = ""

    if secondary_beds:
        sec_names = [fmt(b, b.name.replace("_", " ")) for b in secondary_beds]
        private_zone += (
            f"{len(secondary_beds)} secondary bedroom{'s' if len(secondary_beds) > 1 else ''} "
            f"({', '.join(sec_names)}) along the central passage, "
            f"each touching an external wall. "
            f"All bedrooms distributed symmetrically on both sides of the central passage."
        )

    # ── SYMBOLS ───────────────────────────────────────────────────────────────
    symbols = (
        "Door swing arcs on all doors. Windows on all external walls. "
        "Staircase with direction arrow. Lift shaft labeled 'LIFT CORE'. "
        "All rooms labeled with name and dimensions in metres. "
        "North arrow at top right of drawing."
    )

    # ── NEGATIVE ──────────────────────────────────────────────────────────────
    negative = (
        "No 3D rendering. No perspective view. No furniture. No shadows. "
        "No colour fills. No decorative elements. No hatching. No gradients."
    )

    # ── CRITICAL REPEAT (end of prompt — highest attention weight) ────────────
    critical = (
        f"CRITICAL REQUIREMENTS: "
        f"(1) Living room must be the FIRST space immediately after the entrance at bottom center. "
        f"(2) All {n_beds} bedroom{'s' if n_beds != 1 else ''} must be accessible ONLY through "
        f"the central passage — never directly from the living room. "
        f"(3) Kitchen must be at the rear of the unit, touching an external wall."
    )

    parts = [
        style,
        composition,
        entry_zone,
        semi_private,
        circulation,
        private_zone,
        symbols,
        negative,
        critical,
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def generate_from_svg(svg: str, prompt: str) -> Optional[str]:
    """
    Reserved for ControlNet / img2img from SVG rasterization.
    Not implemented.
    """
    del svg, prompt
    logger.debug("generate_from_svg: stub (ControlNet / img2img not wired)")
    return None
