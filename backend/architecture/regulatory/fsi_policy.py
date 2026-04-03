from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Any, Dict, List

from common.units import sqft_to_sqm, sqm_to_sqft, dxf_to_metres
from rules_engine.rules.loader import get_gdcr_config
from tp_ingestion.models import Plot
from django.contrib.gis.geos import LineString


@dataclass
class CorridorEligibility:
    eligible: bool
    distance_m: Optional[float]
    reason: str


@dataclass
class FsiPolicyDecision:
    authority: str
    zone: str
    base_fsi: float
    max_fsi: float
    corridor_eligible: bool
    corridor_distance_m: Optional[float]
    legal_gating_applied: bool
    notes: List[str]


def infer_zone_from_plot(plot: Optional[Plot], zone_override: Optional[str] = None) -> str:
    if zone_override:
        return zone_override.strip().upper()
    if plot is None:
        return "R1"
    d = (getattr(plot, "designation", "") or "").strip().upper()
    m = re.search(r"\b([RCI]\d)\b", d)
    if m:
        return m.group(1)
    if "R1" in d:
        return "R1"
    if "R2" in d:
        return "R2"
    if "R3" in d:
        return "R3"
    if "C1" in d:
        return "C1"
    if "C2" in d:
        return "C2"
    if "COMMERCIAL" in d:
        return "C2"
    if "RESIDENTIAL" in d or "DW3" in d:
        return "R1"
    return "R1"


def infer_authority(authority_override: Optional[str] = None) -> str:
    if authority_override:
        return authority_override.strip().upper()
    gdcr = get_gdcr_config() or {}
    meta = gdcr.get("meta", {}) or {}
    return str(meta.get("authority_name", "SUDA")).strip().upper()


def _eligible_width_values(eligible_if: Dict[str, Any]) -> List[float]:
    vals = eligible_if.get("eligible_road_widths_m") or []
    if vals:
        out = []
        for v in vals:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
        if out:
            return out
    return [float(eligible_if.get("road_width_min_m", 36.0))]


def _parse_road_edges_str(raw: str) -> List[int]:
    out: List[int] = []
    if not raw:
        return out
    for p in str(raw).split(","):
        s = p.strip()
        if not s:
            continue
        try:
            idx = int(s)
        except ValueError:
            continue
        if idx >= 0:
            out.append(idx)
    return sorted(set(out))


def _iter_plot_edge_segments(plot_geom) -> List[LineString]:
    if plot_geom is None:
        return []
    try:
        coords = list(plot_geom.coords[0])
    except Exception:
        return []
    segments: List[LineString] = []
    for i in range(len(coords) - 1):
        try:
            segments.append(LineString(coords[i], coords[i + 1]))
        except Exception:
            continue
    return segments


def estimate_distance_to_eligible_wide_road_m(
    plot: Plot,
    *,
    eligible_widths: List[float],
) -> Optional[float]:
    """
    Geometric proxy: distance to nearest plot that has eligible road width.
    Distances are computed in DXF feet and converted to metres.
    """
    if plot is None or plot.geom is None:
        return None
    qs = (
        Plot.objects.filter(tp_scheme=plot.tp_scheme)
        .exclude(id=plot.id)
        .exclude(road_width_m__isnull=True)
    )
    candidate_geoms = []
    for p in qs:
        try:
            rw = float(p.road_width_m or 0.0)
        except (TypeError, ValueError):
            continue
        if any(abs(rw - ew) <= 1e-6 or rw >= ew for ew in eligible_widths):
            if p.geom is None:
                continue
            # Prefer explicit road-edge segments when available.
            road_edges = _parse_road_edges_str(getattr(p, "road_edges", "") or "")
            segments = _iter_plot_edge_segments(p.geom)
            if road_edges and segments:
                has_valid = False
                for idx in road_edges:
                    if 0 <= idx < len(segments):
                        candidate_geoms.append(segments[idx])
                        has_valid = True
                if has_valid:
                    continue
            # Fallback: use whole plot geometry when road edges missing.
            candidate_geoms.append(p.geom)
    if not candidate_geoms:
        return None
    min_dxf = None
    for g in candidate_geoms:
        d = float(plot.geom.distance(g))
        if min_dxf is None or d < min_dxf:
            min_dxf = d
    return dxf_to_metres(min_dxf) if min_dxf is not None else None


