"""
architecture.feasibility.service
---------------------------------

Orchestrates building a FeasibilityAggregate from pipeline outputs.
Does not run envelope, placement, or rules; consumes their results only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import logging

from rules_engine.rules.base import RuleResult

from architecture.feasibility.aggregate import (
    AuditMetadata,
    FeasibilityAggregate,
)
from architecture.feasibility.plot_metrics import (
    PlotMetrics,
    compute_plot_metrics,
)
from architecture.feasibility.buildability_metrics import (
    BuildabilityMetrics,
    build_buildability_metrics,
)
from architecture.feasibility.regulatory_metrics import (
    RegulatoryMetrics,
    build_regulatory_metrics,
)
from architecture.feasibility.compliance_summary import (
    ComplianceSummary,
    build_compliance_summary_from_rule_results,
)
from architecture.feasibility.constants import DEFAULT_STOREY_HEIGHT_M
from common.units import dxf_plane_area_to_sqm, sqm_to_sqft


logger = logging.getLogger(__name__)


def build_feasibility_from_pipeline(
    *,
    plot_geom_wkt: str,
    plot_area_sqft: float,
    plot_area_sqm: float,
    envelope_result,
    placement_result,
    building_height_m: float,
    road_width_m: float,
    tp_scheme: str,
    fp_number: str,
    skeleton=None,
    rule_results: Optional[list[RuleResult]] = None,
    storey_height_m: Optional[float] = None,
) -> FeasibilityAggregate:
    """
    Build a FeasibilityAggregate from existing pipeline artefacts.

    Parameters
    ----------
    plot_geom_wkt, plot_area_sqft, plot_area_sqm : from Plot
    envelope_result : EnvelopeResult (must have status VALID and edge_margin_audit)
    placement_result : PlacementResult (footprints, per_tower_core_validation, spacing_required_m)
    building_height_m, road_width_m : proposal/run parameters
    tp_scheme, fp_number : for audit
    skeleton : FloorSkeleton or None; if provided, area_summary used for efficiency/core/circulation
    rule_results : list of RuleResult or None; if provided, compliance_summary is filled
    storey_height_m : storey height (m) used to estimate num_floors when no BuildingProposal.
                      BUA estimate = footprint_sqft * max(1, int(building_height_m / storey_height_m)).
                      Default DEFAULT_STOREY_HEIGHT_M (3.0). Set to client value (e.g. 3.1, 3.3) or
                      use BuildingProposal.total_bua for authority figures.

    Returns
    -------
    FeasibilityAggregate
    """
    # Plot metrics (uses envelope edge_margin_audit)
    plot_metrics = compute_plot_metrics(
        plot_geom_wkt=plot_geom_wkt,
        plot_area_sqft=plot_area_sqft,
        plot_area_sqm=plot_area_sqm,
        edge_margin_audit=envelope_result.edge_margin_audit,
        building_height_m=building_height_m,
    )

    # Buildability: envelope + first footprint + first core validation + skeleton
    env_sqft = envelope_result.envelope_area_sqft or 0.0
    fp = placement_result.footprints[0] if placement_result.footprints else None
    cv = placement_result.per_tower_core_validation[0] if placement_result.per_tower_core_validation else None

    if fp is None or cv is None:
        buildability = build_buildability_metrics(
            envelope_area_sqft=env_sqft,
            footprint_width_m=0.0,
            footprint_depth_m=0.0,
            footprint_area_sqft=0.0,
            core_area_sqm=0.0,
            remaining_usable_sqm=0.0,
        )
    else:
        eff = core_r = circ = None
        if skeleton is not None and getattr(skeleton, "area_summary", None):
            eff = skeleton.area_summary.get("efficiency_ratio")
            core_r = skeleton.area_summary.get("core_ratio")
            circ = skeleton.area_summary.get("circulation_ratio")

        fp_area_intl_sqft = sqm_to_sqft(
            dxf_plane_area_to_sqm(float(fp.area_sqft or 0.0))
        )
        buildability = build_buildability_metrics(
            envelope_area_sqft=env_sqft,
            footprint_width_m=fp.width_m,
            footprint_depth_m=fp.depth_m,
            footprint_area_sqft=fp_area_intl_sqft,
            core_area_sqm=cv.core_area_estimate_sqm,
            remaining_usable_sqm=cv.remaining_usable_sqm,
            efficiency_ratio=eff,
            core_ratio=core_r,
            circulation_ratio=circ,
        )

    # Regulatory: BUA estimate when no proposal (see constants.py and RISKS.md — storey height is configurable).
    storey_m = storey_height_m if storey_height_m is not None else DEFAULT_STOREY_HEIGHT_M
    if storey_height_m is None:
        logger.warning(
            "FeasibilityAggregate using DEFAULT_STOREY_HEIGHT_M=%.2f m; "
            "no preferred_storey_height_m provided by caller.",
            DEFAULT_STOREY_HEIGHT_M,
        )
    num_floors_est = max(1, int(building_height_m / storey_m)) if storey_m > 0 else 1
    footprint_sqft = buildability.footprint_area_sqft
    total_bua_sqft = footprint_sqft * num_floors_est

    # Achieved GC: use built footprint (slab) when available to match architect interpretation;
    # otherwise envelope-based. See RISKS.md — GC = built footprint / plot_area, not envelope.
    if plot_area_sqft > 0 and footprint_sqft > 0:
        achieved_gc_pct = 100.0 * footprint_sqft / plot_area_sqft
    else:
        achieved_gc_pct = envelope_result.ground_coverage_pct or 0.0
    cop_provided = sqm_to_sqft(
        dxf_plane_area_to_sqm(float(envelope_result.common_plot_area_sqft or 0.0))
    )

    spacing_provided_m = None
    if placement_result.placement_audit:
        gaps_m = []
        for entry in placement_result.placement_audit:
            g = entry.get("gap_dxf")
            if g is not None:
                from common.units import dxf_to_metres
                gaps_m.append(dxf_to_metres(g))
        spacing_provided_m = min(gaps_m) if gaps_m else None

    regulatory = build_regulatory_metrics(
        plot_area_sqft=plot_area_sqft,
        total_bua_sqft=total_bua_sqft,
        achieved_gc_pct=achieved_gc_pct,
        cop_provided_sqft=cop_provided,
        spacing_required_m=placement_result.spacing_required_m,
        spacing_provided_m=spacing_provided_m,
    )

    compliance_summary = None
    if rule_results:
        compliance_summary = build_compliance_summary_from_rule_results(rule_results)

    audit = AuditMetadata(
        tp_scheme=tp_scheme,
        fp_number=fp_number,
        building_height_m=building_height_m,
        road_width_m=road_width_m,
        proposal_id=None,
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    return FeasibilityAggregate(
        plot_metrics=plot_metrics,
        regulatory_metrics=regulatory,
        buildability_metrics=buildability,
        compliance_summary=compliance_summary,
        audit_metadata=audit,
        storey_height_used_m=storey_m,
        num_floors_estimated=num_floors_est,
    )
