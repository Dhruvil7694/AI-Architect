from __future__ import annotations

from typing import Any, Dict, List

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from services.plot_service import get_plot_by_public_id
from architecture.services.development_pipeline import (
    generate_optimal_development_floor_plans,
)
from api.mappers.development_mapper import map_development_result_to_dict
from api.serializers.ai_planner import (
    AIPlannerScenarioRequestSerializer,
)
from ai_planner.program_generator import generate_program_spec, ProgramSpec
from ai_planner.scenario_generator import generate_scenarios
from ai_planner.design_critic import generate_design_insights
from planning.program_spec_mapper import build_program_spec_from_inputs


class AIPlannerScenariosAPIView(APIView):
    """
    AI-assisted scenario generator for site planning.

    Flow:
      1. Convert user brief + site area into a ProgramSpec.
      2. Generate three high-level scenarios (balanced / high density / landmark).
      3. For each scenario, run the deterministic development pipeline.
      4. Run the design critic on the resulting metrics.
      5. Return scenarios + layouts + textual insights.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = AIPlannerScenarioRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        brief: str = data["brief"]
        site_id: str = data["site_id"]
        inputs: Dict[str, Any] = data.get("inputs") or {}

        try:
            plot = get_plot_by_public_id(site_id)
        except Exception:
            return Response(
                {"detail": "Site not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        site_area_sqm = float(getattr(plot, "plot_area_sqm", 0.0) or 0.0)

        # 1) Deterministic baseline from PlannerInputs
        base_program: ProgramSpec = build_program_spec_from_inputs(inputs)

        # 2) Optional AI refinement based on brief + site area
        ai_program: ProgramSpec = generate_program_spec(
            brief=brief,
            site_area=site_area_sqm,
        )

        # 3) Merge: preserve deterministic unit_mix, segment-derived priorities
        #    and explicit tower/floor hints; let AI fill in softer fields.
        program_spec = ProgramSpec(
            unit_mix=base_program.unit_mix or ai_program.unit_mix,
            target_units=ai_program.target_units or base_program.target_units,
            preferred_towers=base_program.preferred_towers or ai_program.preferred_towers,
            max_floors=base_program.max_floors or ai_program.max_floors,
            open_space_priority=base_program.open_space_priority or ai_program.open_space_priority,
            density_priority=base_program.density_priority or ai_program.density_priority,
        )
        scenarios = generate_scenarios(
            program_spec=program_spec,
            site_area_sqm=site_area_sqm,
        )

        scenario_payloads: List[Dict[str, Any]] = []
        for scenario in scenarios:
            # Thread the merged ProgramSpec into the deterministic development
            # pipeline so skeleton and floor layout can respond to unit_mix.
            result = generate_optimal_development_floor_plans(
                plot=plot,
                program_spec=program_spec,
                forced_towers=int(scenario.get("tower_count") or 0) or None,
                target_fsi=float(scenario.get("fsi_target") or 0.0) or None,
            )
            result_payload = map_development_result_to_dict(
                result,
                geometry_format="geojson",
            )

            metrics = (
                result_payload.get("metrics")  # from mapper dict
                or {}
            )
            insights = generate_design_insights(
                placement_debug_metrics=result.placement_debug_metrics,
                plan_metrics=metrics,
            )

            scenario_payloads.append(
                {
                    "label": scenario.get("label"),
                    "tower_count": scenario.get("tower_count"),
                    "fsi_target": scenario.get("fsi_target"),
                    "plan": result_payload,
                    "design_insights": insights,
                }
            )

        response_payload: Dict[str, Any] = {
            "program_spec": {
                "unit_mix": program_spec.unit_mix,
                "target_units": program_spec.target_units,
                "preferred_towers": program_spec.preferred_towers,
                "max_floors": program_spec.max_floors,
                "open_space_priority": program_spec.open_space_priority,
                "density_priority": program_spec.density_priority,
            },
            "scenarios": scenario_payloads,
        }

        return Response(response_payload, status=status.HTTP_200_OK)


__all__ = ["AIPlannerScenariosAPIView"]

