"""
floorplan_engine/geometry/polygon_utils.py
------------------------------------------
Shapely helper functions for the circulation core engine.

Handles GeoJSON ↔ Shapely conversion, DXF ↔ local-metre projection,
and the critical ``ensure_single_polygon`` guard (R2-2).
"""

from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import Polygon, mapping, shape

from common.units import DXF_TO_METRES, METRES_TO_DXF, SQFT_TO_SQM

from floorplan_engine.models import AxisFrame, DualGeom


# ── GeoJSON ↔ Shapely ────────────────────────────────────────────────────────

def geojson_to_polygon(geojson: dict) -> Polygon:
    """Parse a GeoJSON Polygon dict into a Shapely Polygon."""
    return shape(geojson)


def polygon_to_geojson(poly: Polygon) -> dict:
    """Convert a Shapely Polygon to a GeoJSON dict."""
    return mapping(poly)


# ── DXF ↔ Local-metre projection ────────────────────────────────────────────

def local_to_dxf(poly_m: Polygon, frame: AxisFrame) -> Polygon:
    """
    Back-project a polygon from local-metre (L, S) coords to DXF feet.

    Each local point (l, s) maps to DXF via::

        dxf_x = origin_x + l * lx + s * sx
        dxf_y = origin_y + l * ly + s * sy

    where (lx, ly) and (sx, sy) are the DXF displacement per metre along
    the L and S axes respectively.
    """
    ox, oy = frame.origin_dxf
    lx, ly = frame.l_vec_dxf
    sx, sy = frame.s_vec_dxf

    def _project(coord: tuple[float, float]) -> tuple[float, float]:
        l, s = coord
        return (ox + l * lx + s * sx, oy + l * ly + s * sy)

    exterior = [_project(c) for c in poly_m.exterior.coords]
    holes = [[_project(c) for c in ring.coords] for ring in poly_m.interiors]
    return Polygon(exterior, holes)


def dxf_to_local(poly_dxf: Polygon, frame: AxisFrame) -> Polygon:
    """
    Project a DXF-feet polygon into local-metre (L, S) coords.

    Inverse of ``local_to_dxf``.  Uses dot products with the L/S unit
    vectors (in DXF space) to recover local coordinates.
    """
    ox, oy = frame.origin_dxf
    lx, ly = frame.l_vec_dxf
    sx, sy = frame.s_vec_dxf

    # L and S vectors in DXF are already per-metre, so their squared
    # magnitudes give the conversion factor.
    l_mag2 = lx * lx + ly * ly
    s_mag2 = sx * sx + sy * sy

    def _unproject(coord: tuple[float, float]) -> tuple[float, float]:
        dx = coord[0] - ox
        dy = coord[1] - oy
        l = (dx * lx + dy * ly) / l_mag2
        s = (dx * sx + dy * sy) / s_mag2
        return (l, s)

    exterior = [_unproject(c) for c in poly_dxf.exterior.coords]
    holes = [[_unproject(c) for c in ring.coords] for ring in poly_dxf.interiors]
    return Polygon(exterior, holes)


# ── Area conversion ──────────────────────────────────────────────────────────

def footprint_area_sqm(poly_dxf: Polygon) -> float:
    """Return the area of a DXF-feet polygon in square metres."""
    return poly_dxf.area * SQFT_TO_SQM


# ── Dual-geom convenience ───────────────────────────────────────────────────

def make_dual(poly_m: Polygon, frame: AxisFrame) -> DualGeom:
    """Create a DualGeom from a local-metre polygon + axis frame."""
    return DualGeom(local_m=poly_m, dxf=local_to_dxf(poly_m, frame))


# ── MultiPolygon guard (R2-2) ───────────────────────────────────────────────

def ensure_single_polygon(geom) -> Optional[Polygon]:
    """
    After ``.intersection()`` the result may be MultiPolygon, empty, or
    a GeometryCollection.  This normalises the output:

    - MultiPolygon → keep the largest polygon by area
    - Polygon → return as-is
    - Empty / other → return None
    """
    if geom is None or geom.is_empty:
        return None
    gtype = geom.geom_type
    if gtype == "Polygon":
        return geom if geom.area > 0 else None
    if gtype == "MultiPolygon":
        polys = [g for g in geom.geoms if g.geom_type == "Polygon" and g.area > 0]
        return max(polys, key=lambda g: g.area) if polys else None
    if gtype == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type == "Polygon" and g.area > 0]
        return max(polys, key=lambda g: g.area) if polys else None
    return None


# ── GeoJSON feature helpers ──────────────────────────────────────────────────

def make_feature(poly: Polygon, layer: str, **props) -> dict:
    """Create a GeoJSON Feature dict for one polygon."""
    return {
        "type": "Feature",
        "properties": {"layer": layer, **props},
        "geometry": mapping(poly),
    }


def make_feature_collection(features: list[dict]) -> dict:
    """Wrap a list of GeoJSON Feature dicts into a FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "features": features,
    }
