from __future__ import annotations

from typing import Any, Dict, List, Optional

import logging
from shapely.geometry import mapping
from shapely.wkt import loads as load_wkt


logger = logging.getLogger(__name__)


def geometry_to_geojson(geom) -> Optional[Dict[str, Any]]:
    """
    Convert a Shapely geometry to a GeoJSON-like dict. Returns None if empty/invalid.
    """
    if geom is None or getattr(geom, "is_empty", True):
        return None
    try:
        return mapping(geom)
    except Exception:
        return None


def wkt_to_geojson(wkt_string: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Convert a WKT string to a GeoJSON-like dict using Shapely.

    Returns None when the input is empty, cannot be parsed, or results
    in an empty geometry. The output dict is JSON-serialisable.
    """
    if not wkt_string:
        return None

    try:
        geom = load_wkt(wkt_string)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to convert WKT to GeoJSON: %s", exc)
        return None

    if geom.is_empty:
        return None

    return mapping(geom)

