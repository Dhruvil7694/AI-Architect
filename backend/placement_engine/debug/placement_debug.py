"""
placement_engine/debug/placement_debug.py
------------------------------------------
Placement quality instrumentation: 8 scalar metrics + GeoJSON debug layer.

This module is read-only with respect to all algorithms.  It consumes existing
EnvelopeResult and PlacementResult objects and derives diagnostic information
from them without modifying any geometry, running any new algorithm, or
changing any placement decision.

Metrics produced
----------------
1.  envelope_area_sqft         – Legal buildable area after setbacks + COP exclusion.
2.  footprint_area_sqft        – Sum of all placed tower footprint areas.
3.  leftover_area_sqft         – Envelope area NOT covered by any spacing buffer.
4.  leftover_compactness_score – Polsby-Popper score of the leftover polygon
                                 (4π·area/perimeter²; 1.0 = circle, 0 = highly irregular).
5.  road_frontage_length_m     – Total road-facing edge length of the plot in metres.
6.  tower_orientation_angles_deg – List of orientation angles used per tower.
7.  cop_area_sqft              – Reserved Common Open Plot area.
8.  cop_min_dimension_m        – Minimum bounding-box dimension of the COP in metres.

Debug GeoJSON layers
--------------------
Layer                  Description
---------------------  ---------------------------------------------------------
buildable_envelope     Legal buildable polygon (after all setbacks + COP exclusion)
selected_footprint     Placed tower footprint rectangle (one feature per tower)
spacing_buffer         Full H/3 exclusion zone around each footprint
cop_area               Common Open Plot reserved polygon
leftover_polygon       Envelope area left after removing all spacing buffers

All coordinates are in DXF feet (SRID=0), matching the backend geometry contract.

Unit contract
-------------
- Input geometry: DXF feet (SRID=0) — Shapely Polygons from EnvelopeResult /
  FootprintCandidate.footprint_polygon.
- Distances and dimensions reported in metres (converted via DXF_TO_METRES).
- Areas reported in square feet (native DXF area).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from shapely.geometry import mapping
from shapely.ops import unary_union

from placement_engine.geometry import DXF_TO_METRES
from placement_engine.geometry.spacing_enforcer import (
    compute_exclusion_zone,
    required_spacing_m,
)


# ── PlacementDebugMetrics dataclass ───────────────────────────────────────────

@dataclass
class PlacementDebugMetrics:
    """
    8 scalar metrics describing placement quality for a single pipeline run.

    All sqft values are in DXF square feet; all _m values are in metres.
    Produced by compute_placement_debug_metrics() — never mutates inputs.
    """

    # ── The 8 required metrics ─────────────────────────────────────────────────

    # 1. Total buildable area after setbacks + COP exclusion
    envelope_area_sqft: float

    # 2. Total placed footprint area across all towers
    footprint_area_sqft: float

    # 3. Envelope area not covered by any spacing buffer (unplaceable residual)
    leftover_area_sqft: float

    # 4. Polsby-Popper compactness of the leftover polygon (0–1; 1.0 = circle)
    leftover_compactness_score: float

    # 5. Sum of all road-facing edge lengths in metres
    road_frontage_length_m: float

    # 6. Per-tower orientation angle used by the inscribed-rectangle algorithm
    tower_orientation_angles_deg: List[float]

    # 7. COP reserved area in square feet
    cop_area_sqft: float

    # 8. Minimum bounding-box dimension of the COP polygon in metres
    cop_min_dimension_m: float

    # ── Derived ratios (bonus context) ────────────────────────────────────────

    # Footprint area as a fraction of envelope area (0–100 %)
    footprint_utilization_pct: float

    # Leftover area as a fraction of envelope area (0–100 %)
    leftover_utilization_pct: float

    # Number of towers successfully placed
    n_towers_placed: int

    # Dominant-open-space heuristic: largest leftover component area as a
    # fraction of total leftover area (0–1; 1.0 = single dominant space).
    open_space_consolidation: float = 0.0

    # Area of the largest leftover open-space component (sqft)
    largest_open_area_sqft: float = 0.0

    # Maximum edge-alignment ratio across towers (0–1)
    edge_alignment_ratio: float = 0.0

    # Target vs actual tower plate areas (sqft) — advisory only
    target_plate_area_sqft: float = 0.0
    actual_plate_area_sqft: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable representation for JSON / API responses."""
        return {
            "envelope_area_sqft":            round(self.envelope_area_sqft, 2),
            "footprint_area_sqft":           round(self.footprint_area_sqft, 2),
            "leftover_area_sqft":            round(self.leftover_area_sqft, 2),
            "leftover_compactness_score":    round(self.leftover_compactness_score, 4),
            "road_frontage_length_m":        round(self.road_frontage_length_m, 3),
            "tower_orientation_angles_deg":  [
                round(a, 2) for a in self.tower_orientation_angles_deg
            ],
            "cop_area_sqft":                 round(self.cop_area_sqft, 2),
            "cop_min_dimension_m":           round(self.cop_min_dimension_m, 3),
            # Derived
            "footprint_utilization_pct":     round(self.footprint_utilization_pct, 2),
            "leftover_utilization_pct":      round(self.leftover_utilization_pct, 2),
            "n_towers_placed":               self.n_towers_placed,
            "open_space_consolidation":      round(self.open_space_consolidation, 4),
            "largest_open_area_sqft":        round(self.largest_open_area_sqft, 2),
            "edge_alignment_ratio":          round(self.edge_alignment_ratio, 4),
            "target_plate_area_sqft":        round(self.target_plate_area_sqft, 2),
            "actual_plate_area_sqft":        round(self.actual_plate_area_sqft, 2),
        }


