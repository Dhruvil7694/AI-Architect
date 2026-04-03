"""
dxf_reader.py
-------------
Reads a TP scheme DXF file and extracts:
  - Plot polygons using a hybrid three-tier strategy:
    Tier 1: Closed LWPOLYLINE entities → direct Shapely Polygons
    Tier 2: Block subdivision via internal LINE/ARC segments
    Tier 3: Deferred to ingestion_service recovery (segment-based)
  - TEXT / MTEXT entities as (text_value, Point) tuples (FP number labels)

Layer filtering is supported via polygon_layers and label_layers parameters.
For TP14 (PAL, SUDA):
  - FP polygons  → layer "F.P."
  - FP labels    → layer "FINAL F.P."

Relies solely on ezdxf + shapely. No Django imports here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

import ezdxf
import json
import math

from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

# Road width text in DXF: "18.00 MT.", "15.00 MT", "12.00 MT.", "24.00 MT.", etc.
_ROAD_WIDTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*M\.?T\.?", re.IGNORECASE)

# FP number pattern: "133", "160/1", etc.
_FP_NUMBER_RE = re.compile(r"^\d+(/\d+)?$")


def _is_fp_number(text: str) -> bool:
    """Return True if text looks like a valid FP plot number."""
    return bool(_FP_NUMBER_RE.match(text.strip()))


@dataclass
class DXFReadResult:
    """Container returned by read_dxf()."""

    polygons: List[Polygon] = field(default_factory=list)
    # Raw segments (LINE, ARC, open LWPOLYLINE) for debug/recovery.
    segments: List[LineString] = field(default_factory=list)
    # Each label: (text_string, insertion_point_as_shapely_Point)
    labels: List[Tuple[str, Point]] = field(default_factory=list)
    # Overlay labels like BLOCK_NO from CAD (not FP plot identifiers).
    block_labels: List[Tuple[str, Point]] = field(default_factory=list)
    layer_names: List[str] = field(default_factory=list)
    entity_type_counts: dict = field(default_factory=dict)


def read_dxf(
    dxf_path: str | Path,
    polygon_layers: Optional[List[str]] = None,
    label_layers: Optional[List[str]] = None,
    *,
    snap_decimals: int = 2,
    min_polygon_area: float = 50.0,
    polygonize_buffer: float = 0.0,
    debug_output_dir: str | Path | None = None,
) -> DXFReadResult:
    """
    Parse a DXF file and extract plot polygons and FP number text labels.

    Uses a hybrid three-tier extraction strategy:
      Tier 1: Closed LWPOLYLINE → direct polygon (covers ~80% of plots)
      Tier 2: Block subdivision via internal segments (covers ~15%)
      Tier 3: Deferred to ingestion_service (segments kept for recovery)
    """
    dxf_path = Path(dxf_path)
    if not dxf_path.exists():
        raise FileNotFoundError(f"DXF file not found: {dxf_path}")

    poly_filter: Optional[Set[str]] = (
        {l.lower() for l in polygon_layers} if polygon_layers else None
    )
    label_filter: Optional[Set[str]] = (
        {l.lower() for l in label_layers} if label_layers else None
    )

    logger.info("Loading DXF: %s", dxf_path)
    if poly_filter:
        logger.info("  Polygon layer filter  : %s", polygon_layers)
    if label_filter:
        logger.info("  Label layer filter    : %s", label_layers)

    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    result = DXFReadResult()
    result.layer_names = [layer.dxf.name for layer in doc.layers]

    entity_counts: dict[str, int] = {}
    labels: List[Tuple[str, Point]] = []
    block_labels: List[Tuple[str, Point]] = []

    # Tier 1: closed LWPOLYLINE polygons
    tier1_polygons: List[Polygon] = []
    # Segments from non-closed entities (for Tier 2 subdivision + Tier 3 recovery)
    segments: List[LineString] = []

    for entity in msp:
        etype = entity.dxftype()
        entity_counts[etype] = entity_counts.get(etype, 0) + 1
        entity_layer = entity.dxf.layer.lower()

        # ── Text labels ──────────────────────────────────────────────────
        if etype == "TEXT":
            if label_filter and entity_layer not in label_filter:
                if entity_layer != "block_no":
                    continue
            txt = entity.dxf.text.strip()
            x = entity.dxf.insert.x
            y = entity.dxf.insert.y
            if txt:
                if entity_layer == "block_no":
                    block_labels.append((txt, Point(x, y)))
                else:
                    labels.append((txt, Point(x, y)))

        elif etype == "MTEXT":
            if label_filter and entity_layer not in label_filter:
                if entity_layer != "block_no":
                    continue
            raw = entity.plain_text().strip()
            txt = _first_meaningful_line(raw)
            x = entity.dxf.insert.x
            y = entity.dxf.insert.y
            if txt:
                if entity_layer == "block_no":
                    block_labels.append((txt, Point(x, y)))
                else:
                    labels.append((txt, Point(x, y)))

        # ── Geometry entities ────────────────────────────────────────────
        elif etype in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC"):
            if poly_filter and entity_layer not in poly_filter:
                continue

            # Tier 1: extract closed LWPOLYLINE directly as polygon
            if etype == "LWPOLYLINE" and getattr(entity, "is_closed", False):
                poly = _closed_lwpolyline_to_polygon(
                    entity, snap_decimals=snap_decimals
                )
                if poly is not None and poly.area >= min_polygon_area:
                    tier1_polygons.append(poly)
                continue  # Don't also break into segments

            # All other geometry → segments (for Tier 2 + Tier 3)
            new_segments = _entity_to_segments(
                entity, snap_decimals=snap_decimals
            )
            segments.extend(new_segments)

        # ── HATCH boundaries as supplemental polygons ──────────────────
        elif etype == "HATCH":
            # Residential/commercial/public hatches often carry plot
            # boundaries that don't exist as closed LWPOLYLINEs
            hatch_layers = {
                "01residential", "02commercial", "03publicpurpose",
                "04green", "residential",
            }
            if entity_layer not in hatch_layers:
                continue
            try:
                for hpath in entity.paths:
                    if hasattr(hpath, "vertices") and hpath.vertices:
                        coords = [
                            (_snap(float(v[0]), snap_decimals),
                             _snap(float(v[1]), snap_decimals))
                            for v in hpath.vertices
                        ]
                        if len(coords) >= 3:
                            poly = _repair_polygon(Polygon(coords))
                            if poly is not None and poly.area >= min_polygon_area:
                                tier1_polygons.append(poly)
            except Exception:
                pass

    # ── Tier 2a: Deduplicate nested block outlines ──────────────────────
    final_polygons, blocks_removed = _deduplicate_nested_polygons(
        tier1_polygons,
        labels,
        min_polygon_area=min_polygon_area,
    )

    # ── Tier 2b: Subdivide blocks with uncovered labels using segments ──
    # Find blocks that still have 2+ FP labels (they weren't removed because
    # not all labels had nested sub-plots). Try to subdivide them.
    numeric_labels = [
        (txt, pt) for txt, pt in labels if _is_fp_number(txt)
    ]
    blocks_subdivided = 0
    polys_to_add: List[Polygon] = []
    polys_to_remove: List[Polygon] = []

    for poly in final_polygons:
        # Count unique numeric FP labels inside this polygon
        fps_inside: set = set()
        for txt, pt in numeric_labels:
            if poly.buffer(0.5).contains(pt):
                fps_inside.add(txt)
        if len(fps_inside) < 2:
            continue

        # This polygon is a block with multiple FP labels — try subdivision
        sub_polys = _subdivide_block_with_segments(
            poly, segments, min_polygon_area=min_polygon_area
        )
        if len(sub_polys) >= 2:
            # Check that subdivision produces sub-polygons covering the labels
            sub_covered = set()
            for sp in sub_polys:
                for txt, pt in numeric_labels:
                    if sp.buffer(0.5).contains(pt):
                        sub_covered.add(txt)
            if len(sub_covered) > len(fps_inside) * 0.5:
                polys_to_remove.append(poly)
                polys_to_add.extend(sub_polys)
                blocks_subdivided += 1
                logger.info(
                    "Subdivided block (area=%.0f, FPs=%s) into %d sub-polygons",
                    poly.area, sorted(fps_inside), len(sub_polys),
                )

    if polys_to_remove:
        polys_to_remove_set = set(id(p) for p in polys_to_remove)
        final_polygons = [p for p in final_polygons if id(p) not in polys_to_remove_set]
        final_polygons.extend(polys_to_add)

    logger.info(
        "Hybrid extraction: %d Tier1 direct, %d block outlines removed, "
        "%d blocks subdivided, %d final polygons, %d segments for recovery",
        len(tier1_polygons),
        len(blocks_removed),
        blocks_subdivided,
        len(final_polygons),
        len(segments),
    )

    if debug_output_dir:
        _export_debug_geojson(debug_output_dir, segments, final_polygons)

    result.polygons = final_polygons
    result.segments = segments
    result.labels = labels
    result.block_labels = block_labels
    result.entity_type_counts = entity_counts

    logger.info(
        "DXF read complete: %d polygons, %d text labels, %d layers",
        len(final_polygons),
        len(labels),
        len(result.layer_names),
    )
    return result


# ── Tier 1: Closed LWPOLYLINE → Polygon ─────────────────────────────────────


def _closed_lwpolyline_to_polygon(
    entity, *, snap_decimals: int
) -> Optional[Polygon]:
    """
    Convert a closed LWPOLYLINE entity directly to a Shapely Polygon,
    using ezdxf's path flattening for correct arc/bulge handling.
    """
    from ezdxf.path import make_path

    raw_pts = list(entity.get_points(format="xyseb"))
    if len(raw_pts) < 3:
        return None

    has_bulge = any(abs(p[4]) > 1e-10 for p in raw_pts)

    if has_bulge:
        # Use ezdxf's built-in path flattening for accurate arc interpolation.
        # distance=0.3 gives smooth curves (max 0.3 DXF-unit deviation from true arc).
        try:
            path = make_path(entity)
            flat_pts = list(path.flattening(distance=0.3))
            coords = [
                (_snap(float(p.x), snap_decimals), _snap(float(p.y), snap_decimals))
                for p in flat_pts
            ]
        except Exception:
            coords = [
                (_snap(float(x), snap_decimals), _snap(float(y), snap_decimals))
                for x, y, *_ in raw_pts
            ]
    else:
        # No bulge — just snap the vertices directly
        coords = [
            (_snap(float(x), snap_decimals), _snap(float(y), snap_decimals))
            for x, y, *_ in raw_pts
        ]

    # Deduplicate consecutive identical points
    unique_coords: List[Tuple[float, float]] = []
    for pt in coords:
        if not unique_coords or pt != unique_coords[-1]:
            unique_coords.append(pt)

    if len(unique_coords) < 3:
        return None

    try:
        poly = Polygon(unique_coords)
        return _repair_polygon(poly)
    except Exception:
        return None


def _repair_polygon(poly: Polygon) -> Optional[Polygon]:
    """Validate and repair a polygon. Returns None if unrecoverable."""
    if not poly.is_valid:
        poly = make_valid(poly)

    if isinstance(poly, Polygon):
        return poly if poly.area > 0 else None

    # make_valid can return MultiPolygon; keep the largest component
    if hasattr(poly, "geoms"):
        polys = [g for g in poly.geoms if isinstance(g, Polygon) and g.area > 0]
        if polys:
            return max(polys, key=lambda g: g.area)

    return None


# ── Tier 2: Block Subdivision ────────────────────────────────────────────────


def _deduplicate_nested_polygons(
    tier1_polygons: List[Polygon],
    labels: List[Tuple[str, Point]],
    *,
    min_polygon_area: float,
) -> Tuple[List[Polygon], set]:
    """
    Remove block-outline polygons that contain smaller Tier 1 polygons
    (the actual sub-plots). DXF files often have both the block outline
    and individual sub-plot outlines as separate closed LWPOLYLINEs.

    Strategy:
    1. Match numeric FP labels to polygons (point-in-polygon)
    2. Find "block" polygons containing 2+ numeric labels
    3. Check if OTHER Tier 1 polygons are nested inside the block
    4. If nested sub-plots cover the block's labels, remove the block

    Returns:
        kept_polygons: cleaned polygon list (blocks replaced by sub-plots)
        blocks_removed: set of polygon objects that were removed
    """
    if not tier1_polygons or not labels:
        return tier1_polygons, set()

    numeric_labels = [
        (txt, pt) for txt, pt in labels if _is_fp_number(txt)
    ]

    # Match labels to polygons — track ALL containing polygons per label
    # (a label can be inside both a sub-plot and its parent block)
    label_to_polys: dict[int, List[int]] = {}  # label_idx → [poly_idx, ...]
    for li, (txt, pt) in enumerate(numeric_labels):
        for pi, poly in enumerate(tier1_polygons):
            if poly.buffer(0.5).contains(pt):
                label_to_polys.setdefault(li, []).append(pi)

    # For each polygon, collect its labels
    poly_label_map: dict[int, List[int]] = {}  # poly_idx → [label_idx, ...]
    for li, poly_idxs in label_to_polys.items():
        for pi in poly_idxs:
            poly_label_map.setdefault(pi, []).append(li)

    # Find block polygons (contain 2+ numeric labels that are UNIQUE to them
    # when considering only the unique FP numbers, not duplicate labels)
    block_candidates: List[int] = []
    for pi, label_idxs in poly_label_map.items():
        unique_fps = set(numeric_labels[li][0] for li in label_idxs)
        if len(unique_fps) >= 2:
            block_candidates.append(pi)

    if not block_candidates:
        return tier1_polygons, set()

    blocks_to_remove: set = set()

    for block_idx in block_candidates:
        block_poly = tier1_polygons[block_idx]
        block_area = block_poly.area

        # Find smaller Tier 1 polygons nested inside this block
        nested_sub_plots: List[int] = []
        for pi, poly in enumerate(tier1_polygons):
            if pi == block_idx:
                continue
            if poly.area >= block_area:
                continue
            # Check if sub-plot is mostly inside the block
            if block_poly.contains(poly.representative_point()):
                nested_sub_plots.append(pi)

        if not nested_sub_plots:
            continue

        # Check: do the nested sub-plots cover the block's labels?
        block_label_idxs = poly_label_map.get(block_idx, [])
        block_fps = set(numeric_labels[li][0] for li in block_label_idxs)

        covered_fps: set = set()
        for sub_idx in nested_sub_plots:
            sub_labels = poly_label_map.get(sub_idx, [])
            for li in sub_labels:
                covered_fps.add(numeric_labels[li][0])

        # Only remove the block if ALL its FP labels are covered by nested
        # sub-plots. If some labels have no sub-plot, keep the block so
        # those labels can still match to it downstream.
        if block_fps and block_fps.issubset(covered_fps):
            blocks_to_remove.add(block_idx)
            logger.info(
                "Removing block polygon %d (area=%.0f) — "
                "%d nested sub-plots cover all FPs: %s",
                block_idx,
                block_area,
                len(nested_sub_plots),
                sorted(block_fps),
            )

    if not blocks_to_remove:
        return tier1_polygons, set()

    blocks_removed_polys = {tier1_polygons[i] for i in blocks_to_remove}
    kept = [p for i, p in enumerate(tier1_polygons) if i not in blocks_to_remove]

    return kept, blocks_removed_polys


def _subdivide_block_with_segments(
    block_poly: Polygon,
    segments: List[LineString],
    *,
    min_polygon_area: float,
    bbox_expand: float = 2.0,
) -> List[Polygon]:
    """
    Subdivide a block polygon using nearby LINE/ARC segments.

    Collects all segments intersecting the block's bounding box (expanded
    by `bbox_expand`), adds the block's own boundary edges, runs
    shapely.polygonize, and returns sub-polygons whose representative
    point falls inside the block.
    """
    if not segments:
        return []

    minx, miny, maxx, maxy = block_poly.bounds
    search_box = box(
        minx - bbox_expand, miny - bbox_expand,
        maxx + bbox_expand, maxy + bbox_expand,
    )

    # Collect segments that intersect the block's bounding box
    local_segs: List[LineString] = []
    for seg in segments:
        if seg.intersects(search_box):
            local_segs.append(seg)

    # Add the block polygon's own boundary as segments
    boundary = block_poly.exterior
    coords = list(boundary.coords)
    for i in range(len(coords) - 1):
        edge = LineString([coords[i], coords[i + 1]])
        if edge.length > 1e-6:
            local_segs.append(edge)

    if len(local_segs) < 3:
        return []

    # Polygonize
    merged = unary_union(local_segs)
    sub_polys = list(polygonize(merged))

    # Keep only sub-polygons inside the block
    result: List[Polygon] = []
    for sp in sub_polys:
        if sp.area < min_polygon_area:
            continue
        if block_poly.contains(sp.representative_point()):
            result.append(sp)

    return result


# ── Segment extraction (for Tier 2 + Tier 3 recovery) ───────────────────────


def _first_meaningful_line(text: str) -> str:
    """
    Return the first non-empty line of a (possibly multi-line) string.
    Used to extract the FP number from MTEXT like "154\\nSALE FOR\\nRESIDENCE".
    """
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return text.strip()


def _snap(v: float, decimals: int) -> float:
    return float(round(float(v), decimals))


def _bulge_to_arc_points(
    p1: tuple[float, float],
    p2: tuple[float, float],
    bulge: float,
    snap_decimals: int,
    n_segs: int = 16,
) -> List[tuple[float, float]]:
    """
    Convert a bulge-encoded arc segment (LWPOLYLINE) to approximating chord points.

    Bulge = tan(theta/4) where theta is the arc's included angle (positive = CCW).
    Returns n_segs+1 points along the arc from p1 to p2, including p2.
    Falls back to [p2] if the geometry is degenerate.
    """
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    chord_len = math.hypot(dx, dy)
    if chord_len < 1e-10:
        return [p2]

    theta = 4.0 * math.atan(bulge)
    sin_half = math.sin(theta / 2.0)
    if abs(sin_half) < 1e-12:
        return [p2]

    r = chord_len / (2.0 * abs(sin_half))

    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    perp_x, perp_y = -dy / chord_len, dx / chord_len

    d = math.sqrt(max(0.0, r * r - (chord_len / 2.0) ** 2))

    if bulge > 0:
        cx, cy = mx - d * perp_x, my - d * perp_y
    else:
        cx, cy = mx + d * perp_x, my + d * perp_y

    start_a = math.atan2(y1 - cy, x1 - cx)
    n = max(4, n_segs)
    pts: List[tuple[float, float]] = []
    for i in range(1, n + 1):
        a = start_a + theta * i / n
        x = _snap(cx + r * math.cos(a), snap_decimals)
        y = _snap(cy + r * math.sin(a), snap_decimals)
        pts.append((x, y))
    return pts


def _entity_to_segments(entity, *, snap_decimals: int) -> List[LineString]:
    """
    Convert supported DXF entities into a list of Shapely LineString segments.
    Used for Tier 2 block subdivision and Tier 3 recovery.
    """
    etype = entity.dxftype()

    def snap_xy(x: float, y: float) -> tuple[float, float]:
        return (_snap(x, snap_decimals), _snap(y, snap_decimals))

    segments: List[LineString] = []

    if etype == "LINE":
        start = entity.dxf.start
        end = entity.dxf.end
        (x1, y1) = snap_xy(start.x, start.y)
        (x2, y2) = snap_xy(end.x, end.y)
        if (x1, y1) != (x2, y2):
            segments.append(LineString([(x1, y1), (x2, y2)]))
        return segments

    if etype == "LWPOLYLINE":
        pts = [(v[0], v[1]) for v in entity.get_points()]
        pts = [snap_xy(x, y) for x, y in pts]
        if len(pts) < 2:
            return segments
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            if a != b:
                segments.append(LineString([a, b]))
        # Close loop if polyline is closed.
        if getattr(entity, "is_closed", False) and len(pts) >= 3:
            a = pts[-1]
            b = pts[0]
            if a != b:
                segments.append(LineString([a, b]))
        return segments

    if etype == "POLYLINE":
        pts = []
        for v in entity.vertices():
            loc = getattr(v.dxf, "location", None)
            if loc is None:
                continue
            pts.append(snap_xy(loc.x, loc.y))
        if len(pts) < 2:
            return segments
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            if a != b:
                segments.append(LineString([a, b]))
        if getattr(entity, "is_closed", False) and len(pts) >= 3:
            a = pts[-1]
            b = pts[0]
            if a != b:
                segments.append(LineString([a, b]))
        return segments

    if etype == "ARC":
        center = entity.dxf.center
        radius = float(entity.dxf.radius)
        start_angle = float(entity.dxf.start_angle)
        end_angle = float(entity.dxf.end_angle)

        delta = end_angle - start_angle
        if delta <= 0:
            delta += 360.0

        step_deg = 5.0
        steps = max(12, int(math.ceil(delta / step_deg)))
        angles = [start_angle + delta * (i / steps) for i in range(steps + 1)]
        pts = []
        cx = float(center.x)
        cy = float(center.y)
        for a in angles:
            rad = math.radians(a)
            x = cx + radius * math.cos(rad)
            y = cy + radius * math.sin(rad)
            pts.append(snap_xy(x, y))
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            if a != b:
                segments.append(LineString([a, b]))
        return segments

    return segments


# ── Debug export ─────────────────────────────────────────────────────────────


def _export_debug_geojson(
    debug_output_dir: str | Path,
    segments: List[LineString],
    polygons: List[Polygon],
) -> None:
    """Export intermediate GeoJSON for debugging."""
    from uuid import uuid4

    out_dir = Path(debug_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid4().hex[:8]

    def write(path: Path, obj: object) -> None:
        path.write_text(json.dumps(obj, ensure_ascii=True), encoding="utf-8")

    raw_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"run_id": run_id},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(seg.coords)[0], list(seg.coords)[1]],
                },
            }
            for seg in segments
        ],
    }

    poly_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"run_id": run_id, "area": poly.area},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[x, y] for (x, y) in poly.exterior.coords],
                    ],
                },
            }
            for poly in polygons
        ],
    }

    write(out_dir / "raw_segments.geojson", raw_fc)
    write(out_dir / "final_plots.geojson", poly_fc)


# ── Road width reader (unchanged) ───────────────────────────────────────────


def read_dxf_road_widths(
    dxf_path: str | Path,
    road_text_layers: Optional[List[str]] = None,
) -> List[Tuple[float, Point]]:
    """
    Extract road width labels (e.g. "18.00 MT.", "12.00 MT.") from TEXT/MTEXT
    and return (width_m, insertion_point) for each.
    """
    dxf_path = Path(dxf_path)
    if not dxf_path.exists():
        raise FileNotFoundError(f"DXF file not found: {dxf_path}")

    layer_set: Optional[Set[str]] = (
        {l.lower() for l in road_text_layers} if road_text_layers else None
    )
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    result: List[Tuple[float, Point]] = []

    for entity in msp:
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        layer = entity.dxf.layer.lower()
        if layer_set and layer not in layer_set:
            continue
        if entity.dxftype() == "TEXT":
            txt = entity.dxf.text.strip()
        else:
            txt = entity.plain_text().strip().splitlines()[0].strip() if entity.plain_text() else ""
        m = _ROAD_WIDTH_RE.search(txt)
        if m:
            try:
                width = float(m.group(1))
                x, y = entity.dxf.insert.x, entity.dxf.insert.y
                result.append((width, Point(x, y)))
            except (ValueError, TypeError):
                continue

    logger.info("Road width labels extracted: %d from %s", len(result), dxf_path)
    return result