def resolve_corridor_eligibility(
    *,
    plot: Optional[Plot],
    road_width_m: float,
    distance_to_wide_road_m: Optional[float] = None,
) -> CorridorEligibility:
    gdcr = get_gdcr_config() or {}
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}
    eligible_if = (fsi_cfg.get("corridor_rule") or {}).get("eligible_if") or {}
    road_width_min_m = float(eligible_if.get("road_width_min_m", 36.0))
    require_distance_check = bool(eligible_if.get("require_distance_check", False))
    buffer_distance_m = float(eligible_if.get("buffer_distance_m", 200.0))
    eligible_widths = _eligible_width_values(eligible_if)

    by_width = float(road_width_m) >= road_width_min_m or any(
        abs(float(road_width_m) - ew) <= 1e-6 for ew in eligible_widths
    )
    if not by_width:
        return CorridorEligibility(False, distance_to_wide_road_m, "road_width_not_eligible")

    dist = distance_to_wide_road_m
    if dist is None and by_width:
        # Plot directly fronts an eligible wide road: distance to corridor is 0.
        dist = 0.0
    if dist is None and plot is not None:
        dist = estimate_distance_to_eligible_wide_road_m(plot, eligible_widths=eligible_widths)

    if require_distance_check:
        if dist is None:
            return CorridorEligibility(False, None, "distance_missing_for_strict_corridor")
        return CorridorEligibility(dist <= buffer_distance_m, dist, f"distance_check_{buffer_distance_m}m")

    return CorridorEligibility(True, dist, "road_width_eligible_non_strict")


def _resolve_legal_caps(
    *,
    authority: str,
    zone: str,
    base_fsi_default: float,
    highest_tier_cap: float,
) -> tuple[float, float, bool]:
    gdcr = get_gdcr_config() or {}
    gating = (gdcr.get("fsi_rules", {}) or {}).get("legal_gating", {}) or {}
    rows = gating.get("authority_zone_tier_caps") or []

    def _read_caps(r: Dict[str, Any]) -> Optional[tuple[float, float, bool]]:
        try:
            return float(r.get("base_cap", base_fsi_default)), float(r.get("corridor_cap", highest_tier_cap)), True
        except (TypeError, ValueError):
            return None

    normalized = []
    for r in rows:
        a = str(r.get("authority", "")).strip().upper() or "*"
        z = str(r.get("zone", "")).strip().upper() or "*"
        normalized.append((a, z, r))

    precedence = [
        (authority, zone),
        (authority, "*"),
        ("*", zone),
        ("*", "*"),
    ]
    for pa, pz in precedence:
        for a, z, r in normalized:
            if a == pa and z == pz:
                caps = _read_caps(r)
                if caps is not None:
                    return caps
    return base_fsi_default, highest_tier_cap, False


def resolve_fsi_policy(
    *,
    plot: Optional[Plot],
    road_width_m: float,
    authority_override: Optional[str] = None,
    zone_override: Optional[str] = None,
    distance_to_wide_road_m: Optional[float] = None,
) -> FsiPolicyDecision:
    gdcr = get_gdcr_config() or {}
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}

    authority = infer_authority(authority_override)
    zone = infer_zone_from_plot(plot, zone_override=zone_override)
    base = float(fsi_cfg.get("base_fsi", 1.8))
    tiers = fsi_cfg.get("premium_tiers") or []
    if tiers:
        highest = max(float(t.get("resulting_cap", 0.0)) for t in tiers)
        non_corridor_caps = [float(t.get("resulting_cap", 0.0)) for t in tiers if not bool(t.get("corridor_required", False))]
        base_cap_from_tiers = non_corridor_caps[0] if non_corridor_caps else base
    else:
        highest = float(fsi_cfg.get("maximum_fsi", 2.7))
        base_cap_from_tiers = highest

    legal_base_cap, legal_corridor_cap, legal_applied = _resolve_legal_caps(
        authority=authority,
        zone=zone,
        base_fsi_default=base_cap_from_tiers,
        highest_tier_cap=highest,
    )

    corridor = resolve_corridor_eligibility(
        plot=plot,
        road_width_m=road_width_m,
        distance_to_wide_road_m=distance_to_wide_road_m,
    )
    max_fsi = legal_corridor_cap if corridor.eligible else legal_base_cap

    notes: List[str] = [corridor.reason]
    if legal_applied:
        notes.append("authority_zone_legal_gating_applied")
    else:
        notes.append("authority_zone_legal_gating_defaulted")

    return FsiPolicyDecision(
        authority=authority,
        zone=zone,
        base_fsi=base,
        max_fsi=max_fsi,
        corridor_eligible=corridor.eligible,
        corridor_distance_m=corridor.distance_m,
        legal_gating_applied=legal_applied,
        notes=notes,
    )


