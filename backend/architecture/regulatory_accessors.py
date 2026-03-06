from __future__ import annotations

"""
architecture.regulatory_accessors
---------------------------------

Centralised accessors for GDCR/NBC-backed regulatory constants.

All code that depends on a particular GDCR.yaml key path should go
through these helpers so that regulatory thresholds have a single
authoritative source and fallback behaviour.
"""

from rules_engine.rules.loader import get_gdcr_config


def get_cop_required_fraction() -> float:
    """
    Return the required common open-plot fraction from GDCR.yaml.

    YAML path:
        common_open_plot.required_fraction

    Fallback:
        0.10 (10 %) — preserves existing behaviour when the key
        is missing or malformed.
    """
    try:
        gdcr = get_gdcr_config()
        return float(gdcr.get("common_open_plot", {}).get("required_fraction", 0.10))
    except Exception:
        return 0.10


def get_height_band(height_m: float) -> str:
    """
    Map building height to LOW_RISE / MID_RISE / HIGH_RISE using GDCR.yaml.

    YAML path:
        height_band_rules.low_rise_max_m
        height_band_rules.mid_rise_max_m

    Fallback:
        low_rise_max_m = 10.0
        mid_rise_max_m = 15.0

    Semantics (unchanged from existing engine):
        if height <= low_max  → "LOW_RISE"
        elif height <= mid_max → "MID_RISE"
        else                   → "HIGH_RISE"
    """
    try:
        gdcr = get_gdcr_config()
        band_cfg = gdcr.get("height_band_rules", {}) or {}
        low_max = float(band_cfg.get("low_rise_max_m", 10.0))
        mid_max = float(band_cfg.get("mid_rise_max_m", 15.0))
    except Exception:
        low_max = 10.0
        mid_max = 15.0

    if height_m <= low_max:
        return "LOW_RISE"
    if height_m <= mid_max:
        return "MID_RISE"
    return "HIGH_RISE"


def get_max_permissible_height_by_road_width(road_width_m: float) -> float:
    """
    Return the maximum permissible building height (m) given road width (m).

    YAML path:
        height_rules.road_width_height_map

    Behaviour:
        - Finds first entry with road_width_m <= road_max, returns its max_height.
        - If no entry matches, returns the last max_height.
    """
    gdcr = get_gdcr_config()
    height_cfg = gdcr.get("height_rules", {}) or {}
    height_map = height_cfg.get("road_width_height_map", []) or []
    if not height_map:
        # Fallback: extremely permissive; caller should still enforce other caps.
        return float("inf")

    for entry in height_map:
        try:
            if road_width_m <= float(entry["road_max"]):
                return float(entry["max_height"])
        except (KeyError, TypeError, ValueError):
            continue
    # Fallback to last entry's max_height if no threshold matched cleanly
    last = height_map[-1]
    try:
        return float(last["max_height"])
    except (KeyError, TypeError, ValueError):
        return float("inf")


def get_max_fsi() -> float:
    """
    Return the maximum permissible FSI from GDCR.yaml.

    YAML path (primary):
        fsi_rules.premium_tiers[*].resulting_cap  (highest value across all tiers)

    YAML path (legacy fallback):
        fsi_rules.maximum_fsi

    Fallback:
        4.0 — highest cap from CGDCR 2017 premium tiers.

    NOTE: This returns the ABSOLUTE maximum FSI (corridor-eligible, all tiers).
    For plot-specific dynamic caps (based on corridor eligibility), use
    get_dynamic_max_fsi() instead.

    Bug fix: The previous implementation looked for key 'maximum_fsi' which
    does not exist in GDCR.yaml.  The YAML defines tiers via 'premium_tiers'
    with 'resulting_cap' values (1.8 base, 2.7, 3.6, 4.0).  The old fallback
    of 2.7 was incorrect — it silently capped FSI at the first tier value
    instead of the true absolute maximum of 4.0.
    """
    try:
        gdcr = get_gdcr_config()
        fsi_cfg = gdcr.get("fsi_rules", {}) or {}
        tiers = fsi_cfg.get("premium_tiers") or []
        if tiers:
            caps = [float(t.get("resulting_cap", 0.0)) for t in tiers]
            return max(caps) if caps else float(fsi_cfg.get("maximum_fsi", 4.0))
        # Legacy fallback for configs that use maximum_fsi key directly
        return float(fsi_cfg.get("maximum_fsi", 4.0))
    except Exception:
        return 4.0


def get_dynamic_max_fsi(plot_area_sqft: float, road_width_m: float) -> float:
    """
    Compute a dynamic max FSI cap based on premium tiers and corridor rules.

    Current behaviour:
      - If corridor_rule is present and road_width >= road_width_min_m,
        treat the plot as corridor-eligible (buffer-based spatial check can be
        added later), and return the highest resulting_cap.
      - Otherwise, return the first tier's resulting_cap when present, or
        fall back to the global max_fsi.
    """
    gdcr = get_gdcr_config()
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}
    tiers = fsi_cfg.get("premium_tiers") or []
    corridor_rule = fsi_cfg.get("corridor_rule") or {}
    eligible_if = corridor_rule.get("eligible_if") or {}

    road_width_min = float(eligible_if.get("road_width_min_m", 36.0))

    corridor_eligible = road_width_m >= road_width_min

    if tiers:
        try:
            highest_cap = max(float(t.get("resulting_cap", 0.0)) for t in tiers)
        except Exception:
            highest_cap = 0.0

        try:
            first_cap = float(tiers[0].get("resulting_cap", 0.0))
        except Exception:
            first_cap = highest_cap

        if corridor_eligible:
            return highest_cap
        return first_cap

    return get_max_fsi()


def get_max_ground_coverage_pct() -> float:
    """
    Return the maximum permissible ground coverage percentage from GDCR.yaml.

    YAML path:
        ground_coverage.max_percentage_dw3

    Fallback:
        40.0 — current GDCR default used elsewhere.
    """
    try:
        gdcr = get_gdcr_config()
        return float(gdcr.get("ground_coverage", {}).get("max_percentage_dw3", 40.0))
    except Exception:
        return 40.0

