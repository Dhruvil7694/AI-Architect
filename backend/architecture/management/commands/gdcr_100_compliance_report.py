from __future__ import annotations

import csv
import os
from typing import List

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot
from architecture.regulatory.development_optimizer import evaluate_development_configuration
from architecture.regulatory.fsi_policy import resolve_fsi_policy, compute_premium_breakdown


class Command(BaseCommand):
    help = "Generate strict GDCR 100% compliance report across sample FPs."

    def add_arguments(self, parser):
        parser.add_argument("--tp", type=int, required=True, help="TP scheme number (e.g. 14)")
        parser.add_argument("--fps", type=str, default="", help="Comma-separated FP numbers; blank = all")
        parser.add_argument("--output", type=str, required=True, help="Output CSV path")
        parser.add_argument("--limit", type=int, default=None, help="Optional row limit after filtering")
        parser.add_argument(
            "--jantri-rate-per-sqm",
            type=float,
            default=None,
            help="Optional Jantri rate (INR/sq.m) for premium amount calculation.",
        )

    def handle(self, *args, **options):
        tp = options["tp"]
        fps_raw = (options.get("fps") or "").strip()
        out_path = options["output"]
        limit = options.get("limit")
        jantri_rate_per_sqm = options.get("jantri_rate_per_sqm")

        qs = Plot.objects.filter(tp_scheme=f"TP{tp}").order_by("fp_number")
        if fps_raw:
            fps = [x.strip() for x in fps_raw.split(",") if x.strip()]
            qs = qs.filter(fp_number__in=fps)
        if limit:
            qs = qs[: int(limit)]
        plots: List[Plot] = list(qs)
        if not plots:
            raise CommandError(f"No plots found for TP{tp} with provided filters.")

        rows = []
        for p in plots:
            road_width = float(getattr(p, "road_width_m", 0.0) or 0.0)
            if road_width <= 0:
                rows.append(
                    {
                        "fp_number": p.fp_number,
                        "road_width_m": "",
                        "status": "SKIPPED",
                        "reason": "missing_road_width",
                    }
                )
                continue

            policy = resolve_fsi_policy(
                plot=p,
                road_width_m=road_width,
                authority_override=None,
                zone_override=None,
                distance_to_wide_road_m=None,
            )
            sol = evaluate_development_configuration(
                plot=p,
                storey_height_m=3.0,
                min_width_m=5.0,
                min_depth_m=3.7,   # ≥ stair_run_m (3.6m) + tolerance
                mode="development",
                debug=False,
            )
            infeasible = sol.n_towers <= 0 or sol.floors <= 0
            corridor_check = (policy.corridor_distance_m is not None) or (not policy.corridor_eligible)
            legal_gating_check = bool(policy.legal_gating_applied)
            exclusion_check = (float(sol.exclusion_adjusted_bua_sqft or 0.0) >= 0.0) and (
                float(sol.exclusion_adjusted_bua_sqft or 0.0) <= float(sol.total_bua_sqft or 0.0) + 1e-6
            )
            premium = compute_premium_breakdown(
                achieved_fsi=float(sol.achieved_fsi or 0.0),
                plot_area_sqm=float(p.plot_area_sqm or 0.0),
                base_fsi=float(policy.base_fsi),
                max_fsi=float(policy.max_fsi),
                corridor_eligible=bool(policy.corridor_eligible),
                jantri_rate_per_sqm=jantri_rate_per_sqm,
            )
            premium_check = premium != {}
            premium_amount_total = 0.0
            for t in premium.get("tiers", []) or []:
                amt = t.get("premium_amount_inr")
                if amt is not None:
                    premium_amount_total += float(amt)
            all_checks = corridor_check and legal_gating_check and exclusion_check and premium_check and (not infeasible)
            failed_checks = []
            if not corridor_check:
                failed_checks.append("corridor_geometry")
            if not legal_gating_check:
                failed_checks.append("legal_gating")
            if not exclusion_check:
                failed_checks.append("exclusion_adjusted_fsi")
            if not premium_check:
                failed_checks.append("premium_breakdown")
            if infeasible:
                failed_checks.append("end_to_end_feasible")

            rows.append(
                {
                    "fp_number": p.fp_number,
                    "road_width_m": round(road_width, 3),
                    "authority": policy.authority,
                    "zone": policy.zone,
                    "corridor_eligible": "Y" if policy.corridor_eligible else "N",
                    "corridor_distance_m": round(float(policy.corridor_distance_m), 3)
                    if policy.corridor_distance_m is not None
                    else "",
                    "max_fsi": round(float(policy.max_fsi), 3),
                    "achieved_fsi": round(float(sol.achieved_fsi or 0.0), 4),
                    "gross_bua_sqft": round(float(sol.total_bua_sqft or 0.0), 2),
                    "counted_bua_sqft": round(float(sol.exclusion_adjusted_bua_sqft or 0.0), 2),
                    "premium_additional_fsi_used": premium.get("additional_fsi_used", ""),
                    "premium_amount_total_inr": round(premium_amount_total, 2) if jantri_rate_per_sqm else "",
                    "check_corridor_geometry": "PASS" if corridor_check else "FAIL",
                    "check_legal_gating": "PASS" if legal_gating_check else "FAIL",
                    "check_exclusion_adjusted_fsi": "PASS" if exclusion_check else "FAIL",
                    "check_premium_breakdown": "PASS" if premium_check else "FAIL",
                    "check_end_to_end_feasible": "PASS" if not infeasible else "FAIL",
                    "overall_100_mode": "PASS" if all_checks else "FAIL",
                    "notes": ";".join(policy.notes),
                    "status": "PASS" if all_checks else "FAIL",
                    "reason": ";".join(failed_checks) if failed_checks else "",
                    "feasibility_detail": (
                        getattr(sol, "feasibility_detail", "") or ""
                    ) if infeasible else "",
                }
            )

        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        columns = [
            "fp_number",
            "road_width_m",
            "authority",
            "zone",
            "corridor_eligible",
            "corridor_distance_m",
            "max_fsi",
            "achieved_fsi",
            "gross_bua_sqft",
            "counted_bua_sqft",
            "premium_additional_fsi_used",
            "premium_amount_total_inr",
            "check_corridor_geometry",
            "check_legal_gating",
            "check_exclusion_adjusted_fsi",
            "check_premium_breakdown",
            "check_end_to_end_feasible",
            "overall_100_mode",
            "notes",
            "status",
            "reason",
            "feasibility_detail",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

        total = len(rows)
        passed = sum(1 for r in rows if r.get("overall_100_mode") == "PASS")
        self.stdout.write(self.style.SUCCESS(f"Wrote {out_path}: {passed}/{total} PASS in 100-mode checks."))
