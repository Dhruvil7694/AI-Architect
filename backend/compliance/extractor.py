from __future__ import annotations

"""
backend.compliance.extractor
----------------------------

Read-only metric extraction layer that derives a flattened ComplianceContext
from upstream layout contracts and plot metadata. This module must not
recompute geometry: it consumes only numeric metrics and configuration.
"""

from dataclasses import dataclass

from tp_ingestion.models import Plot

from residential_layout.building_aggregation import BuildingLayoutContract

from .context import ComplianceContext
from .gdcr_config import GdcrConfig
from .metrics import validate_compliance_context


@dataclass(frozen=True)
class ComplianceMetricExtractorInput:
    """
    Container for the upstream inputs required to derive ComplianceContext.

    This deliberately excludes any geometry types beyond what the layout
    contracts already encapsulate; the extractor must not call polygon
    operations directly.
    """

    plot: Plot
    building: BuildingLayoutContract
    gdcr: GdcrConfig


class ComplianceMetricExtractor:
    """
    Deterministic, read-only extractor that computes derived metrics once
    and assembles a ComplianceContext instance suitable for rule evaluation.
    """

    def build_context(self, data: ComplianceMetricExtractorInput) -> ComplianceContext:
        plot = data.plot
        building = data.building
        gdcr = data.gdcr

        # Plot-level metrics (SI units only)
        plot_area_sqm = float(plot.plot_area_sqm)
        road_width_m = float(getattr(plot, "road_width_m", 0.0) or 0.0)

        # Building-level metrics from Phase 5 contract
        total_bua_sqm = float(building.total_unit_area)
        total_floors = int(building.total_floors)
        building_height_m = float(building.building_height_m)

        # Deterministic building FSI (no geometry recomputation).
        building_fsi = total_bua_sqm / plot_area_sqm if plot_area_sqm > 0 else 0.0

        # Permissible FSI and height from GDCR configuration.
        building_fsi_limit = float(gdcr.fsi_rules.maximum_fsi)
        building_height_limit_m = float(
            gdcr.height_rules.max_height_for_road_width(road_width_m)
        )

        # Ground coverage: use configured cap if present; actual utilisation
        # remains an upstream responsibility for now.
        gc_limit_pct = float(gdcr.parking_rules.max_ground_coverage_pct_dw3 or 0.0)

        context = ComplianceContext(
            ruleset_id=gdcr.regulation_name,
            ruleset_version=gdcr.version,
            development_category_code=_parse_development_category_code(
                gdcr.authority_category
            ),
            plot_area_sqm=plot_area_sqm,
            plot_frontage_m=0.0,
            road_width_m=road_width_m,
            plot_is_corner=False,
            building_height_m=building_height_m,
            building_height_limit_m=building_height_limit_m,
            building_total_builtup_area_sqm=total_bua_sqm,
            building_fsi=building_fsi,
            building_fsi_limit=building_fsi_limit,
            building_ground_coverage_pct=None,
            building_ground_coverage_present=False,
            building_ground_coverage_limit_pct=gc_limit_pct,
            building_number_of_floors=total_floors,
            building_number_of_basements=0,
            building_has_stilt=False,
            structure_number_of_stairs=0,
            structure_required_min_stairs=0,
            structure_stair_min_width_m=0.0,
            structure_stair_max_riser_m=0.0,
            structure_stair_min_tread_m=0.0,
            structure_lift_count=0,
            structure_lift_required=False,
            safety_has_fire_stair=False,
            safety_has_external_stair=False,
            safety_fire_sprinkler_required=False,
            safety_fire_sprinkler_provided=False,
            safety_fire_detection_required=False,
            safety_fire_detection_provided=False,
            safety_refuge_required=False,
            safety_refuge_provided=False,
            parking_required_total=0,
            parking_provided_total=0,
            fire_requires_refuge=bool(
                gdcr.fire_rules.refuge_area_trigger_height_m is not None
                and building_height_m
                > gdcr.fire_rules.refuge_area_trigger_height_m
            ),
            fire_requires_noc=bool(
                gdcr.fire_rules.fire_noc_trigger_height_m is not None
                and building_height_m
                > gdcr.fire_rules.fire_noc_trigger_height_m
            ),
            environment_requires_rainwater_harvesting=gdcr.environment_rules.rainwater_harvesting_required,
            environment_has_rainwater_harvesting=False,
            environment_requires_solar_hot_water=bool(
                gdcr.environment_rules.solar_water_heating_trigger_builtup_sqm
                is not None
                and total_bua_sqm
                > gdcr.environment_rules.solar_water_heating_trigger_builtup_sqm
            ),
            environment_has_solar_hot_water=False,
            accessibility_lift_reaches_all_floors=False,
            accessibility_basic_compliant=False,
        )

        validate_compliance_context(context)
        return context


def _parse_development_category_code(authority_category: str) -> int:
    """
    Map a string like 'D1' to an integer code (1). Falls back to 0 when
    parsing fails, but remains deterministic.
    """
    if not authority_category:
        return 0
    authority_category = authority_category.strip().upper()
    if authority_category.startswith("D"):
        suffix = authority_category[1:]
        try:
            return int(suffix)
        except ValueError:
            return 0
    return 0

