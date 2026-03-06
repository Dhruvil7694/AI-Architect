from __future__ import annotations

from typing import Dict, Any

from architecture.feasibility.regulatory_metrics import (
    _get_gdcr_fsi,
    COP_REQUIRED_FRACTION,
)
from rules_engine.rules.loader import get_gdcr_config

from tp_ingestion.models import Plot
from services.plot_service import get_plot_by_public_id


def _effective_cop_area_sqm(plot_area_sqm: float) -> float:
    """
    Required COP area per GDCR: applies only when plot_area > threshold (default 2000 sqm).
    Required = max(required_fraction × plot_area, minimum_total_area_sqm).
    Returns 0.0 when plot is at or below the threshold (COP not required).
    """
    try:
        cop_cfg = get_gdcr_config().get("common_open_plot", {}) or {}
        threshold_sqm = float(cop_cfg.get("applies_if_plot_area_above_sqm", 2000.0) or 2000.0)
        min_sqm = float(cop_cfg.get("minimum_total_area_sqm", 0.0) or 0.0)
    except Exception:
        threshold_sqm = 2000.0
        min_sqm = 0.0

    if plot_area_sqm <= threshold_sqm:
        return 0.0  # COP not required for plots at or below the threshold

    by_fraction = plot_area_sqm * COP_REQUIRED_FRACTION
    if min_sqm <= 0.0:
        return by_fraction
    return max(by_fraction, min_sqm)


def compute_site_metrics(plot_id: str) -> Dict[str, Any]:
    """
    Compute baseline site feasibility metrics for a plot.

    This is intentionally lightweight:
      - Uses Plot area directly.
      - Uses GDCR config (via regulatory_metrics helpers) to determine
        permissible FSI and COP requirements.
      - COP area = max(10% of plot, minimum_total_area_sqm) so it matches
        the envelope carver (e.g. 200 sqm minimum can yield ~13% on smaller plots).
    """
    plot: Plot = get_plot_by_public_id(plot_id)

    plot_area_sqm = float(plot.plot_area_sqm)
    base_fsi, max_fsi = _get_gdcr_fsi()

    max_bua_sqm = plot_area_sqm * max_fsi
    cop_area_sqm = _effective_cop_area_sqm(plot_area_sqm)

    return {
        "plotId": f"{plot.tp_scheme}-{plot.fp_number}",
        "plotAreaSqm": plot_area_sqm,
        "baseFSI": base_fsi,
        "maxFSI": max_fsi,
        "maxBUA": max_bua_sqm,
        "copAreaSqm": cop_area_sqm,
        # For now we expose a simple label; future work can use real strategy.
        "copStrategy": "central",
    }


__all__ = ["compute_site_metrics"]