# ── Main computation function ─────────────────────────────────────────────────

def compute_placement_debug_metrics(
    envelope_result,   # EnvelopeResult (from envelope_engine.services.envelope_service)
    placement_result,  # PlacementResult (from placement_engine.services.placement_service)
) -> PlacementDebugMetrics:
    """
    Derive all 8 placement quality metrics from existing pipeline outputs.

    This function does NOT re-run any geometry algorithm.  It only reads
    fields that are already present on EnvelopeResult and PlacementResult.

    Parameters
    ----------
    envelope_result  : EnvelopeResult produced by compute_envelope().
    placement_result : PlacementResult produced by compute_placement().

    Returns
    -------
    PlacementDebugMetrics — fully populated, ready for logging or serialisation.
    """
    envelope_poly    = getattr(envelope_result, "envelope_polygon", None)
    cop_poly         = getattr(envelope_result, "common_plot_polygon", None)
    edge_audit       = getattr(envelope_result, "edge_margin_audit", None) or []
    footprints       = getattr(placement_result, "footprints", None) or []
    building_h_m     = float(getattr(placement_result, "building_height_m", 0.0) or 0.0)

    # ── 1. Envelope area ──────────────────────────────────────────────────────
    envelope_area = float(getattr(envelope_result, "envelope_area_sqft", 0.0) or 0.0)

    # ── 2. Total footprint area ───────────────────────────────────────────────
    footprint_area = sum(float(fp.area_sqft or 0.0) for fp in footprints)

    # Target vs actual plate areas (sqft) — advisory only.
    target_plate_area_sqft = float(
        getattr(placement_result, "target_plate_area_sqft", 0.0) or 0.0
    )
    actual_plate_area_sqft = 0.0
    if footprints:
        # Use average footprint area as "actual" plate size.
        actual_plate_area_sqft = footprint_area / float(len(footprints))

    # ── 3 & 4. Leftover area + compactness ───────────────────────────────────
    leftover_area   = 0.0
    compactness     = 0.0
    leftover_poly   = None

    if envelope_poly is not None and not envelope_poly.is_empty:
        if footprints and building_h_m > 0:
            spacing_buffers = [
                compute_exclusion_zone(fp.footprint_polygon, building_h_m)
                for fp in footprints
            ]
            union_buffers = unary_union(spacing_buffers)
            try:
                leftover_poly = envelope_poly.difference(union_buffers)
            except Exception:
                # Geometry precision edge case — fall back to full envelope
                leftover_poly = envelope_poly
        else:
            leftover_poly = envelope_poly

        if leftover_poly is not None and not leftover_poly.is_empty:
            leftover_area = float(leftover_poly.area)
            perimeter = float(leftover_poly.length)
            if perimeter > 0:
                compactness = round(4.0 * math.pi * leftover_poly.area / (perimeter ** 2), 4)

    # ── 5. Road frontage length ───────────────────────────────────────────────
    road_frontage_dxf = 0.0
    for edge in edge_audit:
        if isinstance(edge, dict) and edge.get("edge_type") == "ROAD":
            road_frontage_dxf += float(edge.get("length_dxf", 0.0))
    road_frontage_m = road_frontage_dxf * DXF_TO_METRES

    # ── 6. Per-tower orientation angles ──────────────────────────────────────
    orientation_angles = [
        float(fp.orientation_angle_deg) for fp in footprints
    ]

    # ── 7. COP area ───────────────────────────────────────────────────────────
    cop_area = float(getattr(envelope_result, "common_plot_area_sqft", 0.0) or 0.0)

    # ── 8. COP minimum dimension ──────────────────────────────────────────────
    cop_min_dim_m = 0.0
    if cop_poly is not None and not cop_poly.is_empty:
        minx, miny, maxx, maxy = cop_poly.bounds
        width_m  = (maxx - minx) * DXF_TO_METRES
        height_m = (maxy - miny) * DXF_TO_METRES
        cop_min_dim_m = round(min(width_m, height_m), 3)

    # ── Derived ratios ────────────────────────────────────────────────────────
    footprint_util = (
        round(footprint_area / envelope_area * 100.0, 2)
        if envelope_area > 0 else 0.0
    )
    leftover_util = (
        round(leftover_area / envelope_area * 100.0, 2)
        if envelope_area > 0 else 0.0
    )

    # Dominant open-space metric: largest leftover component vs total leftover.
    largest_open_area = 0.0
    open_space_consolidation = 0.0
    if leftover_poly is not None and not leftover_poly.is_empty:
        if getattr(leftover_poly, "geom_type", None) == "Polygon":
            geoms = [leftover_poly]
        else:
            geoms = [g for g in getattr(leftover_poly, "geoms", []) if not g.is_empty]

        if geoms:
            areas = [float(g.area) for g in geoms]
            total_leftover = sum(areas)
            largest_open_area = max(areas)
            if total_leftover > 0:
                open_space_consolidation = largest_open_area / total_leftover

    # Edge alignment ratio — max across towers.
    edge_alignment_ratio = 0.0
    if envelope_poly is not None and not envelope_poly.is_empty and footprints:
        boundary = envelope_poly.boundary
        for fp in footprints:
            poly = fp.footprint_polygon
            try:
                perim = float(poly.length)
                if perim <= 0:
                    continue
                inter = poly.boundary.intersection(boundary)
                overlap_len = float(inter.length)
                ratio = overlap_len / perim
                if ratio > edge_alignment_ratio:
                    edge_alignment_ratio = ratio
            except Exception:
                continue

    return PlacementDebugMetrics(
        envelope_area_sqft=round(envelope_area, 2),
        footprint_area_sqft=round(footprint_area, 2),
        leftover_area_sqft=round(leftover_area, 2),
        leftover_compactness_score=compactness,
        road_frontage_length_m=round(road_frontage_m, 3),
        tower_orientation_angles_deg=orientation_angles,
        cop_area_sqft=round(cop_area, 2),
        cop_min_dimension_m=cop_min_dim_m,
        footprint_utilization_pct=footprint_util,
        leftover_utilization_pct=leftover_util,
        n_towers_placed=len(footprints),
        open_space_consolidation=open_space_consolidation,
        largest_open_area_sqft=largest_open_area,
        edge_alignment_ratio=edge_alignment_ratio,
        target_plate_area_sqft=target_plate_area_sqft,
        actual_plate_area_sqft=actual_plate_area_sqft,
    )


