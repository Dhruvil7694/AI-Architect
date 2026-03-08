"""
api/views/flat_layout.py
-------------------------
POST /api/development/flat-layout/

Graph-based flat floor plan generator.
Accepts a Claude topology JSON + optional unit dimensions,
runs the full floorplan_engine pipeline, and returns:
  - SVG string
  - Room rectangles (metres)
  - Compliance report (GDCR §13)
  - Layout quality score

Request body (JSON):
{
    "topology": {
        "flat_type": "2BHK",
        "rooms": ["entry", "living", ...],
        "adjacency_graph": [["entry","living"], ...]
    },
    "unit_w":    0.0,          // outer flat width m  (0 = auto)
    "unit_d":    0.0,          // outer flat depth m  (0 = auto)
    "flat_type": "2BHK",       // "1BHK"|"2BHK"|"3BHK" (overrides topology)
    "sa_steps":  2500,         // simulated annealing iterations
    "seed":      42
}

Response (JSON):
{
    "status": "ok",
    "svg":    "<svg>...</svg>",
    "rects":  { "living": {"x":0,"y":0,"w":4,"h":4}, ... },
    "compliance": {
        "all_pass":   false,
        "fail_count": 2,
        "warn_count": 1,
        "fails":      [...],
        "warns":      [...]
    },
    "score":  { "adjacency_score": 12.5, "efficiency_pct": 72.1, ... },
    "unit_w": 11.8,
    "unit_d":  7.6,
    "flat_type": "2BHK",
    "graph_summary": { ... }
}
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

VALID_FLAT_TYPES = {"1BHK", "2BHK", "3BHK"}


class FlatLayoutAPIView(APIView):
    """
    Graph-based flat interior layout generator (floorplan_engine pipeline).
    """

    def post(self, request, *args, **kwargs):
        data = request.data

        # ── Validate required field ───────────────────────────────────────────
        topology = data.get("topology")
        if not topology or not isinstance(topology, dict):
            return Response(
                {"detail": "'topology' must be a dict with 'rooms' and 'adjacency_graph'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not topology.get("rooms") and not topology.get("nodes"):
            return Response(
                {"detail": "'topology.rooms' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        flat_type = (
            data.get("flat_type")
            or topology.get("flat_type")
            or "2BHK"
        ).upper().replace(" ", "")

        unit_w    = float(data.get("unit_w",    0.0))
        unit_d    = float(data.get("unit_d",    0.0))
        sa_steps  = int(data.get("sa_steps",    2500))
        seed      = int(data.get("seed",        42))

        # ── Run pipeline ──────────────────────────────────────────────────────
        try:
            from floorplan_engine.pipeline import generate_floorplan
            result = generate_floorplan(
                topology  = topology,
                unit_w    = unit_w,
                unit_d    = unit_d,
                flat_type = flat_type,
                sa_steps  = sa_steps,
                seed      = seed,
            )
        except Exception as exc:
            logger.exception("FlatLayoutAPIView: pipeline error: %s", exc)
            return Response(
                {"detail": f"Layout engine error: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "status":        "ok",
                "svg":           result["svg"],
                "rects":         result["rects"],
                "compliance":    {
                    "all_pass":   result["compliance"]["all_pass"],
                    "fail_count": result["compliance"]["fail_count"],
                    "warn_count": result["compliance"]["warn_count"],
                    "fails":      result["compliance"]["fails"],
                    "warns":      result["compliance"]["warns"],
                },
                "score":         result["score"],
                "unit_w":        result["unit_w"],
                "unit_d":        result["unit_d"],
                "flat_type":     result["flat_type"],
                "graph_summary": result["graph_summary"],
            },
            status=status.HTTP_200_OK,
        )
