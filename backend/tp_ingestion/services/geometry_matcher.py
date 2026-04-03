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

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree


def _make_strtree(polygons: list) -> STRtree:
    """Build an STRtree compatible with both Shapely 1.x and 2.x."""
    return STRtree(np.array(polygons, dtype=object))

logger = logging.getLogger(__name__)


@dataclass
class MatchedPlot:
    """A polygon successfully matched to an FP number label."""

    fp_number: str
    polygon: Polygon
    label_point: Point
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

    tree = _make_strtree(polygons)

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
    assigned: Dict[int, Tuple[str, Point, str]] = {}  # poly_idx → (fp_text, point, method)
    retry_queue: List[Tuple[str, Point]] = []

    for poly_idx, claimants in claims.items():
        if len(claimants) == 1:
            fp_text, point, _dist = claimants[0]
            method = (
                "contains" if polygons[poly_idx].covers(point) else "nearest"
            )
            assigned[poly_idx] = (fp_text, point, method)
            continue

        # Priority: numeric FP labels beat description labels.
        claimants_sorted = sorted(
            claimants,
            key=lambda c: (0 if _is_fp_number(c[0]) else 1, c[2]),
        )
        winner_text, winner_point, _ = claimants_sorted[0]
        assigned[poly_idx] = (winner_text, winner_point, "conflict-resolved")

        for displaced_fp_text, displaced_point, _dist in claimants_sorted[1:]:
            retry_queue.append((displaced_fp_text, displaced_point))

    # ── Pass 3: retry displaced labels against unassigned polygons ───────────
    taken_indices: Set[int] = set(assigned.keys())
    unassigned_polygon_indices = [i for i in range(len(polygons)) if i not in taken_indices]
    unmatched: List[str] = []

    # PASS 3 (numeric-only, distance-sorted greedy):
    # Build candidate polygons for each displaced numeric label against the
    # currently unassigned polygons. Then assign in order of best (smallest)
    # centroid distance to avoid starving a label with a later, worse match.
    retry_numeric = [(fp_text, point) for fp_text, point in retry_queue if _is_fp_number(fp_text)]
    if retry_numeric and unassigned_polygon_indices:
        unassigned_polys = [polygons[i] for i in unassigned_polygon_indices]
        retry_tree = _make_strtree(unassigned_polys)
        local_to_global = {j: g for j, g in enumerate(unassigned_polygon_indices)}
        expanded_tol = snap_tolerance * 5

        # For each label, compute sorted candidate globals (closest centroid first).
        per_label_candidates: List[Tuple[str, Point, List[int]]] = []
        for fp_text, point in retry_numeric:
            # Containment first if possible, but still allow nearest candidates.
            contain_local = [
                idx
                for idx in retry_tree.query(point)
                if unassigned_polys[idx].covers(point)
            ]

            candidates_local: List[int] = []
            if contain_local:
                candidates_local = contain_local
            else:
                nearby_local = list(retry_tree.query(point.buffer(expanded_tol)))
                # filter by centroid-distance threshold
                candidates_local = [
                    idx
                    for idx in nearby_local
                    if point.distance(unassigned_polys[idx].centroid) <= expanded_tol
                ]

            if not candidates_local:
                continue

            candidates_sorted = sorted(
                candidates_local,
                key=lambda idx: point.distance(unassigned_polys[idx].centroid),
            )
            candidate_globals = [local_to_global[idx] for idx in candidates_sorted]
            per_label_candidates.append((fp_text, point, candidate_globals))

        # Sort labels by their best candidate distance.
        def best_dist(item: Tuple[str, Point, List[int]]) -> float:
            fp_text, point, globals_list = item
            best_global = globals_list[0]
            return point.distance(polygons[best_global].centroid)

        per_label_candidates.sort(key=best_dist)

        taken_in_pass3: Set[int] = set()
        for fp_text, point, candidate_globals in per_label_candidates:
            # pick first candidate polygon not already taken
            chosen: int | None = None
            for gidx in candidate_globals:
                if gidx in taken_in_pass3:
                    continue
                chosen = gidx
                break
            if chosen is None:
                unmatched.append(fp_text)
                continue

            # Finalize assignment
            method = (
                "conflict-resolved"
                if polygons[chosen].covers(point)
                else "nearest"
            )
            assigned[chosen] = (fp_text, point, method)
            taken_indices.add(chosen)
            taken_in_pass3.add(chosen)

        # Any displaced labels that didn't produce candidates are unmatched.
        matched_fp_set = {fp for fp, _pt, _cand in per_label_candidates}
        for fp_text, _point in retry_numeric:
            if fp_text not in matched_fp_set:
                unmatched.append(fp_text)
    # Non-numeric displaced labels are treated as unmatched; they are not needed
    # to map FP numbers to Plot polygons.
    for fp_text, _point in retry_queue:
        if not _is_fp_number(fp_text):
            unmatched.append(fp_text)

    # Add original no-match labels
    for fp_text, _point in no_match:
        logger.warning("FP %s could not be matched to any polygon.", fp_text)
        unmatched.append(fp_text)

    # ── Build result ─────────────────────────────────────────────────────────
    matched: List[MatchedPlot] = []
    for poly_idx, (fp_text, point, method) in assigned.items():
        matched.append(
            MatchedPlot(
                fp_number=fp_text,
                polygon=polygons[poly_idx],
                label_point=point,
                match_method=method,
            )
        )

    logger.info(
        "Matching complete: %d matched (%d after conflict resolution), %d unmatched out of %d labels",
        len(matched),
        len([m for m in matched if m.match_method == "conflict-resolved"]),
        len(unmatched),
        len(labels),
    )
    return matched, unmatched


# ── Internal helpers ─────────────────────────────────────────────────────────

def _find_containing(
    point: Point, polygons: List[Polygon], tree: STRtree
) -> Optional[int]:
    """
    Return the best polygon for the label point among polygons that contain
    or cover the point.

    Important: for boundary points, `contains()` may fail, while `covers()`
    will succeed. We prefer `contains()` first, and for either case choose
    the polygon whose centroid is closest to the label point.
    """
    contains_candidates: list[int] = []
    cover_candidates: list[int] = []
    near_boundary: list[int] = []  # within 1 DXF unit of boundary

    for idx in tree.query(point.buffer(1.0)):
        poly = polygons[idx]
        if poly.contains(point):
            contains_candidates.append(idx)
        elif poly.covers(point):
            cover_candidates.append(idx)
        elif poly.distance(point) < 1.0:
            near_boundary.append(idx)

    # Merge all candidates, preferring smallest polygon.
    # A label sitting 0.2 units outside a 1500 sqft polygon is almost
    # certainly meant for that polygon, not the 5800 sqft block that
    # technically contains it.
    all_candidates = contains_candidates + cover_candidates + near_boundary
    if all_candidates:
        return min(all_candidates, key=lambda i: polygons[i].area)

    return None


def _find_nearest(
    point: Point, polygons: List[Polygon], tree: STRtree, tolerance: float
) -> Optional[int]:
    """Return the index of the nearest polygon within tolerance, or None."""
    # Shapely STRtree.nearest() returns nearest boundary distance; we want nearest centroid
    # for stable FP mapping, and only within the snap tolerance.
    candidate_idxs = list(tree.query(point.buffer(tolerance)))
    if not candidate_idxs:
        return None

    best_idx: Optional[int] = None
    best_dist = float("inf")
    for idx in candidate_idxs:
        centroid = polygons[idx].centroid
        dist = point.distance(centroid)
        if dist <= tolerance and dist < best_dist:
            best_dist = dist
            best_idx = idx

    return best_idx


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