# ── GeoJSON debug layer builder ───────────────────────────────────────────────

def build_debug_geojson(
    envelope_result,   # EnvelopeResult
    placement_result,  # PlacementResult
) -> Dict[str, Any]:
    """
    Build a GeoJSON FeatureCollection with 5 debug visualization layers.

    Layer order (matches typical SVG z-order for rendering):
      1. buildable_envelope   — outermost legal buildable area
      2. cop_area             — COP reservation (render before buffers)
      3. spacing_buffer       — H/3 exclusion zone per tower
      4. leftover_polygon     — residual area after spacing buffers
      5. selected_footprint   — actual placed tower footprint (topmost)

    Each feature's ``properties.layer`` key identifies which layer it belongs
    to so the frontend can style it independently.

    Parameters
    ----------
    envelope_result  : EnvelopeResult from compute_envelope().
    placement_result : PlacementResult from compute_placement().

    Returns
    -------
    GeoJSON FeatureCollection dict — safe to JSON-serialise directly.
    """
    envelope_poly  = getattr(envelope_result, "envelope_polygon", None)
    cop_poly       = getattr(envelope_result, "common_plot_polygon", None)
    footprints     = getattr(placement_result, "footprints", None) or []
    building_h_m   = float(getattr(placement_result, "building_height_m", 0.0) or 0.0)
    spacing_req_m  = float(getattr(placement_result, "spacing_required_m", 0.0) or 0.0)
    packing_mode   = getattr(placement_result, "packing_mode", None)

    features: List[Dict[str, Any]] = []

    # ── Layer 1: buildable_envelope ───────────────────────────────────────────
    if envelope_poly is not None and not envelope_poly.is_empty:
        features.append({
            "type": "Feature",
            "geometry": _geom_to_geojson(envelope_poly),
            "properties": {
                "layer":      "buildable_envelope",
                "area_sqft":  round(float(envelope_poly.area), 2),
                "label":      "Buildable Envelope",
            },
        })

    # ── Layer 2: cop_area ─────────────────────────────────────────────────────
    if cop_poly is not None and not cop_poly.is_empty:
        minx, miny, maxx, maxy = cop_poly.bounds
        w_m = (maxx - minx) * DXF_TO_METRES
        h_m = (maxy - miny) * DXF_TO_METRES
        features.append({
            "type": "Feature",
            "geometry": _geom_to_geojson(cop_poly),
            "properties": {
                "layer":            "cop_area",
                "area_sqft":        round(float(cop_poly.area), 2),
                "min_dimension_m":  round(min(w_m, h_m), 3),
                "cop_strategy":     getattr(envelope_result, "cop_strategy", None),
                "label":            "Common Open Plot (COP)",
            },
        })

    # ── Layers 3 & 5: per-tower spacing_buffer + selected_footprint ───────────
    # Build spacing buffers first so we can also derive the leftover polygon.
    spacing_buffers = []
    for i, fp in enumerate(footprints):
        fp_poly = fp.footprint_polygon
        exclusion = compute_exclusion_zone(fp_poly, building_h_m)
        spacing_buffers.append(exclusion)

        # Layer 3: spacing_buffer
        features.append({
            "type": "Feature",
            "geometry": _geom_to_geojson(exclusion),
            "properties": {
                "layer":              "spacing_buffer",
                "tower_index":        i,
                "spacing_required_m": round(spacing_req_m, 3),
                "label": (
                    f"Tower {i + 1} Spacing Buffer "
                    f"(H/3 = {spacing_req_m:.1f} m)"
                ),
            },
        })

    # ── Layer 4: leftover_polygon ─────────────────────────────────────────────
    if envelope_poly is not None and not envelope_poly.is_empty:
        try:
            if spacing_buffers:
                union_buffers = unary_union(spacing_buffers)
                leftover = envelope_poly.difference(union_buffers)
            else:
                leftover = envelope_poly

            if leftover is not None and not leftover.is_empty:
                perimeter   = float(leftover.length)
                area        = float(leftover.area)
                compactness = (
                    round(4.0 * math.pi * area / (perimeter ** 2), 4)
                    if perimeter > 0 else 0.0
                )
                features.append({
                    "type": "Feature",
                    "geometry": _geom_to_geojson(leftover),
                    "properties": {
                        "layer":              "leftover_polygon",
                        "area_sqft":          round(area, 2),
                        "compactness_score":  compactness,
                        "label":              "Leftover (Unplaceable) Area",
                    },
                })
        except Exception:
            # Geometry precision failure — skip leftover layer rather than crash
            pass

    # ── Layer 5: selected_footprint (rendered on top) ─────────────────────────
    for i, fp in enumerate(footprints):
        features.append({
            "type": "Feature",
            "geometry": _geom_to_geojson(fp.footprint_polygon),
            "properties": {
                "layer":                 "selected_footprint",
                "tower_index":           i,
                "area_sqft":             round(float(fp.area_sqft), 2),
                "width_m":               round(float(fp.width_m), 3),
                "depth_m":               round(float(fp.depth_m), 3),
                "orientation_angle_deg": round(float(fp.orientation_angle_deg), 2),
                "orientation_label":     fp.orientation_label,
                "aspect_ratio":          round(float(fp.aspect_ratio), 3),
                "label":                 f"Tower {i + 1} Footprint",
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "n_towers_placed":    len(footprints),
            "building_height_m":  building_h_m,
            "spacing_required_m": spacing_req_m,
            "packing_mode":       packing_mode,
            "coordinate_system":  "DXF_feet_SRID0",
            "layer_order": [
                "buildable_envelope",
                "cop_area",
                "spacing_buffer",
                "leftover_polygon",
                "selected_footprint",
            ],
        },
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _geom_to_geojson(geom) -> Optional[Dict[str, Any]]:
    """
    Convert a Shapely geometry to a GeoJSON geometry dict.

    Returns None if the geometry is absent, empty, or cannot be mapped
    (e.g. degenerate single-point result after float clipping).
    """
    if geom is None:
        return None
    try:
        if geom.is_empty:
            return None
        return mapping(geom)
    except Exception:
        return None
