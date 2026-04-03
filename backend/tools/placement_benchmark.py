#!/usr/bin/env python
"""
tools/placement_benchmark.py
-----------------------------
Batch-evaluates placement quality across multiple plots from a TP scheme.

Usage
-----
    cd backend
    python tools/placement_benchmark.py --tp 14 --limit 50
    python tools/placement_benchmark.py --tp 14              # all plots
    python tools/placement_benchmark.py --tp 14 --limit 10 --out-dir /tmp/bench

Outputs (written to --out-dir, default: tools/benchmark_out/)
-------
    benchmark_results.csv                    — per-plot metrics table
    benchmark_results.json                   — same data + aggregate stats
    placement_efficiency_histogram.png       — efficiency distribution chart
    debug_outputs/plot_<id>_placement.geojson — GeoJSON snapshot per plot
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Bootstrap Django ──────────────────────────────────────────────────────────
# Must happen before any Django / app imports.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402
django.setup()

# ── App imports (after django.setup) ─────────────────────────────────────────
from tp_ingestion.models import Plot  # noqa: E402
from architecture.services.development_pipeline import (  # noqa: E402
    generate_optimal_development_floor_plans,
    DevelopmentFloorPlanResult,
)

# ── CSV columns (order matters) ───────────────────────────────────────────────
CSV_COLUMNS = [
    "plot_id",
    "fp_number",
    "tp_scheme",
    "status",
    "n_towers_placed",
    "envelope_area_sqft",
    "footprint_area_sqft",
    "efficiency_ratio",
    "leftover_area_sqft",
    "leftover_compactness_score",
    "road_frontage_length_m",
    "cop_area_sqft",
    "cop_min_dimension_m",
    "tower_orientation_angles_deg",
    "elapsed_s",
    "error",
]


# ── Core per-plot runner ──────────────────────────────────────────────────────

def _run_plot(plot: Plot) -> Dict[str, Any]:
    """Run the full pipeline for one plot and return a flat metrics dict."""
    row: Dict[str, Any] = {
        "plot_id": str(plot.id),
        "fp_number": getattr(plot, "fp_number", ""),
        "tp_scheme": getattr(plot, "tp_scheme", ""),
        "status": "error",
        "n_towers_placed": 0,
        "envelope_area_sqft": None,
        "footprint_area_sqft": None,
        "efficiency_ratio": None,
        "leftover_area_sqft": None,
        "leftover_compactness_score": None,
        "road_frontage_length_m": None,
        "cop_area_sqft": None,
        "cop_min_dimension_m": None,
        "tower_orientation_angles_deg": "",
        "elapsed_s": 0.0,
        "error": "",
    }

    t0 = time.perf_counter()
    try:
        result: DevelopmentFloorPlanResult = generate_optimal_development_floor_plans(
            plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.7,
        )
        elapsed = round(time.perf_counter() - t0, 3)
        row["elapsed_s"] = elapsed
        row["status"] = result.status if result.status else "unknown"

        dm = result.placement_debug_metrics
        if dm is not None:
            row["n_towers_placed"] = dm.n_towers_placed
            row["envelope_area_sqft"] = round(dm.envelope_area_sqft, 2)
            row["footprint_area_sqft"] = round(dm.footprint_area_sqft, 2)
            row["efficiency_ratio"] = round(dm.footprint_utilization_pct / 100.0, 4)
            row["leftover_area_sqft"] = round(dm.leftover_area_sqft, 2)
            row["leftover_compactness_score"] = round(dm.leftover_compactness_score, 4)
            row["road_frontage_length_m"] = round(dm.road_frontage_length_m, 3)
            row["cop_area_sqft"] = round(dm.cop_area_sqft, 2)
            row["cop_min_dimension_m"] = round(dm.cop_min_dimension_m, 3)
            angles = dm.tower_orientation_angles_deg
            row["tower_orientation_angles_deg"] = (
                ";".join(f"{a:.1f}" for a in angles) if angles else ""
            )

    except Exception:  # noqa: BLE001
        elapsed = round(time.perf_counter() - t0, 3)
        row["elapsed_s"] = elapsed
        row["error"] = traceback.format_exc(limit=3).strip().splitlines()[-1]

    return row


def _geojson_for_plot(plot: Plot) -> Optional[Dict[str, Any]]:
    """Return the placement debug GeoJSON for a plot, or None on error."""
    try:
        result = generate_optimal_development_floor_plans(
            plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.7,
        )
        return result.placement_debug_geojson
    except Exception:  # noqa: BLE001
        return None


# ── Aggregate statistics ──────────────────────────────────────────────────────

def _aggregate_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics across all plots."""
    efficiencies = [r["efficiency_ratio"] for r in rows if r["efficiency_ratio"] is not None]
    compactnesses = [r["leftover_compactness_score"] for r in rows if r["leftover_compactness_score"] is not None]
    cop_dims = [r["cop_min_dimension_m"] for r in rows if r["cop_min_dimension_m"] is not None]

    def _stats(values: List[float]) -> Dict[str, float]:
        if not values:
            return {"mean": None, "median": None, "min": None, "max": None}
        s = sorted(values)
        n = len(s)
        median = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
        return {
            "mean": round(sum(s) / n, 4),
            "median": round(median, 4),
            "min": round(s[0], 4),
            "max": round(s[-1], 4),
            "count": n,
        }

    total = len(rows)
    errors = sum(1 for r in rows if r["status"] == "error")
    below_60 = sum(1 for r in rows if r["efficiency_ratio"] is not None and r["efficiency_ratio"] < 0.60)
    cop_violations = sum(
        1 for r in rows
        if r["cop_min_dimension_m"] is not None and 0 < r["cop_min_dimension_m"] < 6.0
    )

    return {
        "total_plots": total,
        "error_count": errors,
        "success_count": total - errors,
        "plots_below_60pct_efficiency": below_60,
        "cop_gdcr_violations": cop_violations,
        "efficiency_ratio": _stats(efficiencies),
        "leftover_compactness": _stats(compactnesses),
        "cop_min_dimension_m": _stats(cop_dims),
    }


