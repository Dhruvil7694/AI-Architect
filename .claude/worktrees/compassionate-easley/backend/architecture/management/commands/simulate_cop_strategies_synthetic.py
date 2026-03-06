from __future__ import annotations

"""
simulate_cop_strategies_synthetic
---------------------------------

Management command to exercise the multi-strategy COP development optimiser
on synthetic plots (not fetched from the database) across a range of plot
areas.

For each synthetic plot area, the command:
  - Builds a square Plot geometry whose area matches the requested sqm.
  - Runs the optimiser separately for EDGE and CENTER COP strategies.
  - Runs the unified evaluate_development_configuration() selector.
  - Prints FSI and COP metrics per strategy and the selected configuration.

With --plot: writes comparison charts (FSI, floors, selected strategy) to
--output-dir for visual analysis. Requires matplotlib.
"""

from math import sqrt
from pathlib import Path
from typing import Any, Dict, List

from django.contrib.gis.geos import Polygon
from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot
from common.units import sqm_to_sqft

from architecture.regulatory.development_optimizer import (
    solve_optimal_development_configuration,
    evaluate_development_configuration,
)


class Command(BaseCommand):
    help = (
        "Simulate EDGE vs CENTER COP strategies on synthetic square plots "
        "for a range of plot areas (sqm), without using database plots."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--road-width",
            type=float,
            default=18.0,
            help="Road width in metres for all synthetic plots (default: 18.0).",
        )
        parser.add_argument(
            "--areas-sqm",
            type=str,
            default="1500,1900,2100,2500,3000,4000,6000,10000",
            help=(
                "Comma-separated list of plot areas in sqm "
                "(default: 1500,1900,2100,2500,3000,4000,6000,10000)."
            ),
        )
        parser.add_argument(
            "--storey-height",
            type=float,
            default=3.0,
            help="Storey height in metres (default: 3.0).",
        )
        parser.add_argument(
            "--min-width",
            type=float,
            default=5.0,
            help="Minimum footprint width in metres (default: 5.0).",
        )
        parser.add_argument(
            "--min-depth",
            type=float,
            default=3.5,
            help="Minimum footprint depth in metres (default: 3.5).",
        )
        parser.add_argument(
            "--plot",
            action="store_true",
            help="Generate comparison charts (FSI, floors, strategy) and save to --output-dir. Requires matplotlib.",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="out_cop_analysis",
            help="Directory for chart outputs when --plot is used (default: out_cop_analysis).",
        )

    def _parse_areas(self, raw: str) -> List[float]:
        areas: List[float] = []
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                val = float(token)
            except ValueError:
                continue
            if val > 0.0:
                areas.append(val)
        return areas

    def handle(self, *args, **options):
        road_width_m: float = float(options.get("road_width") or 0.0)
        storey_height_m: float = float(options.get("storey_height") or 3.0)
        min_width_m: float = float(options.get("min_width") or 5.0)
        min_depth_m: float = float(options.get("min_depth") or 3.5)

        areas_raw: str = options.get("areas_sqm") or ""
        areas_sqm: List[float] = self._parse_areas(areas_raw)

        if not areas_sqm:
            self.stdout.write("No valid areas provided; nothing to simulate.")
            return

        if road_width_m <= 0.0:
            self.stdout.write("road_width must be positive.")
            return

        do_plot = bool(options.get("plot"))
        output_dir = str(options.get("output_dir") or "out_cop_analysis").strip()

        self.stdout.write(
            "Simulating COP strategies on synthetic square plots "
            f"(road_width={road_width_m:.3f} m)."
        )
        if do_plot:
            self.stdout.write(f"Charts will be saved to: {output_dir}")

        rows: List[Dict[str, Any]] = []

        for idx, area_sqm in enumerate(areas_sqm):
            area_sqft = sqm_to_sqft(area_sqm)
            if area_sqft <= 0.0:
                continue

            # Construct a square polygon in DXF units whose area matches area_sqft.
            side_dxf = sqrt(area_sqft)
            poly = Polygon(
                (
                    (0.0, 0.0),
                    (side_dxf, 0.0),
                    (side_dxf, side_dxf),
                    (0.0, side_dxf),
                    (0.0, 0.0),
                )
            )

            plot = Plot(
                city="SYN",
                tp_scheme="TPSYN",
                fp_number=str(idx),
                area_excel=area_sqft,
                area_geometry=area_sqft,
                geom=poly,
                validation_status=True,
            )
            plot.road_width_m = road_width_m

            self.stdout.write("")
            self.stdout.write(
                f"===== Synthetic plot {idx} — area={area_sqm:.1f} sqm "
                f"({area_sqft:.1f} sq.ft) ====="
            )

            # Evaluate EDGE and CENTER strategies independently for diagnostics.
            edge_sol = solve_optimal_development_configuration(
                plot=plot,
                storey_height_m=storey_height_m,
                min_width_m=min_width_m,
                min_depth_m=min_depth_m,
                mode="development",
                debug=False,
                cop_strategy="edge",
            )
            center_sol = solve_optimal_development_configuration(
                plot=plot,
                storey_height_m=storey_height_m,
                min_width_m=min_width_m,
                min_depth_m=min_depth_m,
                mode="development",
                debug=False,
                cop_strategy="center",
            )

            self.stdout.write(
                "EDGE   -> FSI={:.3f}, floors={}, n_towers={}, cop_area_sqft={:.1f}, status={}".format(
                    edge_sol.achieved_fsi,
                    edge_sol.floors,
                    edge_sol.n_towers,
                    getattr(edge_sol, "cop_area_sqft", 0.0),
                    edge_sol.controlling_constraint,
                )
            )
            self.stdout.write(
                "CENTER -> FSI={:.3f}, floors={}, n_towers={}, cop_area_sqft={:.1f}, status={}".format(
                    center_sol.achieved_fsi,
                    center_sol.floors,
                    center_sol.n_towers,
                    getattr(center_sol, "cop_area_sqft", 0.0),
                    center_sol.controlling_constraint,
                )
            )

            # Unified selector (same logic used by the main development pipeline).
            best_sol = evaluate_development_configuration(
                plot=plot,
                storey_height_m=storey_height_m,
                min_width_m=min_width_m,
                min_depth_m=min_depth_m,
                mode="development",
                debug=False,
            )

            self.stdout.write(
                "SELECTED -> strategy={}, FSI={:.3f}, floors={}, n_towers={}, cop_area_sqft={:.1f}, controlling={}".format(
                    getattr(best_sol, "cop_strategy", "edge"),
                    best_sol.achieved_fsi,
                    best_sol.floors,
                    best_sol.n_towers,
                    getattr(best_sol, "cop_area_sqft", 0.0),
                    best_sol.controlling_constraint,
                )
            )

            rows.append({
                "area_sqm": area_sqm,
                "area_sqft": area_sqft,
                "edge_fsi": edge_sol.achieved_fsi,
                "edge_floors": edge_sol.floors,
                "edge_towers": edge_sol.n_towers,
                "edge_cop_sqft": getattr(edge_sol, "cop_area_sqft", 0.0),
                "edge_constraint": edge_sol.controlling_constraint,
                "center_fsi": center_sol.achieved_fsi,
                "center_floors": center_sol.floors,
                "center_towers": center_sol.n_towers,
                "center_cop_sqft": getattr(center_sol, "cop_area_sqft", 0.0),
                "center_constraint": center_sol.controlling_constraint,
                "selected_strategy": getattr(best_sol, "cop_strategy", "edge"),
                "selected_fsi": best_sol.achieved_fsi,
                "selected_floors": best_sol.floors,
                "selected_towers": best_sol.n_towers,
                "selected_cop_sqft": getattr(best_sol, "cop_area_sqft", 0.0),
                "selected_bua_sqft": getattr(best_sol, "total_bua_sqft", 0.0),
            })

        if do_plot and rows:
            self._plot_results(rows, output_dir)

    def _plot_results(self, rows: List[Dict[str, Any]], output_dir: str) -> None:
        """Generate comparison charts and save to output_dir. Requires matplotlib."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError as e:
            self.stdout.write(self.style.WARNING(
                f"Cannot generate plots: matplotlib not available ({e}). Install with: pip install matplotlib"
            ))
            return

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        areas = [r["area_sqm"] for r in rows]
        x = np.arange(len(areas))
        width = 0.35

        # ── 1. FSI comparison: EDGE vs CENTER (grouped bar) ─────────────────────
        fig1, ax1 = plt.subplots(figsize=(10, 5))
        edge_fsi = [r["edge_fsi"] for r in rows]
        center_fsi = [r["center_fsi"] for r in rows]
        bars1 = ax1.bar(x - width / 2, edge_fsi, width, label="EDGE COP", color="#2ecc71")
        bars2 = ax1.bar(x + width / 2, center_fsi, width, label="CENTER COP", color="#3498db")
        ax1.set_ylabel("Achieved FSI")
        ax1.set_xlabel("Plot area (sqm)")
        ax1.set_title("COP strategy comparison: EDGE vs CENTER FSI by plot area")
        ax1.set_xticks(x)
        ax1.set_xticklabels([f"{a:.0f}" for a in areas])
        ax1.legend()
        ax1.grid(axis="y", alpha=0.3)
        fig1.tight_layout()
        fsi_path = out_path / "cop_fsi_comparison.png"
        fig1.savefig(fsi_path, dpi=150)
        plt.close(fig1)
        self.stdout.write(self.style.SUCCESS(f"Saved: {fsi_path}"))

        # ── 2. Floors comparison ─────────────────────────────────────────────────
        fig2, ax2 = plt.subplots(figsize=(10, 5))
        edge_floors = [r["edge_floors"] for r in rows]
        center_floors = [r["center_floors"] for r in rows]
        ax2.bar(x - width / 2, edge_floors, width, label="EDGE COP", color="#2ecc71")
        ax2.bar(x + width / 2, center_floors, width, label="CENTER COP", color="#3498db")
        ax2.set_ylabel("Floors")
        ax2.set_xlabel("Plot area (sqm)")
        ax2.set_title("COP strategy comparison: Floors by plot area")
        ax2.set_xticks(x)
        ax2.set_xticklabels([f"{a:.0f}" for a in areas])
        ax2.legend()
        ax2.grid(axis="y", alpha=0.3)
        fig2.tight_layout()
        floors_path = out_path / "cop_floors_comparison.png"
        fig2.savefig(floors_path, dpi=150)
        plt.close(fig2)
        self.stdout.write(self.style.SUCCESS(f"Saved: {floors_path}"))

        # ── 3. Selected strategy (which strategy won per area) ───────────────────
        fig3, ax3 = plt.subplots(figsize=(10, 4))
        selected = [r["selected_strategy"].upper() for r in rows]
        colors = ["#2ecc71" if s == "EDGE" else "#3498db" for s in selected]
        ax3.bar(x, [1] * len(x), color=colors)
        ax3.set_ylabel("Selected")
        ax3.set_xlabel("Plot area (sqm)")
        ax3.set_title("Selected COP strategy by plot area (green=EDGE, blue=CENTER)")
        ax3.set_yticks([])
        ax3.set_xticks(x)
        ax3.set_xticklabels([f"{a:.0f}\n{s}" for a, s in zip(areas, selected)])
        fig3.tight_layout()
        strategy_path = out_path / "cop_selected_strategy.png"
        fig3.savefig(strategy_path, dpi=150)
        plt.close(fig3)
        self.stdout.write(self.style.SUCCESS(f"Saved: {strategy_path}"))

        # ── 4. Summary table as image (optional: FSI + floors + selected) ─────────
        fig4, ax4 = plt.subplots(figsize=(12, max(4, len(rows) * 0.35)))
        ax4.axis("off")
        col_headers = [
            "Area (sqm)", "EDGE FSI", "EDGE fl", "CENTER FSI", "CENTER fl",
            "Selected", "Sel. FSI", "Sel. fl",
        ]
        cell_text = []
        for r in rows:
            cell_text.append([
                f"{r['area_sqm']:.0f}",
                f"{r['edge_fsi']:.3f}",
                str(r["edge_floors"]),
                f"{r['center_fsi']:.3f}",
                str(r["center_floors"]),
                r["selected_strategy"].upper(),
                f"{r['selected_fsi']:.3f}",
                str(r["selected_floors"]),
            ])
        table = ax4.table(
            cellText=cell_text,
            colLabels=col_headers,
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.8)
        ax4.set_title("COP strategy summary: EDGE vs CENTER by plot area", fontsize=12)
        fig4.tight_layout()
        table_path = out_path / "cop_summary_table.png"
        fig4.savefig(table_path, dpi=150, bbox_inches="tight")
        plt.close(fig4)
        self.stdout.write(self.style.SUCCESS(f"Saved: {table_path}"))
