"""
utils.geometry_validation
------------------------
Validate geometries before returning from the planning pipeline.

Checks: polygon validity, self-intersections, minimum dimension constraints.
Uses Shapely validation and optional repair (buffer(0)).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import LineString, Polygon

try:
    from shapely.validation import make_valid
except ImportError:
    def make_valid(geom):
        if getattr(geom, "is_valid", lambda: True)():
            return geom
        return getattr(geom, "buffer", lambda x: geom)(0)

logger = logging.getLogger(__name__)


def validate_polygon(
    poly: Any,
    min_area_sqft: float = 0.0,
    min_dimension_dxf: float = 0.0,
    repair: bool = True,
) -> Tuple[bool, Optional[Polygon], str]:
    """
    Validate a polygon: is_valid, no self-intersection, optional min area/dimension.

    Returns
    -------
    (valid, repaired_polygon, message)
    """
    if poly is None:
        return False, None, "geometry is None"
    if getattr(poly, "is_empty", True):
        return False, None, "geometry is empty"

    if not getattr(poly, "is_valid", lambda: True)():
        if repair:
            try:
                poly = make_valid(poly)
                if hasattr(poly, "geoms"):
                    poly = max(poly.geoms, key=lambda g: getattr(g, "area", 0))
            except Exception as e:
                return False, None, f"invalid and repair failed: {e}"
        else:
            return False, None, "geometry is invalid"

    if getattr(poly, "area", 0) < min_area_sqft:
        return False, poly, f"area {getattr(poly, 'area', 0)} < min {min_area_sqft}"

    if min_dimension_dxf > 0 and hasattr(poly, "minimum_rotated_rectangle"):
        try:
            mrr = poly.minimum_rotated_rectangle
            if mrr and not mrr.is_empty and hasattr(mrr, "exterior"):
                coords = list(mrr.exterior.coords)
                sides = []
                for i in range(len(coords) - 1):
                    a, b = coords[i], coords[i + 1]
                    sides.append((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
                if sides and min(sides) ** 0.5 < min_dimension_dxf:
                    return False, poly, "minimum dimension below constraint"
        except Exception:
            pass

    return True, poly, "OK"


def validate_polygon_strict(
    poly: Any,
    min_area_sqft: float = 0.0,
    min_width_dxf: float = 0.0,
    repair: bool = True,
) -> Tuple[bool, Optional[Polygon], str]:
    """
    Strong validation: validity, no self-intersection, min area, min width.
    min_width_dxf: minimum of the two dimensions of the minimum rotated rectangle.
    """
    valid, repaired, msg = validate_polygon(
        poly,
        min_area_sqft=min_area_sqft,
        min_dimension_dxf=min_width_dxf,
        repair=repair,
    )
    if not valid or repaired is None:
        return valid, repaired, msg
    if not repaired.is_valid:
        return False, repaired, "geometry invalid after repair"
    try:
        from shapely.validation import explain_validity
        reason = explain_validity(repaired)
        if reason != "Valid Geometry":
            return False, repaired, f"validity: {reason}"
    except Exception:
        pass
    return True, repaired, "OK"


def validate_linestring(
    ls: Any,
    min_length_dxf: float = 0.0,
) -> Tuple[bool, Optional[Any], str]:
    """Validate LineString: non-empty, valid, optionally min length."""
    if ls is None:
        return False, None, "geometry is None"
    if getattr(ls, "is_empty", True):
        return False, None, "empty"
    if not getattr(ls, "is_valid", lambda: True)():
        return False, None, "invalid"
    if getattr(ls, "length", 0) < min_length_dxf:
        return False, ls, f"length < {min_length_dxf}"
    return True, ls, "OK"


def validate_geojson_geometry(geom_dict: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Ensure a GeoJSON geometry dict is valid. Returns the same or repaired GeoJSON, or None.
    """
    if not geom_dict or not isinstance(geom_dict, dict):
        return geom_dict
    try:
        from shapely.geometry import shape as geo_shape
        shp = geo_shape(geom_dict)
        if shp.is_empty:
            return None
        if not shp.is_valid:
            shp = make_valid(shp)
            if hasattr(shp, "geoms"):
                shp = max(shp.geoms, key=lambda g: getattr(g, "area", 0))
        return shp.__geo_interface__
    except Exception:
        return geom_dict
