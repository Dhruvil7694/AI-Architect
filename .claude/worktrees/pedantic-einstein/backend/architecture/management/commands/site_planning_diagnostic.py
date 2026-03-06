"""
architecture/management/commands/site_planning_diagnostic.py
------------------------------------------------------------
Deep diagnostic for the full site-planning pipeline against a real Plot
from the live PostGIS database.

This is a regulatory + geometric audit tool, not a unit test.

Usage:
    cd backend
    python manage.py site_planning_diagnostic --tp <TP> --fp <FP>

If --tp/--fp are omitted, the command selects the largest plot in the DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot
from architecture.services.development_pipeline import (
    generate_optimal_development_floor_plans,
)
from envelope_engine.services.envelope_service import compute_envelope
from placement_engine.services.placement_service import compute_placement

from compliance.gdcr_config import load_gdcr_config


SQFT_TO_SQM = 0.092903


@dataclass
class RegulatoryBaseline:
    base_fsi: float
    maximum_fsi: float
    chargeable_fsi: float
    max_gc_pct: Optional[float]
    allowed_height_m: Optional[float]
    road_side_margin_cfg: Dict[str, Any]
    side_rear_margin_cfg: Dict[str, Any]
    inter_building_margin_cfg: Dict[str, Any]
    zone: Optional[str]


def _parse_road_edges(raw: str) -> List[int]:
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [0]


def _select_plot(tp: Optional[int], fp: Optional[str]) -> Plot:
    qs = Plot.objects.all()

    if tp is not None:
        qs = qs.filter(tp_scheme=f"TP{tp}")
    if fp is not None:
        qs = qs.filter(fp_number=str(fp))

    if tp is None and fp is None:
        plot = qs.order_by("-area_geometry").first()
    else:
        plot = qs.first()

    if plot is None:
        if tp is not None or fp is not None:
            raise CommandError(
                f"No Plot found for filters tp={tp!r}, fp={fp!r}. "
                "Ensure the requested FP exists in the live DB."
            )
        raise CommandError(
            "No Plot instances available in the live DB. "
            "Ingest at least one FP (Plot) before running this command."
        )

    return plot


def _load_regulatory_baseline(road_width_m: float) -> RegulatoryBaseline:
    yaml_path: Path = settings.BASE_DIR.parent / "GDCR.yaml"
    gdcr = load_gdcr_config(yaml_path)

    # Load raw YAML for margins / spacing / zone.
    import yaml

    with yaml_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    road_side_margin_cfg = raw.get("road_side_margin", {})
    side_rear_margin_cfg = raw.get("side_rear_margin", {})
    inter_building_margin_cfg = raw.get("inter_building_margin", {})
    use_zone_cfg = raw.get("use_zone", {})

    zone = use_zone_cfg.get("zone")

    base_fsi = float(gdcr.fsi_rules.base_fsi)
    maximum_fsi = float(gdcr.fsi_rules.maximum_fsi)
    chargeable_fsi = float(gdcr.fsi_rules.chargeable_fsi)
    max_gc_pct = gdcr.parking_rules.max_ground_coverage_pct_dw3

    allowed_height_m: Optional[float] = None
    if road_width_m and road_width_m > 0:
        allowed_height_m = gdcr.height_rules.max_height_for_road_width(road_width_m)

    return RegulatoryBaseline(
        base_fsi=base_fsi,
        maximum_fsi=maximum_fsi,
        chargeable_fsi=chargeable_fsi,
        max_gc_pct=max_gc_pct,
        allowed_height_m=allowed_height_m,
        road_side_margin_cfg=road_side_margin_cfg,
        side_rear_margin_cfg=side_rear_margin_cfg,
        inter_building_margin_cfg=inter_building_margin_cfg,
        zone=zone,
    )


def _print_section(title: str, write) -> None:
    write("")
    write(f"===== {title} =====")


def _compute_bbox(plot: Plot) -> Tuple[float, float, float, float, float, float]:
    ext = plot.geom.extent
    minx, miny, maxx, maxy = ext
    bbox_width = maxx - minx
    bbox_depth = maxy - miny
    return float(minx), float(miny), float(maxx), float(maxy), float(bbox_width), float(bbox_depth)


class Command(BaseCommand):
    help = (
        "Deep diagnostic for the end-to-end site planning pipeline "
        "(Plot → Margins → Envelope → Placement → FSI → GC → Height → Spacing) "
        "against a real Plot from the live DB."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tp", type=int, default=None, help="TP scheme number (e.g. 14)")
        parser.add_argument("--fp", type=str, default=None, help="FP number within the TP (e.g. 126)")

    def handle(self, *args, **options):
        tp = options.get("tp")
        fp = options.get("fp")

        # ── STEP 1 — Fetch real plot ───────────────────────────────────────────
        plot = _select_plot(tp, fp)

        self.stdout.write("Running site planning diagnostic.")
        self.stdout.write(f"Selected Plot: id={plot.id}, tp_scheme={plot.tp_scheme}, fp_number={plot.fp_number}")

        plot_area_sqm = float(plot.plot_area_sqm)
        road_width_m = float(getattr(plot, "road_width_m", 0.0) or 0.0)
        road_edges = _parse_road_edges(getattr(plot, "road_edges", "0"))

        # ── STEP 2 — Extract raw plot metrics ─────────────────────────────────
        minx, miny, maxx, maxy, bbox_width, bbox_depth = _compute_bbox(plot)

        _print_section("PLOT BASELINE", self.stdout.write)
        self.stdout.write(f"Plot ID           : {plot.id}")
        self.stdout.write(f"TP / FP           : {plot.tp_scheme} / {plot.fp_number}")
        self.stdout.write(f"Plot Area (sqm)   : {plot_area_sqm:.3f}")
        self.stdout.write(f"Road Width (m)    : {road_width_m:.3f}")
        self.stdout.write(f"Road Edges        : {road_edges}")
        self.stdout.write(f"Geom Bounds       : minx={minx:.3f}, miny={miny:.3f}, maxx={maxx:.3f}, maxy={maxy:.3f}")
        self.stdout.write(f"BBox Width (DXF)  : {bbox_width:.3f}")
        self.stdout.write(f"BBox Depth (DXF)  : {bbox_depth:.3f}")

        # ── STEP 3 — Regulatory baseline (GDCR.yaml) ──────────────────────────
        reg = _load_regulatory_baseline(road_width_m)

        _print_section("REGULATORY BASELINE", self.stdout.write)
        self.stdout.write(f"Zone                      : {reg.zone or 'N/A'}")
        self.stdout.write(f"Base FSI                  : {reg.base_fsi}")
        self.stdout.write(f"Chargeable FSI            : {reg.chargeable_fsi}")
        self.stdout.write(f"Maximum FSI               : {reg.maximum_fsi}")
        self.stdout.write(
            f"Max Ground Coverage DW3   : {reg.max_gc_pct if reg.max_gc_pct is not None else 'N/A'} %"
        )
        self.stdout.write(
            f"Height Limit (from road)  : "
            f"{reg.allowed_height_m:.3f} m" if reg.allowed_height_m is not None else "Height Limit (from road)  : N/A"
        )

        road_side = reg.road_side_margin_cfg
        side_rear = reg.side_rear_margin_cfg
        inter_bldg = reg.inter_building_margin_cfg

        self.stdout.write("")
        self.stdout.write("Road-side margin rules (front):")
        self.stdout.write(f"  Reference           : {road_side.get('reference')}")
        self.stdout.write(f"  Logic               : {road_side.get('logic')}")
        self.stdout.write(f"  Height formula      : {road_side.get('height_formula')}")
        self.stdout.write("  Road-width margins  :")
        for row in road_side.get("road_width_margin_map", []):
            self.stdout.write(
                f"    - road_max={row.get('road_max')} m -> margin={row.get('margin')} m"
            )

        self.stdout.write("")
        self.stdout.write("Side / rear margin rules:")
        self.stdout.write(f"  Reference           : {side_rear.get('reference')}")
        self.stdout.write("  Height-band margins :")
        for row in side_rear.get("height_margin_map", []):
            self.stdout.write(
                f"    - height_max={row.get('height_max')} m -> "
                f"rear={row.get('rear')} m, side={row.get('side')} m"
            )

        self.stdout.write("")
        self.stdout.write("Inter-building spacing rules:")
        self.stdout.write(f"  Reference           : {inter_bldg.get('reference')}")
        self.stdout.write(f"  Formula             : {inter_bldg.get('formula')}")
        self.stdout.write(f"  Minimum spacing (m) : {inter_bldg.get('minimum_spacing_m')}")
        self.stdout.write(f"  Applies to          : {inter_bldg.get('applies_to')}")

        # ── STEP 4 — Theoretical maxima ───────────────────────────────────────
        _print_section("THEORETICAL MAXIMA", self.stdout.write)
        allowed_bua_sqm = reg.maximum_fsi * plot_area_sqm
        self.stdout.write(f"Allowed BUA (sqm)   : {allowed_bua_sqm:.3f}")

        max_gc_area_sqm = None
        if reg.max_gc_pct is not None:
            max_gc_area_sqm = plot_area_sqm * (reg.max_gc_pct / 100.0)
            self.stdout.write(
                f"Max GC Area (sqm)   : {max_gc_area_sqm:.3f} "
                f"({reg.max_gc_pct:.2f}% of plot)"
            )
        else:
            self.stdout.write("Max GC Area (sqm)   : N/A (no GC cap configured)")

        if reg.allowed_height_m is not None:
            self.stdout.write(f"Allowed Height (m)  : {reg.allowed_height_m:.3f}")
        else:
            self.stdout.write("Allowed Height (m)  : N/A (road width missing)")

        # ── Run development pipeline once for configuration / FSI reference ───
        dev_result = generate_optimal_development_floor_plans(
            plot=plot,
            include_building_layout=False,
            strict=True,
        )

        dev_ok = dev_result.status == "OK"

        if not dev_ok:
            _print_section("DEVELOPMENT PIPELINE STATUS", self.stdout.write)
            self.stdout.write(f"Status          : {dev_result.status}")
            self.stdout.write(f"Failure reason  : {dev_result.failure_reason}")
            self.stdout.write(f"Failure details : {dev_result.failure_details}")

        floors = int(dev_result.floors) if dev_ok else 0
        design_height_m = float(dev_result.height_m) if dev_ok else (reg.allowed_height_m or 0.0)

        # Selected COP metadata from the development pipeline (if available).
        selected_cop_strategy: str = getattr(dev_result, "cop_strategy", None) or "edge"
        selected_cop_area_sqft: float = float(
            getattr(dev_result, "cop_area_sqft", 0.0) or 0.0
        )
        selected_cop_area_sqm: float = selected_cop_area_sqft * SQFT_TO_SQM
        selected_cop_margin_m = getattr(dev_result, "cop_margin_m", None)

        # ── STEP 5 — Envelope computation breakdown ────────────────────────────
        _print_section("ENVELOPE", self.stdout.write)

        if road_width_m <= 0.0:
            raise CommandError(
                "Plot.road_width_m is not set or non-positive. Envelope cannot be computed."
            )

        env = compute_envelope(
            plot_wkt=plot.geom.wkt,
            building_height=design_height_m,
            road_width=road_width_m,
            road_facing_edges=road_edges,
            enforce_gc=True,
            cop_strategy=selected_cop_strategy,
        )

        if env.envelope_area_sqft is not None:
            envelope_area_sqm = env.envelope_area_sqft * SQFT_TO_SQM
        elif env.envelope_polygon is not None:
            envelope_area_sqm = env.envelope_polygon.area * SQFT_TO_SQM
        else:
            envelope_area_sqm = 0.0

        envelope_valid = env.status == "VALID" and env.envelope_polygon is not None

        self.stdout.write(f"Envelope Status      : {env.status}")
        self.stdout.write(f"Envelope Area (sqm)  : {envelope_area_sqm:.3f}")

        if env.envelope_area_sqft is not None and plot.plot_area_sqft:
            lost_pct = (1.0 - (env.envelope_area_sqft / float(plot.plot_area_sqft))) * 100.0
            self.stdout.write(f"Plot Lost to Margins : {lost_pct:.2f}%")
        else:
            self.stdout.write("Plot Lost to Margins : N/A")

        # COP diagnostics: strategy, area, and applied margin.
        effective_cop_area_sqft = float(
            getattr(env, "common_plot_area_sqft", None) or selected_cop_area_sqft
        )
        effective_cop_area_sqm = effective_cop_area_sqft * SQFT_TO_SQM
        cop_margin_m = getattr(env, "cop_margin_m", None)
        if cop_margin_m is None:
            cop_margin_m = selected_cop_margin_m

        self.stdout.write(f"COP Strategy         : {getattr(env, 'cop_strategy', selected_cop_strategy)}")
        self.stdout.write(f"COP Area (sqm)       : {effective_cop_area_sqm:.3f}")
        if cop_margin_m is not None:
            self.stdout.write(f"COP Margin Applied   : {cop_margin_m:.3f} m")
        else:
            self.stdout.write("COP Margin Applied   : N/A")

        self.stdout.write(f"GC Status            : {env.gc_status}")
        self.stdout.write(f"GC % (envelope)      : {env.ground_coverage_pct if env.ground_coverage_pct is not None else 'N/A'}")

        if env.status != "VALID":
            self.stdout.write(f"Collapse / Error     : {env.error_message}")

        # Compute frontage from edge_margin_audit (sum of ROAD edges).
        frontage_dxf = 0.0
        for e in env.edge_margin_audit or []:
            if e.get("edge_type") == "ROAD":
                frontage_dxf += float(e.get("length_dxf", 0.0))
        if frontage_dxf > 0.0:
            try:
                from common.units import dxf_to_metres

                frontage_m = dxf_to_metres(frontage_dxf)
                self.stdout.write(f"Plot Frontage (m)    : {frontage_m:.3f}")
            except Exception:
                self.stdout.write(f"Plot Frontage (DXF)  : {frontage_dxf:.3f}")
        else:
            self.stdout.write("Plot Frontage        : N/A (no ROAD edges detected)")

        self.stdout.write("Per-edge margin audit:")
        for e in env.edge_margin_audit or []:
            self.stdout.write(
                f"  Edge {e.get('index')}: type={e.get('edge_type')}, "
                f"length_dxf={e.get('length_dxf')}, "
                f"required_margin_m={e.get('required_margin_m')}"
            )

        # If envelope collapsed, no further geometric analysis makes sense.
        if not envelope_valid:
            self.stdout.write("")
            self.stdout.write(
                "Envelope is not VALID; stopping placement / FSI analysis. "
                "Review margin audit and collapse reason above."
            )

            _print_section("FINAL DIAGNOSIS", self.stdout.write)
            if env.status in ("COLLAPSED", "TOO_SMALL"):
                self.stdout.write("PRIMARY BOTTLENECK: MARGIN COLLAPSED")
                self.stdout.write("Classification     : MARGIN COLLAPSED")
            else:
                self.stdout.write("PRIMARY BOTTLENECK: GEOMETRIC / ENVELOPE ERROR")
                self.stdout.write("Classification     : GEOMETRICALLY INFEASIBLE")
            return

        # ── STEP 6 — Tower placement audit ─────────────────────────────────────
        _print_section("PLACEMENT", self.stdout.write)

        if dev_ok:
            n_towers_requested = int(dev_result.n_towers)
        else:
            n_towers_requested = 1

        placement = compute_placement(
            envelope_wkt=env.envelope_polygon.wkt,
            building_height_m=design_height_m,
            n_towers=n_towers_requested,
        )

        self.stdout.write(f"Placement Status     : {placement.status}")
        self.stdout.write(f"Towers Requested     : {placement.n_towers_requested}")
        self.stdout.write(f"Towers Placed        : {placement.n_towers_placed}")
        self.stdout.write(f"Spacing Required (m) : {placement.spacing_required_m:.3f}")

        per_tower_footprint_sqm: List[float] = []
        for idx, fp in enumerate(placement.footprints or []):
            area_sqm = fp.area_sqft * SQFT_TO_SQM
            per_tower_footprint_sqm.append(area_sqm)
            self.stdout.write(f"  Tower {idx}: footprint={area_sqm:.3f} sqm")

        total_footprint_sqm = sum(per_tower_footprint_sqm)
        self.stdout.write(f"Total Footprint (sqm): {total_footprint_sqm:.3f}")

        spacing_provided_m: Optional[float] = None
        spacing_status = "N/A"
        if placement.placement_audit:
            gaps = [float(e.get("gap_m", 0.0)) for e in placement.placement_audit if "gap_m" in e]
            if gaps:
                spacing_provided_m = min(gaps)
                spacing_status = "PASS" if all(
                    e.get("status") == "PASS" for e in placement.placement_audit
                ) else "FAIL"

        self.stdout.write(
            f"Spacing Provided (m) : {spacing_provided_m:.3f}" if spacing_provided_m is not None
            else "Spacing Provided (m) : N/A (single tower or no audit)"
        )
        self.stdout.write(f"Spacing Audit Status : {spacing_status}")
        self.stdout.write(f"Packing Mode         : {placement.packing_mode}")

        actual_gc_ratio = (total_footprint_sqm / plot_area_sqm) if plot_area_sqm > 0 else 0.0
        self.stdout.write(
            f"GC Actual vs Allowed : "
            f"{actual_gc_ratio * 100:.2f}% of plot "
            f"vs {reg.max_gc_pct:.2f}% allowed"
            if reg.max_gc_pct is not None
            else f"GC Actual            : {actual_gc_ratio * 100:.2f}% of plot (no GC cap configured)"
        )

        # ── STEP 7 — FSI audit ─────────────────────────────────────────────────
        _print_section("FSI ANALYSIS", self.stdout.write)

        # Prefer optimiser's canonical BUA/FSI when available to avoid divergence
        # between optimisation loop and diagnostic re-computation.
        if dev_ok and dev_result.total_bua_sqft > 0:
            actual_bua_sqm = float(dev_result.total_bua_sqft) * SQFT_TO_SQM
            fsi_utilization = (
                float(dev_result.achieved_fsi) / reg.maximum_fsi
                if reg.maximum_fsi > 0
                else 0.0
            )
        else:
            actual_bua_sqm = total_footprint_sqm * float(floors if floors > 0 else 0)
            fsi_utilization = (actual_bua_sqm / allowed_bua_sqm) if allowed_bua_sqm > 0 else 0.0

        # Derive storey height from the optimiser output whenever possible.
        if dev_ok and floors > 0:
            storey_height_m = design_height_m / float(floors)
        else:
            storey_height_m = 3.0

        max_floors_by_fsi = int(allowed_bua_sqm / total_footprint_sqm) if total_footprint_sqm > 0 else 0
        max_floors_by_height = (
            int((reg.allowed_height_m or 0.0) / storey_height_m) if storey_height_m > 0 else 0
        )

        self.stdout.write(f"Floors (from pipeline) : {floors if dev_ok else 'N/A'}")
        self.stdout.write(f"Design Height (m)      : {design_height_m:.3f}")
        self.stdout.write(
            f"Allowed Height (m)     : {reg.allowed_height_m:.3f}"
            if reg.allowed_height_m is not None
            else "Allowed Height (m)     : N/A"
        )
        self.stdout.write(f"BUA Actual (sqm)       : {actual_bua_sqm:.3f}")
        self.stdout.write(f"BUA Allowed (sqm)      : {allowed_bua_sqm:.3f}")
        self.stdout.write(f"FSI Utilization        : {fsi_utilization * 100:.2f}%")
        self.stdout.write(f"Max Floors (by FSI)    : {max_floors_by_fsi}")
        self.stdout.write(f"Max Floors (by Height) : {max_floors_by_height}")

        # ── STEP 8 — Regulatory constraint summary ─────────────────────────────
        _print_section("CONSTRAINT SUMMARY", self.stdout.write)

        def _pass_fail(ok: bool) -> str:
            return "PASS" if ok else "FAIL"

        # Envelope
        env_ok = envelope_valid
        self.stdout.write("REGULATORY CHECK SUMMARY")
        self.stdout.write("------------------------")
        self.stdout.write(
            f"Envelope Valid         : {_pass_fail(env_ok)} "
            f"(status={env.status})"
        )

        # FSI
        fsi_ok = actual_bua_sqm <= allowed_bua_sqm + 1e-6
        self.stdout.write(
            f"FSI Limit              : {_pass_fail(fsi_ok)} "
            f"(actual={actual_bua_sqm:.2f} sqm, allowed={allowed_bua_sqm:.2f} sqm)"
        )

        # GC
        if reg.max_gc_pct is not None:
            gc_ok = actual_gc_ratio <= (reg.max_gc_pct / 100.0) + 1e-6
            self.stdout.write(
                f"Ground Coverage        : {_pass_fail(gc_ok)} "
                f"(actual={actual_gc_ratio * 100:.2f}%, allowed={reg.max_gc_pct:.2f}%)"
            )
        else:
            gc_ok = True
            self.stdout.write("Ground Coverage        : N/A (no GC cap configured)")

        # Height
        if reg.allowed_height_m is not None:
            height_ok = design_height_m <= reg.allowed_height_m + 1e-6
            self.stdout.write(
                f"Height Limit           : {_pass_fail(height_ok)} "
                f"(actual={design_height_m:.2f} m, allowed={reg.allowed_height_m:.2f} m)"
            )
        else:
            height_ok = True
            self.stdout.write("Height Limit           : N/A (no height rule computed)")

        # Spacing
        if spacing_provided_m is not None:
            spacing_ok = spacing_status == "PASS"
            self.stdout.write(
                f"Inter-building Spacing : {_pass_fail(spacing_ok)} "
                f"(actual_min_gap={spacing_provided_m:.2f} m, "
                f"required={placement.spacing_required_m:.2f} m)"
            )
        else:
            spacing_ok = True
            self.stdout.write("Inter-building Spacing : N/A (single tower or no spacing audit)")

        # ── STEP 9 — Architectural diagnostic insights ─────────────────────────
        _print_section("ARCHITECTURAL INSIGHTS", self.stdout.write)

        # Heuristic insights about bottlenecks (purely diagnostic; no solver changes).
        if reg.max_gc_pct is not None:
            gc_headroom_pct = (reg.max_gc_pct / 100.0) - actual_gc_ratio
        else:
            gc_headroom_pct = 0.0

        self.stdout.write(
            f"Envelope width vs depth suggests a limiting dimension of "
            f"{min(bbox_width, bbox_depth):.3f} DXF units."
        )

        if gc_headroom_pct > 0.05:
            self.stdout.write(
                "GC cap does NOT appear to be the primary bottleneck "
                f"(headroom ~{gc_headroom_pct * 100:.1f} percentage points)."
            )
        else:
            self.stdout.write(
                "GC cap appears close to binding; footprint may be GC-limited."
            )

        if reg.allowed_height_m is not None and design_height_m >= reg.allowed_height_m - 1e-3:
            self.stdout.write(
                "Design height is at or near the road-width-based height cap; "
                "height is likely limiting further FSI utilization."
            )
        else:
            self.stdout.write(
                "Design height is below the theoretical height cap; "
                "other factors (GC, spacing, geometry) may be limiting."
            )

        if spacing_provided_m is not None:
            spacing_margin = spacing_provided_m - placement.spacing_required_m
            if spacing_margin < 0.1:
                self.stdout.write(
                    "Inter-building spacing is at or near the H/3 requirement; "
                    "spacing is likely constraining additional towers."
                )
            else:
                self.stdout.write(
                    f"Inter-building spacing has ~{spacing_margin:.2f} m headroom; "
                    "spacing is unlikely to be the primary bottleneck."
                )
        else:
            self.stdout.write(
                "Inter-building spacing not binding (single tower or no spacing pairs)."
            )

        # ── STEP 10 — Final status classification ──────────────────────────────
        _print_section("FINAL DIAGNOSIS", self.stdout.write)

        classification = "GEOMETRICALLY INFEASIBLE"

        if fsi_utilization >= 0.95 and env_ok and fsi_ok and gc_ok and height_ok and spacing_ok:
            classification = "FULLY UTILIZABLE (FSI > 0.95)"
        elif not env_ok:
            classification = "MARGIN COLLAPSED"
        elif reg.allowed_height_m is not None and not height_ok:
            classification = "HEIGHT LIMITED"
        elif reg.max_gc_pct is not None and not gc_ok:
            classification = "GC LIMITED"
        elif spacing_provided_m is not None and not spacing_ok:
            classification = "SPACING LIMITED"

        if classification.startswith("FULLY UTILIZABLE"):
            primary_bottleneck = "NONE (near full FSI utilization)"
        elif classification == "HEIGHT LIMITED":
            primary_bottleneck = "HEIGHT LIMIT"
        elif classification == "GC LIMITED":
            primary_bottleneck = "GROUND COVERAGE LIMIT"
        elif classification == "MARGIN COLLAPSED":
            primary_bottleneck = "MARGINS / ENVELOPE"
        elif classification == "SPACING LIMITED":
            primary_bottleneck = "INTER-BUILDING SPACING"
        else:
            primary_bottleneck = "GEOMETRICALLY INFEASIBLE / OTHER"

        self.stdout.write(f"PRIMARY BOTTLENECK: {primary_bottleneck}")
        self.stdout.write(f"Classification    : {classification}")

