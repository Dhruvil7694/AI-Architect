"""
placement_engine/geometry/spacing_enforcer.py
----------------------------------------------
Two responsibilities:

A) EXCLUSION ZONE — applied DURING packing (packer.py calls compute_exclusion_zone):
   Computes the full H/3 buffer around a placed footprint so the next tower
   cannot overlap or come too close.

   IMPORTANT: we use the FULL spacing_dxf as the buffer radius, NOT half.
   This guarantees that any footprint placed OUTSIDE the exclusion zone has
   a face-to-face clear distance of AT LEAST spacing_dxf from the source
   footprint.

   Old (wrong):  exclusion = footprint.buffer(spacing_dxf / 2)
   Correct:      exclusion = footprint.buffer(spacing_dxf)         ← this module

B) POST-PLACEMENT AUDIT — called after all towers are placed:
   Independently measures the actual face-to-face gap for every pair (i, j)
   and emits a structured audit entry per pair.

   Gap is measured with Shapely's .distance() which returns the nearest-point
   Euclidean distance — the correct GDCR metric for "clear distance between
   parallel faces".

GDCR Reference
--------------
GDCR Table 6.25 — Inter-building spacing:
    required_m = max(building_height_m / 3, minimum_spacing_m)
    applies_to = "parallel_facing_walls"
"""

from __future__ import annotations

import math
from typing import Optional

import yaml
from pathlib import Path
from shapely.geometry import Polygon

from placement_engine.geometry import METRES_TO_DXF, DXF_TO_METRES


# ── GDCR config loader ─────────────────────────────────────────────────────────

def _load_gdcr_inter_building() -> dict:
    """Return the inter_building_margin section of GDCR.yaml."""
    gdcr_path = Path(__file__).resolve().parents[3] / "GDCR.yaml"
    with open(gdcr_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg.get("inter_building_margin", {})


# ── Spacing computation ────────────────────────────────────────────────────────

def required_spacing_m(building_height_m: float) -> float:
    """
    Return the required inter-building clear distance in metres per GDCR.

    Formula: max(H / 3, minimum_spacing_m)
    The minimum_spacing_m default (3.0 m) is loaded from GDCR.yaml.
    """
    cfg = _load_gdcr_inter_building()
    min_spacing = float(cfg.get("minimum_spacing_m", 3.0))
    return max(building_height_m / 3.0, min_spacing)


def required_spacing_dxf(building_height_m: float) -> float:
    """Same as required_spacing_m but in DXF feet."""
    return required_spacing_m(building_height_m) * METRES_TO_DXF


# ── Exclusion zone (used by packer during placement) ──────────────────────────

def compute_exclusion_zone(
    footprint:          Polygon,
    building_height_m:  float,
) -> Polygon:
    """
    Return the full H/3 buffer around *footprint*.

    Any subsequent tower must be placed OUTSIDE this zone, guaranteeing a
    face-to-face gap of at least required_spacing_dxf(building_height_m).

    Parameters
    ----------
    footprint         : Placed tower footprint (Shapely Polygon, DXF feet).
    building_height_m : Building height in metres.

    Returns
    -------
    Shapely Polygon — the exclusion zone.
    """
    spacing_dxf = required_spacing_dxf(building_height_m)
    return footprint.buffer(spacing_dxf)


# ── Post-placement gap audit ───────────────────────────────────────────────────

def audit_spacing(
    footprints:         list[Polygon],
    building_height_m:  float,
) -> list[dict]:
    """
    Independently verify the face-to-face gap for every pair of placed towers.

    Emits one structured audit entry per pair.  A FAIL here after using the
    correct full-buffer packing indicates a floating-point geometry edge case
    and must be flagged in the PlacementResult status.

    Parameters
    ----------
    footprints        : Ordered list of placed footprint Polygons (DXF feet).
    building_height_m : Building height in metres (same for all towers in this
                        simple model; future extension can accept per-tower heights).

    Returns
    -------
    List of audit dicts, one per unique pair (i, j) with i < j.
    """
    req_m    = required_spacing_m(building_height_m)
    req_dxf  = req_m * METRES_TO_DXF
    formula  = f"H({building_height_m}m) / 3 = {building_height_m / 3:.3f}m, min={req_m:.3f}m"
    cfg = _load_gdcr_inter_building()
    clause = f"GDCR {cfg.get('reference', 'Table 6.25')}"

    entries: list[dict] = []

    for i in range(len(footprints)):
        for j in range(i + 1, len(footprints)):
            gap_dxf = footprints[i].distance(footprints[j])
            gap_m   = gap_dxf * DXF_TO_METRES
            status  = "PASS" if gap_m >= req_m - 1e-6 else "FAIL"

            entries.append({
                "pair":              [i, j],
                "gap_dxf":           round(gap_dxf, 4),
                "gap_m":             round(gap_m, 4),
                "required_m":        round(req_m, 4),
                "buffer_applied_dxf": round(req_dxf, 4),
                "status":            status,
                "gdcr_clause":       clause,
                "formula":           formula,
            })

    return entries


def any_spacing_fail(audit_entries: list[dict]) -> bool:
    """Return True if any audit entry has status == 'FAIL'."""
    return any(e["status"] == "FAIL" for e in audit_entries)