def compute_exclusion_adjusted_bua_sqft(
    *,
    total_bua_sqft: float,
    floors: int,
    per_tower_core_area_sqm: Optional[List[float]] = None,
    has_parking_floor_exclusion: bool = True,
    building_height_m: float = 0.0,
    typical_floor_area_sqft: float = 0.0,
) -> float:
    gdcr = get_gdcr_config() or {}
    ex_cfg = ((gdcr.get("fsi_rules", {}) or {}).get("exclusion_accounting", {}) or {})
    if not bool(ex_cfg.get("enabled", True)):
        return total_bua_sqft

    excluded = 0.0
    if per_tower_core_area_sqm:
        excluded += sum(sqm_to_sqft(max(0.0, float(a))) for a in per_tower_core_area_sqm) * max(1, int(floors))

    parking_cfg = ex_cfg.get("parking_floor_exclusion", {}) or {}
    if has_parking_floor_exclusion and bool(parking_cfg.get("enabled", True)):
        max_parking_floors = int(parking_cfg.get("max_excluded_parking_floors", 1))
        excluded += max(0, max_parking_floors) * max(0.0, float(typical_floor_area_sqft))

    refuge_cfg = ex_cfg.get("refuge_area_exclusion", {}) or {}
    if bool(refuge_cfg.get("enabled", True)):
        trigger_h = float(refuge_cfg.get("trigger_height_m", 25.0))
        refuge_pct = float(refuge_cfg.get("excluded_pct_of_typical_floor", 4.0)) / 100.0
        if float(building_height_m) > trigger_h and typical_floor_area_sqft > 0:
            excluded += refuge_pct * float(typical_floor_area_sqft)

    counted = max(0.0, float(total_bua_sqft) - excluded)
    return counted


def compute_premium_breakdown(
    *,
    achieved_fsi: float,
    plot_area_sqm: float,
    base_fsi: float,
    max_fsi: float,
    corridor_eligible: bool,
    jantri_rate_per_sqm: Optional[float] = None,
) -> Dict[str, Any]:
    gdcr = get_gdcr_config() or {}
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}
    tiers = fsi_cfg.get("premium_tiers") or []

    effective_fsi = min(max_fsi, max(0.0, float(achieved_fsi)))
    additional_fsi_used = max(0.0, effective_fsi - float(base_fsi))

    remaining = additional_fsi_used
    blocks = []
    for t in tiers:
        try:
            cap = float(t.get("resulting_cap", 0.0))
            add = float(t.get("additional_fsi", 0.0))
            req_corr = bool(t.get("corridor_required", False))
            pct = float(t.get("jantri_rate_percent", 0.0))
        except (TypeError, ValueError):
            continue
        if req_corr and not corridor_eligible:
            continue
        # incremental block width relative to previous cap is not always explicit,
        # so we consume by available "additional_fsi" from YAML for determinism.
        used = min(max(0.0, add), remaining)
        remaining = max(0.0, remaining - used)
        area_sqm = used * plot_area_sqm
        amount = None
        if jantri_rate_per_sqm is not None:
            amount = area_sqm * float(jantri_rate_per_sqm) * (pct / 100.0)
        blocks.append(
            {
                "resulting_cap": cap,
                "corridor_required": req_corr,
                "jantri_rate_percent": pct,
                "fsi_used_in_tier": round(used, 4),
                "chargeable_area_sqm": round(area_sqm, 2),
                "premium_amount_inr": round(amount, 2) if amount is not None else None,
            }
        )
        if remaining <= 1e-9:
            break

    return {
        "base_fsi": round(base_fsi, 4),
        "achieved_fsi_considered": round(effective_fsi, 4),
        "additional_fsi_used": round(additional_fsi_used, 4),
        "corridor_eligible": corridor_eligible,
        "tiers": blocks,
        "unallocated_additional_fsi": round(remaining, 4),
    }
