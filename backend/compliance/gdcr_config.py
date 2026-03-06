from __future__ import annotations

"""
backend.compliance.gdcr_config
------------------------------

Lightweight loader for the CGDCR configuration YAML used by the deterministic
Phase E compliance engine. This is not the rule engine itself; it is a typed
view over GDCR.yaml that exposes only the numeric parameters needed to derive
input metrics (e.g. permissible FSI, height vs. road width bands).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass(frozen=True)
class RoadWidthHeightBand:
    road_max_m: float
    max_height_m: float


@dataclass(frozen=True)
class GdcrHeightRules:
    road_width_height_bands: List[RoadWidthHeightBand]
    airport_noc_required: bool

    def max_height_for_road_width(self, road_width_m: float) -> float:
        """
        Deterministically pick the first band whose road_max_m >= road_width_m.
        Falls back to the highest band if none match.
        """
        for band in self.road_width_height_bands:
            if road_width_m <= band.road_max_m:
                return band.max_height_m
        # Defensive fallback: last band
        return self.road_width_height_bands[-1].max_height_m


@dataclass(frozen=True)
class GdcrFsiRules:
    base_fsi: float
    # Deprecated fields retained for backward compatibility; premium tiers
    # and corridor rules are now the authoritative source of FSI caps.
    chargeable_fsi: float
    maximum_fsi: float


@dataclass(frozen=True)
class GdcrParkingRules:
    max_ground_coverage_pct_dw3: Optional[float] = None


@dataclass(frozen=True)
class GdcrFireRules:
    refuge_area_trigger_height_m: Optional[float] = None
    fire_noc_trigger_height_m: Optional[float] = None


@dataclass(frozen=True)
class GdcrEnvironmentRules:
    rainwater_harvesting_required: bool
    solid_waste_bin_required: bool
    solar_water_heating_trigger_builtup_sqm: Optional[float]


@dataclass(frozen=True)
class GdcrConfig:
    regulation_name: str
    authority_category: str
    applicable_use: str
    version: str

    fsi_rules: GdcrFsiRules
    height_rules: GdcrHeightRules
    parking_rules: GdcrParkingRules
    fire_rules: GdcrFireRules
    environment_rules: GdcrEnvironmentRules


def load_gdcr_config(yaml_path: Path) -> GdcrConfig:
    """
    Parse GDCR.yaml once into a strongly-typed configuration object. This
    function performs no rule evaluation; it only exposes numeric parameters.
    """
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    meta = data.get("meta", {})
    fsi = data.get("fsi_rules", {})
    height = data.get("height_rules", {})
    ground_coverage = data.get("ground_coverage", {})
    fire = data.get("fire_safety", {})
    environmental = data.get("environmental", {})

    bands: List[RoadWidthHeightBand] = []
    for row in height.get("road_width_height_map", []):
        bands.append(
            RoadWidthHeightBand(
                road_max_m=float(row["road_max"]),
                max_height_m=float(row["max_height"]),
            )
        )

    fsi_rules = GdcrFsiRules(
        base_fsi=float(fsi.get("base_fsi", 0.0)),
        chargeable_fsi=float(fsi.get("chargeable_fsi", 0.0)),
        maximum_fsi=float(
            fsi.get("maximum_fsi")
            or max(
                (tier.get("resulting_cap", 0.0) for tier in fsi.get("premium_tiers", [])),
                default=0.0,
            )
        ),
    )

    parking_rules = GdcrParkingRules(
        max_ground_coverage_pct_dw3=float(
            ground_coverage.get("max_percentage_dw3", 0.0)
        )
        if "max_percentage_dw3" in ground_coverage
        else None,
    )

    fire_rules = GdcrFireRules(
        refuge_area_trigger_height_m=float(
            fire.get("refuge_area_if_height_above", 0.0)
        )
        if "refuge_area_if_height_above" in fire
        else None,
        fire_noc_trigger_height_m=float(
            fire.get("fire_noc_required_if_height_above", 0.0)
        )
        if "fire_noc_required_if_height_above" in fire
        else None,
    )

    env_rules = GdcrEnvironmentRules(
        rainwater_harvesting_required=bool(
            environmental.get("rainwater_harvesting_required", False)
        ),
        solid_waste_bin_required=bool(
            environmental.get("solid_waste_bin_required", False)
        ),
        solar_water_heating_trigger_builtup_sqm=float(
            environmental.get("solar_water_heating_required_if_builtup_above", 0.0)
        )
        if "solar_water_heating_required_if_builtup_above" in environmental
        else None,
    )

    height_rules = GdcrHeightRules(
        road_width_height_bands=bands,
        airport_noc_required=bool(height.get("airport_noc_required", False)),
    )

    return GdcrConfig(
        regulation_name=str(meta.get("regulation_name", "")),
        authority_category=str(meta.get("authority_category", "")),
        applicable_use=str(meta.get("applicable_use", "")),
        version=str(meta.get("version", "")),
        fsi_rules=fsi_rules,
        height_rules=height_rules,
        parking_rules=parking_rules,
        fire_rules=fire_rules,
        environment_rules=env_rules,
    )

