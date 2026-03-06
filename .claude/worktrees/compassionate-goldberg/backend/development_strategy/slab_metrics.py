"""
development_strategy/slab_metrics.py
-------------------------------------
Extract slab-level metrics from FloorSkeleton. No geometry recomputation;
all values come from skeleton.area_summary and skeleton.unit_zones.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SlabMetrics:
    """
    Slab-level metrics for the Development Strategy Engine.

    All areas in sq.m. Band lists have one entry per UnitZone; order matches
    skeleton.unit_zones. band_orientation_axes[i] is that zone's orientation_axis.
    """

    gross_slab_area_sqm: float
    core_area_sqm: float
    corridor_area_sqm: float
    net_usable_area_sqm: float
    efficiency_ratio: float
    band_lengths_m: list[float]
    band_widths_m: list[float]
    band_orientation_axes: list[str]


def compute_slab_metrics(skeleton) -> SlabMetrics:
    """
    Build SlabMetrics from an evaluated FloorSkeleton.

    Uses only skeleton.area_summary and skeleton.unit_zones. No geometry
    recomputation. Caller must pass a skeleton that has already been evaluated
    (area_summary populated by skeleton_evaluator.compute_area_summary).

    If area_summary is missing or empty, returns zeros and empty lists.
    """
    summary = getattr(skeleton, "area_summary", None) or {}
    unit_zones = getattr(skeleton, "unit_zones", []) or []

    gross_slab_area_sqm = float(summary.get("footprint_area_sqm", 0.0))
    core_area_sqm = float(summary.get("core_area_sqm", 0.0))
    corridor_area_sqm = float(summary.get("corridor_area_sqm", 0.0))
    net_usable_area_sqm = float(summary.get("unit_area_sqm", 0.0))
    efficiency_ratio = float(summary.get("efficiency_ratio", 0.0))

    band_widths_m = list(summary.get("unit_band_widths", []))
    band_lengths_m = list(summary.get("unit_band_depths", []))
    band_orientation_axes = [getattr(uz, "orientation_axis", "") for uz in unit_zones]

    # If summary had no band keys, lengths may not match unit_zones; align by len(unit_zones)
    n = len(unit_zones)
    if len(band_widths_m) != n and unit_zones:
        band_widths_m = [getattr(uz, "zone_width_m", 0.0) for uz in unit_zones]
    if len(band_lengths_m) != n and unit_zones:
        band_lengths_m = [getattr(uz, "zone_depth_m", 0.0) for uz in unit_zones]

    return SlabMetrics(
        gross_slab_area_sqm=gross_slab_area_sqm,
        core_area_sqm=core_area_sqm,
        corridor_area_sqm=corridor_area_sqm,
        net_usable_area_sqm=net_usable_area_sqm,
        efficiency_ratio=efficiency_ratio,
        band_lengths_m=band_lengths_m,
        band_widths_m=band_widths_m,
        band_orientation_axes=band_orientation_axes,
    )
