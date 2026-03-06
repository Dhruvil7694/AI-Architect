"""
gdcr_engine.rules_loader
------------------------

Thin validated wrapper around the existing rules_engine YAML loader.

Responsibilities
----------------
- Expose a single entry point for accessing parsed GDCR/NBC configuration.
- Validate that mandatory GDCR sections are present; raise descriptive errors
  when configuration is malformed.
- Provide typed accessor helpers so callers never touch raw dict key paths.

Design
------
This module delegates storage and caching to rules_engine.rules.loader so
that GDCR.yaml is loaded exactly once per process.  All additions here are
validation and accessor logic only — no file I/O, no LRU cache of its own.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Delegate raw loading to the existing loader (single source of truth).
from rules_engine.rules.loader import get_gdcr_config, get_nbc_config  # noqa: F401  re-exported

# ---------------------------------------------------------------------------
# Mandatory section keys required for the compliance engine to function.
# ---------------------------------------------------------------------------

_REQUIRED_TOP_LEVEL_KEYS: List[str] = [
    "fsi_rules",
    "height_rules",
    "road_side_margin",
    "side_rear_margin",
    "ground_coverage",
    "access_rules",
]


def validate_gdcr_config() -> Dict[str, Any]:
    """
    Load and validate the GDCR configuration.

    Returns the validated config dict.  Raises ``KeyError`` if a required
    section is absent, ``ValueError`` if a required numeric field is missing
    or non-numeric.

    Usage
    -----
        from gdcr_engine.rules_loader import validate_gdcr_config
        gdcr = validate_gdcr_config()
    """
    gdcr = get_gdcr_config()
    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in gdcr:
            raise KeyError(
                f"GDCR.yaml is missing required section '{key}'. "
                "Please check the configuration file."
            )

    # FSI rules
    fsi = gdcr["fsi_rules"]
    if "base_fsi" not in fsi:
        raise KeyError("GDCR.yaml fsi_rules.base_fsi is required.")
    try:
        float(fsi["base_fsi"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"GDCR.yaml fsi_rules.base_fsi must be numeric: {exc}") from exc

    # Height rules
    height_map = gdcr["height_rules"].get("road_width_height_map")
    if not height_map:
        raise KeyError("GDCR.yaml height_rules.road_width_height_map is empty or missing.")

    # Ground coverage
    gc = gdcr["ground_coverage"]
    if "max_percentage_dw3" not in gc:
        raise KeyError("GDCR.yaml ground_coverage.max_percentage_dw3 is required.")

    return gdcr


# ---------------------------------------------------------------------------
# Typed accessor helpers
# ---------------------------------------------------------------------------

def get_base_fsi() -> float:
    """Return the base (as-of-right) FSI for DW3 Residential (CGDCR R1 zone)."""
    gdcr = get_gdcr_config()
    return float(gdcr["fsi_rules"]["base_fsi"])


def get_fsi_tiers() -> List[Dict[str, Any]]:
    """
    Return the list of premium FSI tier dicts from GDCR.yaml.

    Each tier dict contains at minimum:
        - additional_fsi      : float   (FSI increment above base)
        - resulting_cap       : float   (absolute FSI cap for this tier)
        - jantri_rate_percent : float   (land premium payment %)
        - corridor_required   : bool    (True if plot must be in corridor)
    """
    gdcr = get_gdcr_config()
    return list(gdcr["fsi_rules"].get("premium_tiers") or [])


def get_corridor_rule() -> Dict[str, Any]:
    """
    Return the corridor eligibility rule dict from GDCR.yaml.

    Keys:
        eligible_if.road_width_min_m  : float  (minimum adjacent road width)
        eligible_if.buffer_distance_m : float  (max distance from wide road)
    """
    gdcr = get_gdcr_config()
    return dict(gdcr["fsi_rules"].get("corridor_rule") or {})


def get_height_map() -> List[Dict[str, Any]]:
    """
    Return the road-width → max-height mapping list (GDCR Table 6.23).

    Each entry: {"road_max": float, "max_height": float}
    """
    gdcr = get_gdcr_config()
    return list(gdcr["height_rules"].get("road_width_height_map") or [])


def get_road_side_margin_map() -> List[Dict[str, Any]]:
    """
    Return the road-width → road-side margin mapping list (GDCR Table 6.24).

    Each entry: {"road_max": float, "margin": float}
    """
    gdcr = get_gdcr_config()
    return list(gdcr["road_side_margin"].get("road_width_margin_map") or [])


def get_road_side_height_formula() -> str:
    """
    Return the road-side margin height formula string (e.g. 'H / 5').
    """
    gdcr = get_gdcr_config()
    return str(gdcr["road_side_margin"].get("height_formula", "H / 5"))


def get_road_side_min_margin() -> float:
    """Return the absolute minimum road-side margin (m)."""
    gdcr = get_gdcr_config()
    return float(gdcr["road_side_margin"].get("minimum_road_side_margin", 1.5))


def get_side_rear_margin_map() -> List[Dict[str, Any]]:
    """
    Return the height → side/rear margin mapping list (GDCR Table 6.26).

    Each entry: {"height_max": float, "rear": float, "side": float}
    """
    gdcr = get_gdcr_config()
    return list(gdcr["side_rear_margin"].get("height_margin_map") or [])


def get_max_gc_pct() -> float:
    """Return the maximum permissible ground coverage percentage for DW3."""
    gdcr = get_gdcr_config()
    return float(gdcr["ground_coverage"]["max_percentage_dw3"])


def get_cop_config() -> Dict[str, Any]:
    """Return the common open plot configuration dict from GDCR.yaml."""
    gdcr = get_gdcr_config()
    return dict(gdcr.get("common_open_plot") or {})


def get_min_road_width_dw3() -> float:
    """Return the minimum road width required for DW3 Apartments (m)."""
    gdcr = get_gdcr_config()
    return float(gdcr["access_rules"]["minimum_road_width_for_dw3"])


def get_height_band_config() -> Dict[str, Any]:
    """Return height band thresholds from GDCR.yaml."""
    gdcr = get_gdcr_config()
    return dict(gdcr.get("height_band_rules") or {})
