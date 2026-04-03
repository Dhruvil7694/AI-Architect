"""
services/envelope_service.py
-----------------------------
Orchestrates the full envelope computation pipeline:

    Plot.geom
        → EdgeClassifier
        → MarginResolver
        → EnvelopeBuilder        (per-edge half-plane intersection)
        → CoverageEnforcer       (measure / clip GC)
        → CommonPlotCarver       (10% rear reservation)
        → PlotEnvelope (DB model, optional)

The core function `compute_envelope` is a pure Python function (no ORM
writes).  The caller decides whether to persist the result.

Shapely ↔ Django GIS conversion
---------------------------------
Plot.geom is a Django GEOSGeometry (PolygonField, SRID=0).
Shapely works with its own Polygon class.
Conversion:
    shapely_poly = shapely.wkt.loads(plot.geom.wkt)
    geos_poly    = GEOSGeometry(shapely_poly.wkt, srid=0)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from shapely.geometry import Polygon as ShapelyPolygon
from shapely import wkt as shapely_wkt

from common.units import metres_to_dxf
from rules_engine.rules.loader import get_gdcr_config

from envelope_engine.geometry import (
    EnvelopeCollapseError,
    EnvelopeError,
    EnvelopeTooSmallError,
    InvalidGeometryError,
    InsufficientInputError,
)
from envelope_engine.geometry.edge_classifier import classify_edges
from envelope_engine.geometry.margin_resolver import margin_audit_log, resolve_margins
from envelope_engine.geometry.envelope_builder import build_envelope
from envelope_engine.geometry.coverage_enforcer import enforce_ground_coverage
from envelope_engine.geometry.common_plot_carver import carve_common_plot

logger = logging.getLogger(__name__)


# ── Result dataclass (pure Python — no Django deps) ────────────────────────────

@dataclass
class EnvelopeResult:
    """
    Holds every artefact produced by the envelope pipeline.
    All geometry fields are Shapely Polygons.
    """

    status: str                             # VALID / COLLAPSED / TOO_SMALL / …

    # Geometry layers
    margin_polygon:      Optional[ShapelyPolygon] = None
    gc_polygon:          Optional[ShapelyPolygon] = None
    envelope_polygon:    Optional[ShapelyPolygon] = None
    common_plot_polygon: Optional[ShapelyPolygon] = None

    # Scalar metrics
    envelope_area_sqft:    Optional[float] = None
    ground_coverage_pct:   Optional[float] = None
    gc_status:             str = "NA"
    common_plot_area_sqft: Optional[float] = None
    common_plot_status:    str = "NA"

    # Common open plot (COP) metadata
    cop_strategy: Optional[str] = None
    cop_margin_m: Optional[float] = None

    # Full per-edge audit log (list of dicts)
    edge_margin_audit: list = field(default_factory=list)

    # Raw EdgeSpec objects (for spatial planner — avoids reconstructing from audit)
    edge_specs_raw: list = field(default_factory=list)

    # Input snapshot
    road_facing_edges:    list = field(default_factory=list)
    building_height_used: Optional[float] = None
    road_width_used:      Optional[float] = None

    # Error detail (when status != VALID)
    error_message: str = ""


# ── Core pipeline function ─────────────────────────────────────────────────────

def compute_envelope(
    plot_wkt: str,
    building_height: float,
    road_width: float,
    road_facing_edges: List[int],
    enforce_gc: bool = True,
    cop_strategy: str = "edge",
) -> EnvelopeResult:
    """
    Run the full envelope computation pipeline.

    Parameters
    ----------
    plot_wkt          : WKT string of the plot polygon (DXF feet, SRID=0)
    building_height   : proposed building height in metres
    road_width        : adjacent road width in metres
    road_facing_edges : 0-based indices of edges that face a road
    enforce_gc        : whether to clip to GDCR ground coverage limit

    Returns
    -------
    EnvelopeResult — always returns (never raises), with status set
    """
    result = EnvelopeResult(
        status="ERROR",
        road_facing_edges=road_facing_edges,
        building_height_used=building_height,
        road_width_used=road_width,
        cop_strategy=cop_strategy,
    )

    # ── Parse WKT ─────────────────────────────────────────────────────────────
    try:
        plot_polygon: ShapelyPolygon = shapely_wkt.loads(plot_wkt)
    except Exception as exc:
        result.error_message = f"Failed to parse plot WKT: {exc}"
        result.status = "INVALID_GEOM"
        return result

    try:
        # ── Step 1: Classify edges ─────────────────────────────────────────────
        edge_specs = classify_edges(plot_polygon, road_facing_edges, road_width)

        # ── Step 2: Resolve margins ────────────────────────────────────────────
        resolve_margins(edge_specs, building_height)
        result.edge_margin_audit = margin_audit_log(edge_specs)
        result.edge_specs_raw = edge_specs

        _log_margin_summary(edge_specs, building_height, road_width)

        # ── Step 3: Build envelope (per-edge half-plane intersection) ──────────
        margin_polygon = build_envelope(plot_polygon, edge_specs)
        result.margin_polygon = margin_polygon

        # ── Step 4: Enforce ground coverage ───────────────────────────────────
        gc_polygon, gc_pct, gc_status = enforce_ground_coverage(
            margin_polygon, plot_polygon, enforce=enforce_gc
        )
        result.gc_polygon          = gc_polygon
        result.ground_coverage_pct = gc_pct
        result.gc_status           = gc_status

        # ── Step 5: Carve common plot ──────────────────────────────────────────
        common_geom, common_area, common_status = carve_common_plot(
            plot_polygon, gc_polygon, edge_specs, cop_strategy=cop_strategy
        )
        result.common_plot_polygon    = common_geom
        result.common_plot_area_sqft  = common_area
        result.common_plot_status     = common_status

        # ── Finalise ───────────────────────────────────────────────────────────
        # COP must not be part of buildable envelope; subtract the buffered
        # COP exclusion zone (height-dependent margin) from the GC-limited
        # polygon. Margin bands are defined in GDCR.yaml common_open_plot.
        effective_envelope = gc_polygon
        if common_geom is not None and not common_geom.is_empty:
            try:
                gdcr = get_gdcr_config()
                cop_cfg = gdcr.get("common_open_plot", {}) or {}
                bands = cop_cfg.get("margin_height_bands") or []
                cop_margin_m = 0.0
                for band in bands:
                    try:
                        if building_height <= float(band.get("height_max_m", 0.0)):
                            cop_margin_m = float(band.get("margin_m", 0.0))
                            break
                    except (TypeError, ValueError):
                        continue

                result.cop_margin_m = cop_margin_m

                if cop_margin_m > 0.0:
                    cop_margin_dxf = metres_to_dxf(cop_margin_m)
                    cop_exclusion = common_geom.buffer(cop_margin_dxf)
                    # Clip exclusion to GC polygon to avoid over-subtraction.
                    cop_exclusion = cop_exclusion.intersection(gc_polygon)
                else:
                    cop_exclusion = common_geom

                if cop_exclusion is not None and not cop_exclusion.is_empty:
                    effective_envelope = gc_polygon.difference(cop_exclusion)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to apply COP margin to envelope: %s. "
                    "Using GC polygon as envelope.",
                    exc,
                )
                effective_envelope = gc_polygon

        result.envelope_polygon    = effective_envelope
        result.envelope_area_sqft  = round(effective_envelope.area, 2)
        result.status              = "VALID"

        logger.info(
            "Envelope VALID — area %.1f sq.ft, GC %.1f%%, common plot %.1f sq.ft (%s)",
            result.envelope_area_sqft,
            result.ground_coverage_pct,
            result.common_plot_area_sqft or 0.0,
            result.common_plot_status,
        )

    except InsufficientInputError as exc:
        result.status        = "INSUFFICIENT_INPUT"
        result.error_message = str(exc)
        logger.error("Envelope computation: %s", exc)

    except InvalidGeometryError as exc:
        result.status        = "INVALID_GEOM"
        result.error_message = str(exc)
        logger.error("Envelope computation: %s", exc)

    except EnvelopeCollapseError as exc:
        result.status        = "COLLAPSED"
        result.error_message = str(exc)
        logger.warning("Envelope computation: %s", exc)

    except EnvelopeTooSmallError as exc:
        result.status        = "TOO_SMALL"
        result.error_message = str(exc)
        logger.warning("Envelope computation: %s", exc)

    except Exception as exc:  # noqa: BLE001
        result.status        = "ERROR"
        result.error_message = f"Unexpected error: {exc}"
        logger.exception("Unexpected error in envelope computation: %s", exc)

    return result


# ── Persistence helper ─────────────────────────────────────────────────────────

def save_envelope(
    result: EnvelopeResult,
    proposal,                   # BuildingProposal Django model instance
) -> "envelope_engine.models.PlotEnvelope":  # noqa: F821
    """
    Convert an EnvelopeResult to a PlotEnvelope DB record and save it.

    Parameters
    ----------
    result   : output of compute_envelope()
    proposal : BuildingProposal instance

    Returns
    -------
    Saved PlotEnvelope instance
    """
    from django.contrib.gis.geos import GEOSGeometry

    from envelope_engine.models import PlotEnvelope

    def _to_geos(shapely_poly) -> Optional["GEOSGeometry"]:
        if shapely_poly is None or shapely_poly.is_empty:
            return None
        return GEOSGeometry(shapely_poly.wkt, srid=0)

    pe = PlotEnvelope(
        proposal              = proposal,
        status                = result.status,
        error_message         = result.error_message,
        margin_geom           = _to_geos(result.margin_polygon),
        gc_geom               = _to_geos(result.gc_polygon),
        envelope_geom         = _to_geos(result.envelope_polygon),
        common_plot_geom      = _to_geos(result.common_plot_polygon),
        envelope_area_sqft    = result.envelope_area_sqft,
        ground_coverage_pct   = result.ground_coverage_pct,
        gc_status             = result.gc_status or "NA",
        common_plot_area_sqft = result.common_plot_area_sqft,
        common_plot_status    = result.common_plot_status or "NA",
        edge_margin_audit     = result.edge_margin_audit,
        road_facing_edges     = result.road_facing_edges,
        building_height_used  = result.building_height_used,
        road_width_used       = result.road_width_used,
    )
    pe.save()
    return pe


# ── Internal helpers ───────────────────────────────────────────────────────────

def _log_margin_summary(edge_specs, building_height, road_width):
    logger.info(
        "Margins resolved — H=%.1f m, road=%.1f m | Edges: %s",
        building_height,
        road_width,
        ", ".join(
            f"[{s.index}]{s.edge_type} {s.required_margin_m:.1f}m"
            for s in edge_specs
        ),
    )
