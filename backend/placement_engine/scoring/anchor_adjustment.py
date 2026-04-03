"""
placement_engine/scoring/anchor_adjustment.py
---------------------------------------------
Lightweight post-processing step that anchors a selected footprint rectangle
to the dominant (longest) edge of the buildable envelope.

This runs AFTER select_best_candidate() and BEFORE the footprint is committed
to the packing result.  It never changes which candidate was chosen; it only
adjusts the position of the chosen rectangle.

Algorithm (Steps 2–4)
---------------------
1. Find the dominant edge — the longest linear segment of the envelope exterior.
2. Construct a LineString for that edge to use as the proximity reference.
3. If the footprint is already close to the dominant edge
   (distance(rectangle, dominant_edge_line) < TOUCH_THRESHOLD_M), do nothing.
4. Otherwise binary-search for the maximum translation distance along the
   inward normal of the dominant edge that still keeps the footprint fully
   inside the envelope.
5. If the anchored position is valid (footprint ⊆ envelope), apply it.
   Otherwise fall back to the largest valid partial translation, or return
   the original footprint unchanged.

The FootprintCandidate dataclass is immutable by convention, so a new instance
is returned when the position changes.  The original is returned on failure.

Units
-----
All geometry is in DXF feet (SRID=0).  The threshold TOUCH_THRESHOLD_M is
converted to DXF feet before the distance check.
"""

from __future__ import annotations

import logging
import math
from typing import Optional, Tuple

from shapely.affinity import translate
from shapely.geometry import LineString, MultiPolygon, Polygon

from placement_engine.geometry import (
    DXF_TO_METRES,
    METRES_TO_DXF,
    FootprintCandidate,
)

logger = logging.getLogger(__name__)

# Footprints closer than this to the envelope boundary are already considered
# "anchored" and are not adjusted.  1.5 m converted at call-time to DXF feet.
TOUCH_THRESHOLD_M: float = 1.5

# Number of bisection iterations used to find the largest valid translation.
_BISECT_ITERS: int = 20


# ── Public API ─────────────────────────────────────────────────────────────────

def anchor_to_dominant_edge(
    candidate: FootprintCandidate,
    envelope: Polygon,
) -> FootprintCandidate:
    """
    Slide *candidate* toward the dominant envelope edge until it touches.

    Parameters
    ----------
    candidate : Selected footprint candidate (from select_best_candidate).
    envelope  : Buildable envelope polygon (DXF feet, SRID=0).

    Returns
    -------
    Adjusted FootprintCandidate with updated footprint_polygon (and unchanged
    area/width/depth/angle fields since the shape does not change, only position).
    Returns *candidate* unchanged on any failure.
    """
    fp = candidate.footprint_polygon
    touch_threshold_dxf = TOUCH_THRESHOLD_M * METRES_TO_DXF

    # ── Step 2: find dominant edge and build its LineString ───────────────────
    dom_edge = _dominant_edge(envelope)
    if dom_edge is None:
        logger.debug("[Anchor] Could not find dominant edge — skipping")
        return candidate

    (x1, y1), (x2, y2) = dom_edge
    dom_edge_line = LineString([(x1, y1), (x2, y2)])

    # ── Step 3: check distance specifically to the dominant edge ─────────────
    dist_to_dom_dxf = fp.distance(dom_edge_line)
    dist_to_dom_m = dist_to_dom_dxf * DXF_TO_METRES

    logger.debug(
        "[Anchor] distance_to_dominant_edge_before: %.3f m (threshold: %.1f m)",
        dist_to_dom_m, TOUCH_THRESHOLD_M,
    )

    if dist_to_dom_dxf <= touch_threshold_dxf:
        logger.debug("[Anchor] Already touching dominant edge — no adjustment needed")
        return candidate

    # ── Compute inward perpendicular direction of dominant edge ───────────────
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        logger.debug("[Anchor] Dominant edge degenerate — skipping")
        return candidate

    # Left-hand perpendicular; flip toward envelope centroid to ensure inward
    nx, ny = -dy / length, dx / length
    cx, cy = envelope.centroid.x, envelope.centroid.y
    ex, ey = (x1 + x2) / 2, (y1 + y2) / 2
    if (nx * (cx - ex) + ny * (cy - ey)) < 0:
        nx, ny = -nx, -ny

    # ── Step 4: binary-search for the maximum valid translation ───────────────
    # Upper bound: current distance to dominant edge plus a small margin.
    max_translation = dist_to_dom_dxf + 1.0

    anchored_fp, translation_dxf = _bisect_anchor(
        fp, envelope, nx, ny, max_translation,
    )

    # ── Step 5: validate and apply ────────────────────────────────────────────
    if anchored_fp is None or translation_dxf < 1e-6:
        logger.debug("[Anchor] Binary search found no valid translation — keeping original")
        return candidate

    translation_m = translation_dxf * DXF_TO_METRES
    final_dist_to_dom_m = anchored_fp.distance(dom_edge_line) * DXF_TO_METRES

    logger.debug(
        "[Anchor] translation_distance: %.3f m | "
        "distance_to_dominant_edge_after: %.4f m",
        translation_m, final_dist_to_dom_m,
    )

    # Build an updated candidate with the new footprint position.
    # Shape, area, width, depth and orientation are unchanged — only position moves.
    return _rebuild_candidate(candidate, anchored_fp)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _dominant_edge(envelope) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """
    Return the (p1, p2) coordinates of the longest exterior edge of *envelope*.

    Exterior edges are the consecutive vertex pairs of the outer ring.
    If *envelope* is a MultiPolygon (e.g. donut from CENTER COP strategy),
    the largest component is used.
    Returns None if the exterior ring has fewer than 2 vertices.
    """
    if isinstance(envelope, MultiPolygon):
        parts = [g for g in envelope.geoms if isinstance(g, Polygon) and not g.is_empty]
        if not parts:
            return None
        envelope = max(parts, key=lambda g: g.area)
    if not isinstance(envelope, Polygon) or envelope.is_empty:
        return None
    coords = list(envelope.exterior.coords)
    if len(coords) < 2:
        return None

    best_len = -1.0
    best_edge = None
    for i in range(len(coords) - 1):   # last coord == first (closed ring)
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        if seg_len > best_len:
            best_len = seg_len
            best_edge = ((x1, y1), (x2, y2))

    return best_edge


