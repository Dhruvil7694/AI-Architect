from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from rules_engine.rules.loader import get_gdcr_config


@dataclass(frozen=True)
class SellableAreaSummary:
    plot_area_sq_yards: float
    achieved_fsi: float
    sellable_per_yard: float
    total_sellable_sqft: float
    flat_total_sqft: float
    estimated_rca_per_flat_sqft: float
    efficiency_ratio: float
    segment: str


def _load_sellable_config() -> dict:
    gdcr = get_gdcr_config() or {}
    return gdcr.get("sellable_ratios", {})


def interpolate_sellable_per_yard(fsi: float) -> float:
    """Interpolate sellable-per-yard from FSI using configured breakpoints."""
    cfg = _load_sellable_config()
    breakpoints = cfg.get("fsi_to_sellable_per_yard", [])

    if not breakpoints:
        return fsi * 15.0

    sorted_bp = sorted(breakpoints, key=lambda b: float(b["fsi"]))
    fsi_val = float(fsi)

    if fsi_val <= float(sorted_bp[0]["fsi"]):
        return float(sorted_bp[0]["sellable_per_yard"])

    if fsi_val >= float(sorted_bp[-1]["fsi"]):
        return float(sorted_bp[-1]["sellable_per_yard"])

    for i in range(len(sorted_bp) - 1):
        f0 = float(sorted_bp[i]["fsi"])
        f1 = float(sorted_bp[i + 1]["fsi"])
        s0 = float(sorted_bp[i]["sellable_per_yard"])
        s1 = float(sorted_bp[i + 1]["sellable_per_yard"])
        if f0 <= fsi_val <= f1:
            t = (fsi_val - f0) / (f1 - f0) if f1 != f0 else 0.0
            return s0 + t * (s1 - s0)

    return float(sorted_bp[-1]["sellable_per_yard"])


def compute_rca_from_flat_area(
    flat_total_sqft: float,
    ratio: Optional[float] = None,
    segment: Optional[str] = None,
) -> float:
    """RCA = flat_total_area × efficiency_ratio."""
    if ratio is not None:
        return flat_total_sqft * ratio

    cfg = _load_sellable_config()
    if segment:
        seg_ratios = cfg.get("segment_efficiency", {})
        ratio = float(seg_ratios.get(segment, cfg.get("flat_to_rca_ratio", 0.55)))
    else:
        ratio = float(cfg.get("flat_to_rca_ratio", 0.55))

    return flat_total_sqft * ratio


def compute_rca_from_rooms(room_areas_sqft: List[float]) -> float:
    """RCA = sum of internal room areas (measured wall-to-wall)."""
    return sum(max(0.0, float(a)) for a in room_areas_sqft)


def compute_sellable_area(
    plot_area_sq_yards: float,
    achieved_fsi: float,
    flat_total_sqft: float = 0.0,
    segment: str = "mid",
) -> SellableAreaSummary:
    """Compute complete sellable area summary using industry ratios."""
    sellable_per_yard = interpolate_sellable_per_yard(achieved_fsi)
    total_sellable = plot_area_sq_yards * sellable_per_yard

    cfg = _load_sellable_config()
    seg_ratios = cfg.get("segment_efficiency", {})
    efficiency = float(seg_ratios.get(segment, cfg.get("flat_to_rca_ratio", 0.55)))

    rca_per_flat = compute_rca_from_flat_area(
        flat_total_sqft, segment=segment,
    ) if flat_total_sqft > 0 else 0.0

    return SellableAreaSummary(
        plot_area_sq_yards=plot_area_sq_yards,
        achieved_fsi=achieved_fsi,
        sellable_per_yard=round(sellable_per_yard, 1),
        total_sellable_sqft=round(total_sellable, 0),
        flat_total_sqft=flat_total_sqft,
        estimated_rca_per_flat_sqft=round(rca_per_flat, 0),
        efficiency_ratio=efficiency,
        segment=segment,
    )
