"""
architecture.feasibility.regulatory_metrics
--------------------------------------------

Exposes permissible vs achieved FSI, GC, COP, and spacing from existing
engine outputs and GDCR config. Does not recompute formulas; reuses
values already produced by envelope, placement, and rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from architecture.regulatory_accessors import get_cop_required_fraction
from common.units import sqft_to_sqm

# COP required fraction (GDCR-driven; defaults to 10% for backward compatibility)
COP_REQUIRED_FRACTION: float = get_cop_required_fraction()


@dataclass
class RegulatoryMetrics:
    """Regulatory metrics for feasibility reporting."""

    # FSI
    base_fsi: float
    max_fsi: float
    achieved_fsi: float
    fsi_utilization_pct: float

    # Ground coverage
    permissible_gc_pct: float
    achieved_gc_pct: float

    # Common open plot
    cop_required_sqft: float
    cop_provided_sqft: float

    # Spacing (inter-building)
    spacing_required_m: float
    spacing_provided_m: Optional[float]  # None if single tower


def _get_gdcr_fsi() -> tuple[float, float]:
    """Return (base_fsi, max_fsi) from GDCR config, honouring premium tiers."""
    from rules_engine.rules.loader import get_gdcr_config

    gdcr = get_gdcr_config()
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}
    base = float(fsi_cfg.get("base_fsi", 1.8))

    tiers = fsi_cfg.get("premium_tiers") or []
    if tiers:
        try:
            max_ = float(max(float(t.get("resulting_cap", 0.0)) for t in tiers))
        except Exception:
            max_ = float(fsi_cfg.get("maximum_fsi", 2.7))
    else:
        max_ = float(fsi_cfg.get("maximum_fsi", 2.7))

    return base, max_


def _get_gdcr_max_gc_pct() -> float:
    """Return max ground coverage % from GDCR config."""
    from rules_engine.rules.loader import get_gdcr_config
    gdcr = get_gdcr_config()
    return float(gdcr.get("ground_coverage", {}).get("max_percentage_dw3", 40.0))


def build_regulatory_metrics(
    *,
    plot_area_sqft: float,
    total_bua_sqft: float,
    achieved_gc_pct: float,
    cop_provided_sqft: float,
    spacing_required_m: float,
    spacing_provided_m: Optional[float] = None,
    permissible_gc_pct: Optional[float] = None,
) -> RegulatoryMetrics:
    """
    Build RegulatoryMetrics from pipeline outputs and GDCR config.

    FSI: achieved_fsi = total_bua_sqft / plot_area_sqft; permissible from config.
    GC: achieved_gc_pct is supplied by the caller — typically built footprint / plot
        when placement exists, else envelope-based (see feasibility RISKS.md).
    COP: required = 10% of plot_area_sqft; provided from envelope.
    Spacing: from placement result.
    """
    base_fsi, max_fsi = _get_gdcr_fsi()
    achieved_fsi = (total_bua_sqft / plot_area_sqft) if plot_area_sqft > 0 else 0.0
    permissible_fsi = max_fsi  # use max as the "permissible" for utilization
    fsi_util = (achieved_fsi / permissible_fsi * 100.0) if permissible_fsi > 0 else 0.0

    perm_gc = permissible_gc_pct if permissible_gc_pct is not None else _get_gdcr_max_gc_pct()

    # COP: only required when plot area exceeds the GDCR threshold (default 2000 sq.m).
    # The threshold is defined in GDCR.yaml: common_open_plot.applies_if_plot_area_above_sqm.
    # Previous implementation always computed COP regardless of plot size — fixed here.
    try:
        from rules_engine.rules.loader import get_gdcr_config as _get_gdcr
        _gdcr = _get_gdcr()
        _cop_cfg = _gdcr.get("common_open_plot") or {}
        _cop_threshold_sqm = float(_cop_cfg.get("applies_if_plot_area_above_sqm", 2000.0))
        _cop_min_sqm = float(_cop_cfg.get("minimum_total_area_sqm", 200.0))
    except Exception:
        _cop_threshold_sqm = 2000.0
        _cop_min_sqm = 200.0

    _plot_area_sqm = sqft_to_sqm(plot_area_sqft)
    if _plot_area_sqm > _cop_threshold_sqm:
        cop_required = max(plot_area_sqft * COP_REQUIRED_FRACTION,
                           _cop_min_sqm / 0.09290304)  # min in sq.ft
    else:
        cop_required = 0.0  # COP not required for plots <= threshold

    return RegulatoryMetrics(
        base_fsi=base_fsi,
        max_fsi=max_fsi,
        achieved_fsi=round(achieved_fsi, 4),
        fsi_utilization_pct=round(fsi_util, 2),
        permissible_gc_pct=perm_gc,
        achieved_gc_pct=achieved_gc_pct,
        cop_required_sqft=round(cop_required, 2),
        cop_provided_sqft=round(cop_provided_sqft, 2),
        spacing_required_m=spacing_required_m,
        spacing_provided_m=spacing_provided_m,
    )
