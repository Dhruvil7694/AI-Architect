from __future__ import annotations

"""
backend.compliance.metrics
--------------------------

Central registry of ComplianceContext metrics with deterministic metadata:
  - name
  - domain (plot / building / structure / safety / parking / fire / environment / accessibility)
  - type (float / int / bool / str)
  - unit (m, sqm, ratio, count, flag)
  - source (plot / building_contract / gdcr_config / derived)
  - required flag

This registry is used for:
  - schema and unit validation
  - documentation and introspection
  - deterministic handling of missing metrics
"""

from dataclasses import dataclass
from typing import Dict, Literal, Type

from .context import ComplianceContext


MetricDomain = Literal[
    "plot",
    "building",
    "structure",
    "safety",
    "parking",
    "fire",
    "environment",
    "accessibility",
    "global",
]


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    domain: MetricDomain
    py_type: Type
    unit: str
    source: str
    required: bool


METRIC_DEFINITIONS: Dict[str, MetricDefinition] = {
    # Global / admin
    "ruleset_id": MetricDefinition(
        name="ruleset_id",
        domain="global",
        py_type=str,
        unit="",
        source="gdcr_config",
        required=True,
    ),
    "ruleset_version": MetricDefinition(
        name="ruleset_version",
        domain="global",
        py_type=str,
        unit="",
        source="gdcr_config",
        required=True,
    ),
    "development_category_code": MetricDefinition(
        name="development_category_code",
        domain="global",
        py_type=int,
        unit="code",
        source="gdcr_config",
        required=True,
    ),
    # Plot
    "plot_area_sqm": MetricDefinition(
        name="plot_area_sqm",
        domain="plot",
        py_type=float,
        unit="sqm",
        source="plot",
        required=True,
    ),
    "plot_frontage_m": MetricDefinition(
        name="plot_frontage_m",
        domain="plot",
        py_type=float,
        unit="m",
        source="plot",
        required=False,
    ),
    "road_width_m": MetricDefinition(
        name="road_width_m",
        domain="plot",
        py_type=float,
        unit="m",
        source="plot",
        required=True,
    ),
    "plot_is_corner": MetricDefinition(
        name="plot_is_corner",
        domain="plot",
        py_type=bool,
        unit="flag",
        source="plot",
        required=False,
    ),
    # Building
    "building_height_m": MetricDefinition(
        name="building_height_m",
        domain="building",
        py_type=float,
        unit="m",
        source="building_contract",
        required=True,
    ),
    "building_height_limit_m": MetricDefinition(
        name="building_height_limit_m",
        domain="building",
        py_type=float,
        unit="m",
        source="gdcr_config",
        required=True,
    ),
    "building_total_bua_sqm": MetricDefinition(
        name="building_total_bua_sqm",
        domain="building",
        py_type=float,
        unit="sqm",
        source="building_contract",
        required=True,
    ),
    "building_fsi": MetricDefinition(
        name="building_fsi",
        domain="building",
        py_type=float,
        unit="ratio",
        source="derived",
        required=True,
    ),
    "building_fsi_limit": MetricDefinition(
        name="building_fsi_limit",
        domain="building",
        py_type=float,
        unit="ratio",
        source="gdcr_config",
        required=True,
    ),
    "building_ground_coverage_pct": MetricDefinition(
        name="building_ground_coverage_pct",
        domain="building",
        py_type=float,
        unit="percent",
        source="derived",
        required=False,
    ),
    "building_ground_coverage_present": MetricDefinition(
        name="building_ground_coverage_present",
        domain="building",
        py_type=bool,
        unit="flag",
        source="derived",
        required=True,
    ),
    "building_ground_coverage_limit_pct": MetricDefinition(
        name="building_ground_coverage_limit_pct",
        domain="building",
        py_type=float,
        unit="percent",
        source="gdcr_config",
        required=False,
    ),
    "building_number_of_floors": MetricDefinition(
        name="building_number_of_floors",
        domain="building",
        py_type=int,
        unit="count",
        source="building_contract",
        required=True,
    ),
    "building_number_of_basements": MetricDefinition(
        name="building_number_of_basements",
        domain="building",
        py_type=int,
        unit="count",
        source="building_contract",
        required=False,
    ),
    "building_has_stilt": MetricDefinition(
        name="building_has_stilt",
        domain="building",
        py_type=bool,
        unit="flag",
        source="building_contract",
        required=False,
    ),
    # Parking
    "parking_required_total": MetricDefinition(
        name="parking_required_total",
        domain="parking",
        py_type=int,
        unit="count",
        source="derived",
        required=False,
    ),
    "parking_provided_total": MetricDefinition(
        name="parking_provided_total",
        domain="parking",
        py_type=int,
        unit="count",
        source="building_contract",
        required=False,
    ),
    # Safety
    "safety_has_fire_stair": MetricDefinition(
        name="safety_has_fire_stair",
        domain="safety",
        py_type=bool,
        unit="flag",
        source="building_contract",
        required=False,
    ),
    "safety_lift_required": MetricDefinition(
        name="structure_lift_required",
        domain="safety",
        py_type=bool,
        unit="flag",
        source="gdcr_config",
        required=False,
    ),
}


class ComplianceContextValidationError(ValueError):
    pass


def validate_compliance_context(context: ComplianceContext) -> None:
    """
    Validate that all required metrics in the registry are present and of
    the expected Python type. Raises ComplianceContextValidationError on
    any mismatch; does not attempt recovery.
    """
    missing: list[str] = []
    wrong_type: list[str] = []

    for name, definition in METRIC_DEFINITIONS.items():
        value = getattr(context, name)
        if value is None:
            if definition.required:
                missing.append(name)
            continue
        if not isinstance(value, definition.py_type):
            wrong_type.append(name)

    if missing or wrong_type:
        parts: list[str] = []
        if missing:
            parts.append(f"missing={','.join(sorted(missing))}")
        if wrong_type:
            parts.append(f"wrong_type={','.join(sorted(wrong_type))}")
        raise ComplianceContextValidationError("; ".join(parts))