# ── Histogram ─────────────────────────────────────────────────────────────────

def _save_histogram(rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Save a matplotlib efficiency distribution histogram."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  [warn] matplotlib not available — skipping histogram")
        return

    efficiencies = [r["efficiency_ratio"] for r in rows if r["efficiency_ratio"] is not None]
    if not efficiencies:
        print("  [warn] No efficiency data — skipping histogram")
        return

    bins = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01]
    labels = ["<40%", "40–50%", "50–60%", "60–70%", "70–80%", "80%+"]
    colors = ["#d32f2f", "#f57c00", "#fbc02d", "#388e3c", "#1976d2", "#7b1fa2"]

    counts = [0] * (len(bins) - 1)
    for e in efficiencies:
        for i in range(len(bins) - 1):
            if bins[i] <= e < bins[i + 1]:
                counts[i] += 1
                break

    fig, ax = plt.subplots(figsize=(10, 6))
    x = range(len(labels))
    bars = ax.bar(x, counts, color=colors, edgecolor="white", linewidth=0.8)

    # Annotate counts
    for bar, count in zip(bars, counts):
        if count > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.3,
                str(count),
                ha="center", va="bottom", fontsize=11, fontweight="bold",
            )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_xlabel("Footprint Utilisation (footprint / envelope area)", fontsize=13)
    ax.set_ylabel("Number of Plots", fontsize=13)
    ax.set_title(
        f"Placement Efficiency Distribution  —  {len(efficiencies)} plots",
        fontsize=14, fontweight="bold",
    )

    # Reference line at 60%
    ax.axvline(x=2.5, color="red", linestyle="--", linewidth=1.5, label="60% threshold")
    ax.legend(fontsize=11)

    mean_eff = sum(efficiencies) / len(efficiencies)
    ax.text(
        0.98, 0.95,
        f"Mean: {mean_eff:.1%}\nMedian: {sorted(efficiencies)[len(efficiencies)//2]:.1%}",
        transform=ax.transAxes, ha="right", va="top",
        fontsize=11, bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8),
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Histogram saved → {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Placement quality benchmark across a TP scheme.")
    parser.add_argument("--tp", required=True, help="TP scheme number (e.g. 14)")
    parser.add_argument("--limit", type=int, default=None, help="Max plots to process (default: all)")
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).parent / "benchmark_out"),
        help="Output directory (default: tools/benchmark_out/)",
    )
    parser.add_argument(
        "--skip-geojson",
        action="store_true",
        help="Skip per-plot GeoJSON snapshot saving (faster)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    debug_dir = out_dir / "debug_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    tp_scheme = f"TP{args.tp}"
    print(f"\n{'='*60}")
    print(f"  Placement Benchmark — {tp_scheme}")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}")

    # ── Load plots ────────────────────────────────────────────────────────────
    qs = Plot.objects.filter(tp_scheme=tp_scheme).order_by("fp_number")
    plots = list(qs)
    if not plots:
        print(f"[error] No plots found for tp_scheme='{tp_scheme}'")
        sys.exit(1)

    if args.limit:
        plots = plots[: args.limit]

    print(f"\nLoaded {len(plots)} plots (tp_scheme={tp_scheme})\n")

    # ── Run pipeline per plot ─────────────────────────────────────────────────
    rows: List[Dict[str, Any]] = []
    for i, plot in enumerate(plots, 1):
        label = f"FP{getattr(plot, 'fp_number', plot.id)}"
        print(f"  [{i:>3}/{len(plots)}] {label:<12}", end="", flush=True)

        row = _run_plot(plot)
        rows.append(row)

        eff = row["efficiency_ratio"]
        eff_str = f"{eff:.1%}" if eff is not None else "N/A"
        err_str = f"  ← {row['error'][:60]}" if row["error"] else ""
        print(f"  efficiency={eff_str}  status={row['status']}  {row['elapsed_s']:.2f}s{err_str}")

        # Save GeoJSON snapshot
        if not args.skip_geojson and row["status"] != "error":
            geojson = _geojson_for_plot(plot)
            if geojson is not None:
                gj_path = debug_dir / f"plot_{plot.id}_placement.geojson"
                gj_path.write_text(json.dumps(geojson, indent=2))

    # ── Write CSV ─────────────────────────────────────────────────────────────
    csv_path = out_dir / "benchmark_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n  CSV → {csv_path}")

    # ── Write JSON ────────────────────────────────────────────────────────────
    agg = _aggregate_stats(rows)
    json_payload = {
        "benchmark_config": {
            "tp_scheme": tp_scheme,
            "n_plots": len(plots),
            "limit": args.limit,
        },
        "aggregate": agg,
        "plots": rows,
    }
    json_path = out_dir / "benchmark_results.json"
    json_path.write_text(json.dumps(json_payload, indent=2, default=str))
    print(f"  JSON → {json_path}")

    # ── Histogram ─────────────────────────────────────────────────────────────
    hist_path = out_dir / "placement_efficiency_histogram.png"
    _save_histogram(rows, hist_path)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  AGGREGATE SUMMARY")
    print(f"{'='*60}")
    print(f"  Total plots      : {agg['total_plots']}")
    print(f"  Errors           : {agg['error_count']}")
    print(f"  Below 60% eff    : {agg['plots_below_60pct_efficiency']}")
    print(f"  COP violations   : {agg['cop_gdcr_violations']}  (min_dim < 6 m)")
    eff_s = agg["efficiency_ratio"]
    if eff_s["count"]:
        print(f"  Efficiency ratio : mean={eff_s['mean']:.1%}  "
              f"median={eff_s['median']:.1%}  "
              f"min={eff_s['min']:.1%}  max={eff_s['max']:.1%}")
    cmp_s = agg["leftover_compactness"]
    if cmp_s.get("count"):
        print(f"  Compactness      : mean={cmp_s['mean']:.3f}  "
              f"median={cmp_s['median']:.3f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
