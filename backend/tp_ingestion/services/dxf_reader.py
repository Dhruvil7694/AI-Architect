"""
dxf_reader.py
-------------
Reads a TP scheme DXF file and extracts:
  - Closed LWPOLYLINE entities as Shapely Polygons (plot boundaries)
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
from shapely.geometry import Point, Polygon

logger = logging.getLogger(__name__)

# Road width text in DXF: "18.00 MT.", "15.00 MT", "12.00 MT.", "24.00 MT.", etc.
_ROAD_WIDTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*M\.?T\.?", re.IGNORECASE)


@dataclass
class DXFReadResult:
    """Container returned by read_dxf()."""

    polygons: List[Polygon] = field(default_factory=list)
    # Each label: (text_string, insertion_point_as_shapely_Point)
    labels: List[Tuple[str, Point]] = field(default_factory=list)
    layer_names: List[str] = field(default_factory=list)
    entity_type_counts: dict = field(default_factory=dict)


def read_dxf(
    dxf_path: str | Path,
    polygon_layers: Optional[List[str]] = None,
    label_layers: Optional[List[str]] = None,
) -> DXFReadResult:
    """
    Parse a DXF file and extract plot polygons and FP number text labels.

    Parameters
    ----------
    dxf_path        : path to the .dxf file
    polygon_layers  : if given, only closed LWPOLYLINE on these layers are
                      extracted (case-insensitive). Default: all layers.
    label_layers    : if given, only TEXT/MTEXT on these layers are extracted
                      (case-insensitive). Default: all layers.

    Returns
    -------
    DXFReadResult
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
    polygons: List[Polygon] = []
    labels: List[Tuple[str, Point]] = []

    for entity in msp:
        etype = entity.dxftype()
        entity_counts[etype] = entity_counts.get(etype, 0) + 1
        entity_layer = entity.dxf.layer.lower()

        if etype == "LWPOLYLINE":
            if poly_filter and entity_layer not in poly_filter:
                continue
            poly = _lwpolyline_to_polygon(entity)
            if poly is not None:
                polygons.append(poly)

        elif etype == "TEXT":
            if label_filter and entity_layer not in label_filter:
                continue
            txt = entity.dxf.text.strip()
            x = entity.dxf.insert.x
            y = entity.dxf.insert.y
            if txt:
                labels.append((txt, Point(x, y)))

        elif etype == "MTEXT":
            if label_filter and entity_layer not in label_filter:
                continue
            # plain_text() strips DXF formatting codes (ezdxf >= 0.17 API)
            raw = entity.plain_text().strip()
            # For multi-line MTEXT like "154\nSALE FOR\nRESIDENCE", take
            # only the first non-empty line so the FP number is clean.
            txt = _first_meaningful_line(raw)
            x = entity.dxf.insert.x
            y = entity.dxf.insert.y
            if txt:
                labels.append((txt, Point(x, y)))

    result.polygons = polygons
    result.labels = labels
    result.entity_type_counts = entity_counts

    logger.info(
        "DXF read complete: %d closed polylines, %d text labels, %d layers",
        len(polygons),
        len(labels),
        len(result.layer_names),
    )
    return result


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


def _lwpolyline_to_polygon(entity) -> Polygon | None:
    """
    Convert a closed LWPOLYLINE entity to a Shapely Polygon.
    Returns None if the polyline is open or has fewer than 3 vertices.
    """
    if not entity.is_closed:
        return None

    points = [(v[0], v[1]) for v in entity.get_points()]
    if len(points) < 3:
        return None

    try:
        poly = Polygon(points)
        if not poly.is_valid:
            poly = poly.buffer(0)  # attempt to repair self-intersections
        return poly if poly.is_valid else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not build polygon from LWPOLYLINE: %s", exc)
        return None


def read_dxf_road_widths(
    dxf_path: str | Path,
    road_text_layers: Optional[List[str]] = None,
) -> List[Tuple[float, Point]]:
    """
    Extract road width labels (e.g. "18.00 MT.", "12.00 MT.") from TEXT/MTEXT
    and return (width_m, insertion_point) for each.

    Parameters
    ----------
    dxf_path           : path to the .dxf file
    road_text_layers   : if given, only TEXT on these layers (e.g. ["ROADNAME"]).
                         Default: all layers (any text matching the pattern).

    Returns
    -------
    List of (width_m: float, Point) in DXF coordinates.
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