def _bisect_anchor(
    fp: Polygon,
    envelope: Polygon,
    nx: float,
    ny: float,
    max_t: float,
) -> Tuple[Optional[Polygon], float]:
    """
    Binary-search for the largest translation distance *t* along (nx, ny)
    such that ``translate(fp, t*nx, t*ny)`` lies entirely inside *envelope*.

    Returns (translated_polygon, t) or (None, 0) if even t=0 fails.
    """
    # Sanity: untranslated footprint must be inside envelope
    if not envelope.contains(fp):
        # Slight precision tolerance — try a tiny inward nudge
        if not envelope.buffer(1e-6).contains(fp):
            return None, 0.0

    lo, hi = 0.0, max_t
    best_fp: Optional[Polygon] = None
    best_t = 0.0

    for _ in range(_BISECT_ITERS):
        mid = (lo + hi) / 2.0
        translated = translate(fp, xoff=mid * nx, yoff=mid * ny)

        # Check: translated footprint must be fully inside envelope
        # Use a tiny buffer tolerance for floating-point edge cases
        if envelope.buffer(1e-4).contains(translated):
            best_fp = translated
            best_t = mid
            lo = mid          # can go further
        else:
            hi = mid          # overshot — reduce

    # Final strict containment check on winner
    if best_fp is not None and not envelope.contains(best_fp):
        # Clip to envelope as last resort
        clipped = best_fp.intersection(envelope)
        if (
            clipped.is_empty
            or clipped.geom_type not in ("Polygon", "MultiPolygon")
            or clipped.area < fp.area * 0.99   # must not lose >1% of area
        ):
            return None, 0.0
        best_fp = clipped if clipped.geom_type == "Polygon" else best_fp

    return best_fp, best_t


def _rebuild_candidate(original: FootprintCandidate, new_poly: Polygon) -> FootprintCandidate:
    """
    Return a new FootprintCandidate identical to *original* except for the
    footprint_polygon, which is replaced with *new_poly*.

    Area, width, depth, and orientation are preserved — the shape did not change,
    only its position inside the envelope.
    """
    return FootprintCandidate(
        footprint_polygon=new_poly,
        area_sqft=original.area_sqft,
        width_dxf=original.width_dxf,
        depth_dxf=original.depth_dxf,
        width_m=original.width_m,
        depth_m=original.depth_m,
        orientation_angle_deg=original.orientation_angle_deg,
        orientation_label=original.orientation_label,
        grid_resolution_dxf=original.grid_resolution_dxf,
        source_component_index=original.source_component_index,
    )
