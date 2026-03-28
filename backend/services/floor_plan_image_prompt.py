"""
floor_plan_image_prompt.py — Convert LLM layout JSON + metrics into DALL-E 3 prompts.

Two pure functions. No AI calls, no side effects — deterministic string builders.
"""
from __future__ import annotations

from typing import Any, Dict


def build_architectural_prompt(
    layout: Dict[str, Any],
    metrics: Dict[str, Any],
    segment: str = "mid",
    units_per_core: int | None = None,
) -> str:
    """Build DALL-E 3 prompt for a black-and-white technical architectural floor plan."""

    floor_w = metrics.get("floorLengthM", 24.0)
    floor_d = metrics.get("floorDepthM", 12.0)
    n_units = metrics.get("nUnitsPerFloor", len(layout.get("units", [])))
    upc = units_per_core or n_units

    core = layout.get("core", {})
    corridor = layout.get("corridor", {})
    units = layout.get("units", [])

    parts = [
        "Professional architectural floor plan, black and white line drawing, "
        "top-down orthographic view, scale 1:100, clean drafting style.",
        "",
        f"Floor plate: {floor_w}m x {floor_d}m rectangular slab.",
    ]

    # Core
    if core:
        parts.append(
            f"Central service core: {core.get('w', 4.5)}m x {core.get('h', 12.0)}m "
            f"containing {core.get('stairs', 2)} staircases, {core.get('lifts', 2)} lifts, "
            f"and a lobby area."
        )

    # Corridor
    if corridor:
        parts.append(
            f"Central corridor: {corridor.get('w', 24.0)}m x {corridor.get('h', 1.5)}m "
            "running the full length of the floor plate."
        )

    # Units
    for unit in units:
        unit_type = unit.get("type", "unit")
        carpet = unit.get("carpet_area_sqm", 0)
        side = unit.get("side", "")
        rooms = unit.get("rooms", [])

        parts.append("")
        parts.append(f"{unit_type} unit ({carpet} sqm carpet) on the {side} side:")

        for room in rooms:
            rtype = room.get("type", "room")
            rw = room.get("w", 0)
            rh = room.get("h", 0)
            pos = room.get("position", "")
            parts.append(f"  - {rtype}: {rw}m x {rh}m at {pos}")

    # Architectural conventions
    parts.append("")
    parts.append(
        "Architectural conventions: Diagonal hatching on wet zones (kitchen, bathrooms, toilets). "
        "Door swing arcs shown as quarter-circle arcs. Windows as double lines on exterior walls. "
        "Dimension lines on all rooms. Structural column grid at 4.5m centers shown as dashed lines "
        "with circle markers."
    )

    # Title block
    seg_label = segment.title() if segment else "Mid"
    parts.append("")
    parts.append(
        f"Title block: \"Typical Floor Plan — {upc} units/core — {seg_label} — Scale 1:100\""
    )

    # Finish
    parts.append("")
    parts.append(
        "Clean white background, no color, architectural drafting convention, "
        "thin precise black lines, professional quality."
    )

    return "\n".join(parts)


def build_presentation_prompt(
    layout: Dict[str, Any],
    metrics: Dict[str, Any],
    segment: str = "mid",
) -> str:
    """Build DALL-E 3 prompt for a colored real estate brochure rendering."""

    floor_w = metrics.get("floorLengthM", 24.0)
    floor_d = metrics.get("floorDepthM", 12.0)
    units = layout.get("units", [])
    core = layout.get("core", {})

    # Material palette by segment
    material_palettes = {
        "budget": "laminate flooring, basic ceramic tiles, simple modular kitchen with laminate finish",
        "mid": "vitrified tile flooring, modular kitchen with granite countertop, ceramic bathroom tiles",
        "premium": "wooden flooring in bedrooms, polished granite counters, designer bathroom fixtures, "
                   "full-height tiling in bathrooms",
        "luxury": "Italian marble flooring throughout, imported designer fixtures, walk-in wardrobes, "
                  "premium hardwood accents, rain shower in master bath",
    }

    # Furniture descriptions by room type
    furniture = {
        "LIVING": "L-shaped sofa, coffee table, TV unit, and accent rug",
        "BEDROOM": "king-size bed with headboard, side tables, and wardrobe",
        "KITCHEN": "L-shaped counter with sink, cooktop, chimney, and refrigerator",
        "TOILET": "western commode, vanity with basin, mirror, and shower area",
        "PASSAGE": "clean open passage",
        "DINING": "4-seater dining table with chairs",
        "BALCONY": "planters with greenery and outdoor seating",
    }

    mat = material_palettes.get(segment, material_palettes["mid"])

    parts = [
        "Luxury residential floor plan, top-down bird's-eye view, photorealistic architectural rendering, "
        "soft warm lighting, magazine-quality presentation.",
        "",
        f"Floor plate: {floor_w}m x {floor_d}m rectangular building footprint.",
    ]

    # Core
    if core:
        parts.append(
            f"Central core with marble-floored lobby, {core.get('lifts', 2)} lifts with "
            f"stainless steel doors, and {core.get('stairs', 2)} enclosed staircases."
        )

    parts.append(f"Material palette: {mat}.")

    # Units with furnished rooms
    for unit in units:
        unit_type = unit.get("type", "unit")
        carpet = unit.get("carpet_area_sqm", 0)
        side = unit.get("side", "")
        rooms = unit.get("rooms", [])

        parts.append("")
        parts.append(f"{unit_type} unit ({carpet} sqm) on the {side} side:")

        for room in rooms:
            rtype = room.get("type", "room")
            rw = room.get("w", 0)
            rh = room.get("h", 0)
            furn = furniture.get(rtype, "furnished appropriately")
            parts.append(f"  - {rtype} ({rw}m x {rh}m): {furn}")

    # Balconies
    parts.append("")
    parts.append("Balconies: planters with greenery, outdoor seating, city views.")

    # Finish
    parts.append("")
    parts.append(
        "No perspective distortion, perfectly orthographic top-down view, clean edges, "
        "magazine-quality rendering, warm ambient lighting with soft shadows."
    )

    return "\n".join(parts)
