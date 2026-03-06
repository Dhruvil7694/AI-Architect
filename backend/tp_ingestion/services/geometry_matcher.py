"""
geometry_matcher.py
-------------------
Spatially matches FP number text labels (Points) to plot polygons.

Strategy
--------
1. Containment pass: for each label, find the polygon that contains its
   insertion point (via STRtree).
2. Nearest-neighbour fallback: for labels that had no containing polygon,
   find the closest polygon within snap_tolerance.
3. Conflict resolution: if multiple labels claim the same polygon, keep
   the label whose insertion point is closest to the polygon's centroid;
   displaced labels are re-queued for another nearest-neighbour attempt
   against only unassigned polygons.

This three-step approach handles two common DXF quality issues:
  • Public-purpose / description labels (e.g. "GARDEN") placed inside an
    FP polygon alongside the numeric FP label — the numeric label wins
    because it is almost always closer to the centroid.
  • FP labels accidentally placed inside a neighbouring plot's polygon —
    conflict resolution pushes them out to the correct (unassigned) polygon.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)


@dataclass
class MatchedPlot:
    """A polygon successfully matched to an FP number label."""

    fp_number: str
    polygon: Polygon
    match_method: str  # "contains" | "nearest" | "conflict-resolved"


def match_fp_to_polygons(
    polygons: List[Polygon],
    labels: List[Tuple[str, Point]],
    snap_tolerance: float = 1.0,
) -> Tuple[List[MatchedPlot], List[str]]:
    """
    Match FP number labels to polygons using a three-step strategy:
    containment → nearest-neighbour fallback → conflict resolution.

    Parameters
    ----------
    polygons       : list of Shapely Polygons from the DXF
    labels         : list of (fp_number_text, shapely.Point) from the DXF
    snap_tolerance : max distance for the nearest-neighbour fallback

    Returns
    -------
    matched   : list of MatchedPlot (one per label, deduplicated by FP number)
    unmatched : list of fp_number strings that could not be matched
    """
    if not polygons or not labels:
        logger.warning("No polygons or labels provided — nothing to match.")
        return [], [lbl for lbl, _ in labels]

    tree = STRtree(polygons)

    # ── Pass 1: containment + nearest-neighbour ──────────────────────────────
    # polygon_index (int) → list of (fp_text, point, distance_to_centroid)
    claims: Dict[int, List[Tuple[str, Point, float]]] = {}
    no_match: List[Tuple[str, Point]] = []

    for fp_text, point in labels:
        poly_idx = _find_containing(point, polygons, tree)

        if poly_idx is None:
            poly_idx = _find_nearest(point, polygons, tree, snap_tolerance)

        if poly_idx is None:
            no_match.append((fp_text, point))
            continue

        centroid = polygons[poly_idx].centroid
        dist = point.distance(centroid)
        claims.setdefault(poly_idx, []).append((fp_text, point, dist))

    # ── Pass 2: conflict resolution ──────────────────────────────────────────
    # For each polygon with multiple claimants, the one closest to the centroid
    # wins; displaced labels enter a retry queue.
    assigned: Dict[int, str] = {}          # poly_idx → winning fp_text
    retry_queue: List[Tuple[str, Point]] = []

    for poly_idx, claimants in claims.items():
        if len(claimants) == 1:
            fp_text, _, _ = claimants[0]
            assigned[poly_idx] = fp_text
        else:
            # Priority: numeric FP labels (pure integers or "n/n" format) beat
            # non-numeric description labels (GARDEN, S.E.W.S.H, etc.).
            # Within each priority tier, the label closest to the centroid wins.
            claimants_sorted = sorted(
                claimants,
                key=lambda c: (0 if _is_fp_number(c[0]) else 1, c[2]),
            )
            winner_text, _, _ = claimants_sorted[0]
            assigned[poly_idx] = winner_text
            for fp_text, point, _ in claimants_sorted[1:]:
                logger.debug(
                    "Conflict: '%s' displaced from polygon (area=%.1f) by '%s'. "
                    "Queuing for retry.",
                    fp_text, polygons[poly_idx].area, winner_text,
                )
                retry_queue.append((fp_text, point))

    # ── Pass 3: retry displaced labels against unassigned polygons ───────────
    taken_indices: Set[int] = set(assigned.keys())
    unassigned_polys = [
        (i, p) for i, p in enumerate(polygons) if i not in taken_indices
    ]
    unmatched: List[str] = []

    if unassigned_polys and retry_queue:
        retry_polys = [p for _, p in unassigned_polys]
        retry_tree = STRtree(retry_polys)
        retry_idx_map = {j: i for j, (i, _) in enumerate(unassigned_polys)}

        for fp_text, point in retry_queue:
            local_idx = _find_containing(point, retry_polys, retry_tree)
            if local_idx is None:
                local_idx = _find_nearest(point, retry_polys, retry_tree, snap_tolerance * 5)

            if local_idx is not None:
                global_idx = retry_idx_map[local_idx]
                assigned[global_idx] = fp_text
                taken_indices.add(global_idx)
                # remove from unassigned so it can't be claimed again
                unassigned_polys = [(i, p) for i, p in unassigned_polys if i != global_idx]
                logger.debug("Retry success: '%s' → polygon idx %d", fp_text, global_idx)
            else:
                logger.warning("FP %s could not be matched to any polygon.", fp_text)
                unmatched.append(fp_text)
    else:
        for fp_text, _ in retry_queue:
            logger.warning("FP %s could not be matched (no unassigned polygons left).", fp_text)
            unmatched.append(fp_text)

    # Add original no-match labels
    for fp_text, _ in no_match:
        logger.warning("FP %s could not be matched to any polygon.", fp_text)
        unmatched.append(fp_text)

    # ── Build result ─────────────────────────────────────────────────────────
    matched: List[MatchedPlot] = []
    original_claim_map: Dict[str, int] = {}
    for poly_idx, claimants in claims.items():
        for fp_text, _, _ in claimants:
            original_claim_map[fp_text] = poly_idx

    for poly_idx, fp_text in assigned.items():
        original_idx = original_claim_map.get(fp_text)
        if original_idx == poly_idx:
            method = "contains" if _point_inside(
                next(pt for t, pt, _ in claims[poly_idx] if t == fp_text),
                polygons[poly_idx],
            ) else "nearest"
        else:
            method = "conflict-resolved"
        matched.append(MatchedPlot(fp_number=fp_text, polygon=polygons[poly_idx], match_method=method))

    logger.info(
        "Matching complete: %d matched (%d after conflict resolution), "
        "%d unmatched out of %d labels",
        len(matched), len([m for m in matched if m.match_method == "conflict-resolved"]),
        len(unmatched), len(labels),
    )
    return matched, unmatched


# ── Internal helpers ─────────────────────────────────────────────────────────

def _find_containing(
    point: Point, polygons: List[Polygon], tree: STRtree
) -> Optional[int]:
    """Return the index of the first polygon that contains point, or None."""
    for idx in tree.query(point):
        if polygons[idx].contains(point):
            return idx
    return None


def _find_nearest(
    point: Point, polygons: List[Polygon], tree: STRtree, tolerance: float
) -> Optional[int]:
    """Return the index of the nearest polygon within tolerance, or None."""
    idx = tree.nearest(point)
    if idx is None:
        return None
    if point.distance(polygons[idx]) <= tolerance:
        return idx
    return None


def _point_inside(point: Point, polygon: Polygon) -> bool:
    return polygon.contains(point)


def _is_fp_number(text: str) -> bool:
    """
    Return True if text looks like a valid FP plot number.
    Accepts pure integers ("5", "130") and sub-plot format ("160/1").
    Rejects description labels like "GARDEN", "S.E.W.S.H", "(Parking)".
    """
    import re
    return bool(re.match(r'^\d+(/\d+)?$', text.strip()))
