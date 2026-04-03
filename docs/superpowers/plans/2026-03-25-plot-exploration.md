# Plot Exploration Step — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Plot Exploration" step as the first planner step — auto-analyzes a plot under GDCR rules, shows constraints dashboard + 3 AI-generated development scenarios, letting users pick and tweak before site planning.

**Architecture:** Backend `GET /api/development/explore/{plot_id}/` reuses existing `compute_feasibility_map` + `resolve_fsi_policy` + `detect_road_edges_with_meta`, packages the data, sends to GPT-4o for 3 scenario suggestions, returns a combined response. Frontend adds `PlotExplorationView` as step 1 with split layout (TP map + constraints + scenario cards).

**Tech Stack:** Django REST Framework, GPT-4o via existing `call_openai`, React/Next.js, Zustand, TanStack Query, Tailwind CSS, MapLibre (existing `PlannerTpMap`).

---

## File Map

### New Backend Files
| File | Responsibility |
|------|---------------|
| `backend/services/plot_exploration_service.py` | Orchestrator: load plot → feasibility → FSI policy → road edges → setback annotations → AI scenarios → sellable estimates → fallback |
| `backend/services/plot_exploration_prompt.py` | Build (system_prompt, user_prompt) for GPT-4o scenario generation |
| `backend/api/views/plot_exploration.py` | Thin DRF `APIView` wrapping `explore_plot()` |

### New Frontend Files
| File | Responsibility |
|------|---------------|
| `frontend/src/modules/planner/components/PlotExplorationView.tsx` | Main split-view: left=TP map with annotations, right=constraints+scenarios+editor |
| `frontend/src/modules/planner/components/ConstraintsDashboard.tsx` | Renders GDCR constraints from `ExplorationResponse.constraints` |
| `frontend/src/modules/planner/components/ScenarioCards.tsx` | 3 scenario cards with select, key metrics, parameter editor on selection |

### Modified Files
| File | Change |
|------|--------|
| `backend/api/urls/development.py` | Add `explore/<str:plot_id>/` route |
| `backend/ai_layer/config.py` | Add `exploration_model`, `exploration_timeout_s`, `exploration_max_tokens` fields |
| `frontend/src/state/plannerStore.ts` | `PlanningStep = "explore" \| "site" \| "floor"`, add `selectedScenario`, default step → `"explore"` |
| `frontend/src/modules/planner/components/StepNavigation.tsx` | 3 steps with disable logic |
| `frontend/src/app/(protected)/planner/page.tsx` | Route `"explore"` to `PlotExplorationView` |
| `frontend/src/services/plannerService.ts` | Add `ExplorationResponse` types + `getPlotExploration()` |
| `frontend/src/modules/planner/hooks/usePlannerData.ts` | Add `usePlotExploration()` query hook |
| `frontend/src/lib/queryKeys.ts` | Add `exploration` key factory |

---

## Task 1: Backend — AI Config for Exploration

**Files:**
- Modify: `backend/ai_layer/config.py`

- [ ] **Step 1: Add exploration config fields to AIConfig**

In `backend/ai_layer/config.py`, add three new fields to the `AIConfig` dataclass (after line 45, the floor plan fields):

```python
    # Plot exploration scenario generation
    exploration_model: str = "gpt-4o"
    exploration_timeout_s: float = 30.0
    exploration_max_tokens: int = 2048
```

And add the env var overrides in `get_ai_config()` (after line 88, the floor plan overrides):

```python
        exploration_model=os.environ.get("OPENAI_EXPLORATION_MODEL", "gpt-4o"),
        exploration_timeout_s=_float_env("AI_EXPLORATION_TIMEOUT_S", 30.0),
        exploration_max_tokens=_int_env("AI_EXPLORATION_MAX_TOKENS", 2048),
```

- [ ] **Step 2: Verify no import errors**

Run: `cd backend && python -c "from ai_layer.config import get_ai_config; c = get_ai_config(); print(c.exploration_model, c.exploration_max_tokens)"`
Expected: `gpt-4o 2048`

- [ ] **Step 3: Commit**

```bash
git add backend/ai_layer/config.py
git commit -m "feat: add exploration AI config fields for plot exploration endpoint"
```

---

## Task 2: Backend — Exploration Prompt Builder

**Files:**
- Create: `backend/services/plot_exploration_prompt.py`

- [ ] **Step 1: Create the prompt builder**

Create `backend/services/plot_exploration_prompt.py`:

```python
"""
services/plot_exploration_prompt.py
-----------------------------------
Build (system_prompt, user_prompt) for GPT-4o plot exploration scenario generation.

Input: structured context dict with plot area, road width, GDCR limits, FSI policy,
unit compatibility, and permissible building types.

Output: tuple[str, str] — (system_prompt, user_prompt).
"""
from __future__ import annotations

from typing import Any


def build_exploration_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for GPT-4o scenario generation."""

    system_prompt = """You are an expert Indian real estate development feasibility consultant specializing in GDCR (Gujarat Development Control Regulations).

Given a plot's regulatory constraints, generate exactly 3 development scenarios as a JSON object.

RULES:
- Each scenario MUST respect the provided constraints (max towers, max floors, max height, max FSI).
- buildingType MUST be one of the provided permissibleBuildingTypes IDs.
- unitMix items MUST only include unit types marked as compatible.
- Scenarios MUST be meaningfully different: one maximizes density, one balances density/livability, one prioritizes premium positioning.
- All numeric values must be realistic and internally consistent.

OUTPUT FORMAT — a single JSON object, no markdown:
{
  "scenarios": [
    {
      "id": "high_density",
      "label": "High Density",
      "description": "<one line>",
      "towers": <int>,
      "floors": <int>,
      "buildingType": <int from permissible list>,
      "segment": "<budget|mid|premium|luxury>",
      "unitMix": ["2BHK", "3BHK"],
      "unitsPerCore": <2|4|6>,
      "estimatedFSI": <float>,
      "tradeoffNote": "<one line>"
    },
    { "id": "balanced", ... },
    { "id": "premium", ... }
  ]
}"""

    # Build user prompt from context
    c = context
    compatible_units = [k for k, v in c.get("unitCompatibility", {}).items() if v]
    building_types_str = ", ".join(
        f"ID {bt['id']}: {bt['label']} (max {bt['maxHeightM']}m)"
        for bt in c.get("permissibleBuildingTypes", [])
    )

    user_prompt = f"""PLOT ANALYSIS:
- Plot area: {c['plotAreaSqm']:.0f} sqm ({c['plotAreaSqm'] / 0.8361:.0f} sq.yd)
- Road width: {c['roadWidthM']}m
- Zone: {c.get('zone', 'R1')}

REGULATORY CONSTRAINTS:
- Max height: {c['maxHeightM']}m
- Max floors: {c['maxFloors']}
- Max FSI: {c['maxFSI']}
- Base FSI: {c['baseFSI']}
- Max ground cover: {c['maxGCPct']}%
- Max feasible towers: {c['maxFeasibleTowers']}
- Corridor eligible: {c.get('corridorEligible', False)}

PERMISSIBLE BUILDING TYPES: {building_types_str}
COMPATIBLE UNIT TYPES: {', '.join(compatible_units)}

SELLABLE RATIO TABLE (FSI → sellable sq.yd per sq.yd of plot):
  FSI 1.8 → 28, FSI 2.7 → 42, FSI 3.6 → 54, FSI 4.0 → 60
  (Use linear interpolation between points)

Generate 3 scenarios: high_density (maximize sellable area), balanced (recommended), premium (maximize unit value).
Each scenario must stay within the above constraints."""

    return system_prompt, user_prompt
```

- [ ] **Step 2: Verify module loads**

Run: `cd backend && python -c "from services.plot_exploration_prompt import build_exploration_prompt; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/plot_exploration_prompt.py
git commit -m "feat: add GPT-4o prompt builder for plot exploration scenarios"
```

---

## Task 3: Backend — Plot Exploration Service

**Files:**
- Create: `backend/services/plot_exploration_service.py`

- [ ] **Step 1: Create the exploration service**

Create `backend/services/plot_exploration_service.py`:

```python
"""
services/plot_exploration_service.py
------------------------------------
Orchestrator for the Plot Exploration endpoint.

Pipeline:
1. Load Plot → 2. Feasibility → 3. FSI Policy → 4. Road edges →
5. Setback annotations → 6. AI scenarios → 7. Sellable estimates →
8. Validate/clamp → 9. Fallback if AI fails
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any, Optional

from django.utils import timezone

from services.plot_service import get_plot_by_public_id
from architecture.services.feasibility_advisor import compute_feasibility_map
from architecture.services.feasibility_serializer import feasibility_to_dict
from architecture.regulatory.fsi_policy import (
    resolve_fsi_policy,
    FsiPolicyDecision,
    infer_zone_from_plot,
    infer_authority,
)
from architecture.spatial.road_edge_detector import detect_road_edges_with_meta
from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config
from services.plot_exploration_prompt import build_exploration_prompt

logger = logging.getLogger(__name__)

# ── Sellable ratio interpolation table ─────────────────────────────────────
# (achieved_fsi, sellable_sqyd_per_sqyd_of_plot)
_SELLABLE_TABLE = [
    (1.8, 28.0),
    (2.7, 42.0),
    (3.6, 54.0),
    (4.0, 60.0),
]

# Segment average carpet areas (sqm)
_SEGMENT_AVG_CARPET = {
    "budget": 45.0,
    "mid": 65.0,
    "premium": 85.0,
    "luxury": 110.0,
}

_RERA_EFFICIENCY = 0.55


def _interpolate_sellable_ratio(fsi: float) -> float:
    """Linear interpolation of sellable per sq.yd from FSI."""
    if fsi <= _SELLABLE_TABLE[0][0]:
        return _SELLABLE_TABLE[0][1]
    if fsi >= _SELLABLE_TABLE[-1][0]:
        return _SELLABLE_TABLE[-1][1]
    for i in range(len(_SELLABLE_TABLE) - 1):
        f0, s0 = _SELLABLE_TABLE[i]
        f1, s1 = _SELLABLE_TABLE[i + 1]
        if f0 <= fsi <= f1:
            t = (fsi - f0) / (f1 - f0) if f1 != f0 else 0.0
            return s0 + t * (s1 - s0)
    return _SELLABLE_TABLE[-1][1]


def _estimate_sellable(plot_area_sqm: float, fsi: float, segment: str) -> dict:
    """Compute sellable area estimates from FSI and segment."""
    plot_area_sqyd = plot_area_sqm / 0.8361
    sellable_per_sqyd = _interpolate_sellable_ratio(fsi)
    sellable_sqyd = plot_area_sqyd * sellable_per_sqyd
    sellable_sqm = sellable_sqyd * 0.8361
    avg_unit_area = _SEGMENT_AVG_CARPET.get(segment, 65.0)
    estimated_total_units = int(sellable_sqm / avg_unit_area) if avg_unit_area > 0 else 0
    return {
        "estimatedSellableAreaSqm": round(sellable_sqm, 0),
        "sellablePerSqYd": round(sellable_per_sqyd, 1),
        "estimatedTotalUnits": estimated_total_units,
    }


def _build_setback_annotations(plot, road_edge_indices: list[int]) -> tuple[list, list, list]:
    """
    Compute per-edge setback annotations and envelope coordinates.

    Returns (setback_distances, road_edges_annotated, envelope_coords).
    """
    setback_distances = []
    road_edges_annotated = []

    if plot.geom is None:
        return setback_distances, road_edges_annotated, []

    coords = list(plot.geom.coords[0])
    n_edges = len(coords) - 1
    road_width_m = float(plot.road_width_m or 0.0)

    for i in range(n_edges):
        is_road = i in road_edge_indices
        edge_type = "road" if is_road else "side"
        # Simplified: road edges get road margin, others get side/rear margin
        # A more sophisticated version would detect rear edges
        if is_road:
            distance_m = _get_road_margin(road_width_m)
            road_edges_annotated.append({
                "edgeIndex": i,
                "roadWidthM": road_width_m,
                "setbackM": distance_m,
            })
        else:
            distance_m = 3.0  # default side/rear margin
            # Simple heuristic: edge opposite to road is rear
            if n_edges >= 3 and road_edge_indices:
                opp = (road_edge_indices[0] + n_edges // 2) % n_edges
                if i == opp:
                    edge_type = "rear"

        setback_distances.append({
            "edgeIndex": i,
            "distanceM": distance_m,
            "type": edge_type,
        })

    # Compute rough envelope by inward-buffering the plot polygon
    envelope_coords_list = []
    try:
        from shapely.geometry import shape as shapely_shape
        plot_shapely = shapely_shape({
            "type": "Polygon",
            "coordinates": [[(c[0], c[1]) for c in coords]],
        })
        min_setback_dxf = min(s["distanceM"] for s in setback_distances) / 0.3048 if setback_distances else 10.0
        envelope = plot_shapely.buffer(-min_setback_dxf)
        if not envelope.is_empty and envelope.geom_type == "Polygon":
            envelope_coords_list = [list(c) for c in envelope.exterior.coords]
    except Exception:
        pass

    return setback_distances, road_edges_annotated, envelope_coords_list


def _get_road_margin(road_width_m: float) -> float:
    """Get road margin from GDCR Table 6.24 simplified."""
    if road_width_m <= 12:
        return 3.0
    elif road_width_m <= 15:
        return 3.0
    elif road_width_m <= 18:
        return 4.5
    elif road_width_m <= 30:
        return 6.0
    else:
        return 9.0


def _build_unit_compatibility(fmap_dict: dict) -> dict:
    """Extract unit compatibility from feasibility's recommended tower option."""
    compat = fmap_dict.get("floorPlanCompat", {})
    return {
        "1BHK": compat.get("canFit1bhk", True),
        "2BHK": compat.get("canFit2bhk", True),
        "3BHK": compat.get("canFit3bhk", True),
        "4BHK": compat.get("canFit4bhk", False),
    }


def _generate_ai_scenarios(context: dict) -> Optional[list[dict]]:
    """Call GPT-4o to generate 3 development scenarios."""
    config = get_ai_config()
    system_prompt, user_prompt = build_exploration_prompt(context)

    raw = call_openai(
        model=config.exploration_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_s=config.exploration_timeout_s,
        temperature=0.3,
        rate_limit_kind="advisor",
        max_tokens=config.exploration_max_tokens,
    )

    if raw is None:
        logger.warning("AI exploration call returned None")
        return None

    parsed = parse_json_response(raw)
    if parsed is None:
        logger.warning("AI exploration response failed to parse. First 500 chars: %s", raw[:500])
        return None

    scenarios = parsed.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) == 0:
        logger.warning("AI returned no scenarios")
        return None

    return scenarios


def _generate_fallback_scenarios(fmap_dict: dict, context: dict) -> list[dict]:
    """Deterministic fallback when AI is unavailable."""
    max_towers = context["maxFeasibleTowers"]
    max_floors = context["maxFloors"]
    recommended_towers = fmap_dict.get("recommendedTowers", 1)
    recommended_floors = fmap_dict.get("recommendedFloors", max_floors)
    compat = context["unitCompatibility"]
    compatible = [k for k, v in compat.items() if v]

    # Pick building type: use first permissible
    btypes = context.get("permissibleBuildingTypes", [])
    bt_id = btypes[-1]["id"] if btypes else 2  # highest type for density

    scenarios = [
        {
            "id": "high_density",
            "label": "High Density",
            "description": "Maximize sellable area with compact units",
            "towers": max_towers,
            "floors": max_floors,
            "buildingType": bt_id,
            "segment": "budget",
            "unitMix": compatible[:2] if len(compatible) >= 2 else compatible,
            "unitsPerCore": 6,
            "estimatedFSI": context["maxFSI"],
            "tradeoffNote": "Maximum unit count, smaller open spaces",
        },
        {
            "id": "balanced",
            "label": "Balanced",
            "description": "Good mix of density and livability",
            "towers": max(1, recommended_towers),
            "floors": recommended_floors,
            "buildingType": btypes[len(btypes) // 2]["id"] if btypes else 2,
            "segment": "mid",
            "unitMix": ["2BHK", "3BHK"] if "2BHK" in compatible and "3BHK" in compatible else compatible[:2],
            "unitsPerCore": 4,
            "estimatedFSI": round(context["baseFSI"] * 1.5, 2),
            "tradeoffNote": "Balanced density and open space",
        },
        {
            "id": "premium",
            "label": "Premium",
            "description": "Fewer towers, larger units, premium positioning",
            "towers": 1,
            "floors": recommended_floors,
            "buildingType": btypes[0]["id"] if btypes else 1,
            "segment": "luxury",
            "unitMix": compatible[-2:] if len(compatible) >= 2 else compatible,
            "unitsPerCore": 4,
            "estimatedFSI": context["baseFSI"],
            "tradeoffNote": "Maximum value per unit, large open spaces",
        },
    ]
    return scenarios


def _clamp_scenario(scenario: dict, context: dict) -> dict:
    """Validate and clamp a scenario to respect constraints."""
    scenario["towers"] = max(1, min(scenario.get("towers", 1), context["maxFeasibleTowers"]))
    scenario["floors"] = max(1, min(scenario.get("floors", 1), context["maxFloors"]))
    scenario["estimatedFSI"] = min(scenario.get("estimatedFSI", 1.8), context["maxFSI"])

    # Ensure buildingType is permissible
    permissible_ids = {bt["id"] for bt in context.get("permissibleBuildingTypes", [])}
    if scenario.get("buildingType") not in permissible_ids and permissible_ids:
        scenario["buildingType"] = max(permissible_ids)

    # Ensure unitMix only has compatible types
    compat = context.get("unitCompatibility", {})
    scenario["unitMix"] = [u for u in scenario.get("unitMix", []) if compat.get(u, False)]
    if not scenario["unitMix"]:
        scenario["unitMix"] = [k for k, v in compat.items() if v][:2]

    return scenario


def explore_plot(plot_id: str) -> dict:
    """
    Main orchestrator for plot exploration.

    Returns a dict matching the ExplorationResponse schema.
    """
    # 1. Load plot
    plot = get_plot_by_public_id(plot_id)
    road_width_m = float(plot.road_width_m or 0.0)

    # 2. Compute or load cached feasibility
    use_default_cache = True
    has_cached = (
        use_default_cache
        and plot.cached_feasibility_json is not None
        and abs(float(plot.cached_feasibility_storey_height_m or 0.0) - 3.0) < 1e-9
    )
    if has_cached:
        fmap_dict = dict(plot.cached_feasibility_json)
    else:
        fmap = compute_feasibility_map(plot=plot, storey_height_m=3.0)
        fmap_dict = feasibility_to_dict(fmap)
        plot.cached_feasibility_json = fmap_dict
        plot.cached_feasibility_storey_height_m = 3.0
        plot.cached_metrics_updated_at = timezone.now()
        plot.save(update_fields=[
            "cached_feasibility_json",
            "cached_feasibility_storey_height_m",
            "cached_metrics_updated_at",
        ])

    # 3. FSI policy
    fsi_policy = resolve_fsi_policy(
        plot=plot,
        road_width_m=road_width_m,
    )

    # 4. Road edges
    road_edge_indices, _fallback_used = detect_road_edges_with_meta(plot.geom, None)

    # 5. Setback annotations
    setback_distances, road_edges_annotated, envelope_coords = _build_setback_annotations(
        plot, road_edge_indices
    )

    # 6. Build context for AI + response
    zone = infer_zone_from_plot(plot)
    authority = infer_authority()
    plot_area_sqm = fmap_dict.get("plotAreaSqm", 0.0)
    unit_compat = _build_unit_compatibility(fmap_dict)

    context = {
        "plotAreaSqm": plot_area_sqm,
        "roadWidthM": road_width_m,
        "zone": zone,
        "authority": authority,
        "maxHeightM": fmap_dict.get("maxHeightM", 0.0),
        "maxFloors": fmap_dict.get("maxFloors", 0),
        "maxFSI": fmap_dict.get("maxFSI", 0.0),
        "baseFSI": fsi_policy.base_fsi,
        "maxGCPct": fmap_dict.get("maxGCPct", 0.0),
        "maxFeasibleTowers": fmap_dict.get("maxFeasibleTowers", 0),
        "corridorEligible": fsi_policy.corridor_eligible,
        "corridorReason": fsi_policy.notes[0] if fsi_policy.notes else "",
        "unitCompatibility": unit_compat,
        "permissibleBuildingTypes": fmap_dict.get("permissibleBuildingTypes", []),
    }

    # 7. AI scenarios (with fallback)
    ai_scenarios = _generate_ai_scenarios(context)
    if ai_scenarios is None:
        logger.info("Using fallback scenarios for plot %s", plot_id)
        scenarios = _generate_fallback_scenarios(fmap_dict, context)
    else:
        scenarios = ai_scenarios

    # 8. Clamp and add sellable estimates
    for s in scenarios:
        s = _clamp_scenario(s, context)
        sellable = _estimate_sellable(
            plot_area_sqm,
            s.get("estimatedFSI", 1.8),
            s.get("segment", "mid"),
        )
        s.update(sellable)

    # 9. Build premium tiers from FSI policy
    from rules_engine.rules.loader import get_gdcr_config
    gdcr = get_gdcr_config() or {}
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}
    raw_tiers = fsi_cfg.get("premium_tiers") or []
    premium_tiers = []
    for t in raw_tiers:
        premium_tiers.append({
            "fromFSI": float(t.get("from_fsi", 0)),
            "toFSI": float(t.get("resulting_cap", 0)),
            "rate": float(t.get("premium_pct", 0)) / 100.0,
        })

    # 10. Build response
    return {
        "plotSummary": {
            "plotId": plot_id,
            "areaSqm": round(plot_area_sqm, 1),
            "roadWidthM": road_width_m,
            "zone": zone,
            "authority": authority,
            "designation": getattr(plot, "designation", "") or "",
        },
        "constraints": {
            "maxHeightM": context["maxHeightM"],
            "maxFloors": context["maxFloors"],
            "maxFSI": context["maxFSI"],
            "baseFSI": context["baseFSI"],
            "corridorEligible": context["corridorEligible"],
            "corridorReason": context["corridorReason"],
            "maxGroundCoverPct": context["maxGCPct"],
            "maxFeasibleTowers": context["maxFeasibleTowers"],
            "setbacks": {
                "road": _get_road_margin(road_width_m),
                "side": 3.0,
                "rear": 3.0,
            },
            "premiumTiers": premium_tiers,
            "permissibleBuildingTypes": fmap_dict.get("permissibleBuildingTypes", []),
        },
        "unitCompatibility": unit_compat,
        "scenarios": scenarios,
        "plotAnnotations": {
            "roadEdges": road_edges_annotated,
            "setbackDistances": setback_distances,
            "envelopeCoords": envelope_coords,
        },
    }
```

- [ ] **Step 2: Verify module loads**

Run: `cd backend && python -c "from services.plot_exploration_service import explore_plot; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/plot_exploration_service.py
git commit -m "feat: add plot exploration service — orchestrates feasibility + AI scenarios"
```

---

## Task 4: Backend — API Endpoint + URL Route

**Files:**
- Create: `backend/api/views/plot_exploration.py`
- Modify: `backend/api/urls/development.py`

- [ ] **Step 1: Create the API view**

Create `backend/api/views/plot_exploration.py`:

```python
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from services.plot_exploration_service import explore_plot

logger = logging.getLogger(__name__)


class PlotExplorationAPIView(APIView):
    """
    GET /api/development/explore/{plot_id}/

    Returns GDCR constraints, 3 AI-generated development scenarios,
    and plot annotations for the exploration step.
    """

    permission_classes = [AllowAny]

    def get(self, request, plot_id: str, *args, **kwargs):
        try:
            result = explore_plot(plot_id)
        except Exception as exc:
            if "not found" in str(exc).lower() or "does not exist" in str(exc).lower():
                return Response(
                    {"detail": "Plot not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            logger.exception("Plot exploration failed for %s: %s", plot_id, exc)
            return Response(
                {"detail": "Plot exploration failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_200_OK)
```

- [ ] **Step 2: Add URL route**

In `backend/api/urls/development.py`, add the import at the top (after line 19, the feasibility import):

```python
from api.views.plot_exploration import PlotExplorationAPIView
```

And add the URL pattern (before the feasibility path, around line 73):

```python
    path(
        "explore/<str:plot_id>/",
        PlotExplorationAPIView.as_view(),
        name="plot-exploration",
    ),
```

- [ ] **Step 3: Verify URL resolves**

Run: `cd backend && python manage.py show_urls 2>/dev/null | grep explore || python -c "from api.urls.development import urlpatterns; print([u.name for u in urlpatterns])"`
Expected: Output contains `plot-exploration`

- [ ] **Step 4: Commit**

```bash
git add backend/api/views/plot_exploration.py backend/api/urls/development.py
git commit -m "feat: add GET /api/development/explore/{plot_id}/ endpoint"
```

---

## Task 5: Frontend — Types + Service + Query Key + Hook

**Files:**
- Modify: `frontend/src/services/plannerService.ts`
- Modify: `frontend/src/lib/queryKeys.ts`
- Modify: `frontend/src/modules/planner/hooks/usePlannerData.ts`

- [ ] **Step 1: Add TypeScript types and service function**

At the end of `frontend/src/services/plannerService.ts` (before the final empty line), add:

```typescript
// ── Plot Exploration (Step 1) ─────────────────────────────────────────────────

export interface ExplorationScenario {
  id: string;
  label: string;
  description: string;
  towers: number;
  floors: number;
  buildingType: number;
  segment: string;
  unitMix: string[];
  unitsPerCore: number;
  estimatedFSI: number;
  estimatedSellableAreaSqm: number;
  sellablePerSqYd: number;
  estimatedTotalUnits: number;
  tradeoffNote: string;
}

export interface PremiumTier {
  fromFSI: number;
  toFSI: number;
  rate: number;
}

export interface SetbackAnnotation {
  edgeIndex: number;
  distanceM: number;
  type: "road" | "side" | "rear";
}

export interface RoadEdgeAnnotation {
  edgeIndex: number;
  roadWidthM: number;
  setbackM: number;
}

export interface ExplorationConstraints {
  maxHeightM: number;
  maxFloors: number;
  maxFSI: number;
  baseFSI: number;
  corridorEligible: boolean;
  corridorReason: string;
  maxGroundCoverPct: number;
  maxFeasibleTowers: number;
  setbacks: { road: number; side: number; rear: number };
  premiumTiers: PremiumTier[];
  permissibleBuildingTypes: BuildingTypeOption[];
}

export interface PlotAnnotations {
  roadEdges: RoadEdgeAnnotation[];
  setbackDistances: SetbackAnnotation[];
  envelopeCoords: number[][];
}

export interface ExplorationResponse {
  plotSummary: {
    plotId: string;
    areaSqm: number;
    roadWidthM: number;
    zone: string;
    authority: string;
    designation: string;
  };
  constraints: ExplorationConstraints;
  unitCompatibility: Record<string, boolean>;
  scenarios: ExplorationScenario[];
  plotAnnotations: PlotAnnotations;
}

export async function getPlotExploration(
  plotId: string,
): Promise<ExplorationResponse> {
  return httpRequest<ExplorationResponse>(
    `/api/development/explore/${encodeURIComponent(plotId)}/`,
    { method: "GET" },
  );
}
```

- [ ] **Step 2: Add query key factory**

In `frontend/src/lib/queryKeys.ts`, add inside the `planner` object (after the `feasibility` key, around line 30):

```typescript
    exploration: (plotId: string | number) =>
      ["planner", "exploration", { plotId }] as const,
```

And add it to the `QueryKey` union type:

```typescript
  | typeof queryKeys.planner.exploration
```

- [ ] **Step 3: Add usePlotExploration hook**

In `frontend/src/modules/planner/hooks/usePlannerData.ts`, add the import for `getPlotExploration` and `ExplorationResponse` at the top (in the existing import block from `plannerService`):

```typescript
  getPlotExploration,
  type ExplorationResponse,
```

Then add the hook (after `useFeasibility`):

```typescript
export function usePlotExploration(plotId: string | null) {
  return useQuery<ExplorationResponse | null>({
    queryKey: plotId
      ? queryKeys.planner.exploration(plotId)
      : ["planner", "exploration", "none"],
    queryFn: () => (plotId ? getPlotExploration(plotId) : Promise.resolve(null)),
    enabled: Boolean(plotId),
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to the new types/functions.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/plannerService.ts frontend/src/lib/queryKeys.ts frontend/src/modules/planner/hooks/usePlannerData.ts
git commit -m "feat: add ExplorationResponse types, service function, and usePlotExploration hook"
```

---

## Task 6: Frontend — Planner Store + Step Navigation Updates

**Files:**
- Modify: `frontend/src/state/plannerStore.ts`
- Modify: `frontend/src/modules/planner/components/StepNavigation.tsx`

- [ ] **Step 1: Update PlanningStep type and store**

In `frontend/src/state/plannerStore.ts`:

1. Change `PlanningStep` type (line 26):
```typescript
export type PlanningStep = "explore" | "site" | "floor";
```

2. Add `selectedScenario` to the `PlannerState` type (after line 86, `selectedUnit`):
```typescript
  selectedScenario: import("@/services/plannerService").ExplorationScenario | null;
```

3. Add `setSelectedScenario` to `PlannerActions` (after line 105, `setSelectedUnit`):
```typescript
  setSelectedScenario: (scenario: import("@/services/plannerService").ExplorationScenario | null) => void;
```

4. Change default `planningStep` from `"site"` to `"explore"` (line 152):
```typescript
  planningStep: "explore",
```

5. Add `selectedScenario: null` to initial state (after line 155, `selectedUnit: null`):
```typescript
  selectedScenario: null,
```

6. Add `setSelectedScenario` action (after line 235, `setSelectedUnit`):
```typescript
  setSelectedScenario: (scenario) => set({ selectedScenario: scenario }),
```

7. Update `resetForPlot` to reset to `"explore"` and clear scenario (line 226-230):
```typescript
      planningStep: "explore",
      ...
      selectedScenario: null,
```

- [ ] **Step 2: Update StepNavigation**

Replace the entire contents of `frontend/src/modules/planner/components/StepNavigation.tsx`:

```tsx
"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { PlanningStep } from "@/state/plannerStore";

export function StepNavigation() {
  const planningStep = usePlannerStore((s) => s.planningStep);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);
  const selectedScenario = usePlannerStore((s) => s.selectedScenario);

  const steps: { id: PlanningStep; label: string }[] = [
    { id: "explore", label: "Plot Exploration" },
    { id: "site", label: "Site Plan" },
    { id: "floor", label: "AI Floor Plan" },
  ];

  return (
    <nav className="flex items-center gap-1" aria-label="Planning steps">
      {steps.map(({ id, label }, idx) => {
        const active = planningStep === id;
        const disabled =
          (id === "site" && selectedScenario === null) ||
          (id === "floor" && selectedTowerIndex === null);

        return (
          <div key={id} className="flex items-center">
            <button
              type="button"
              onClick={() => !disabled && setPlanningStep(id)}
              disabled={disabled}
              className={`group flex items-center gap-2 px-4 py-2 transition-all duration-300 ${
                active
                  ? "text-orange-600"
                  : disabled
                    ? "cursor-not-allowed opacity-30 text-neutral-400"
                    : "text-neutral-400 hover:text-neutral-900"
              }`}
            >
              <span className={`font-heading text-sm font-bold tracking-tight ${active ? "" : "font-medium"}`}>
                {label}
              </span>
              {active && (
                <div className="h-1.5 w-1.5 rounded-full bg-orange-600 shadow-[0_0_8px_rgba(234,88,12,0.6)] animate-pulse" />
              )}
            </button>
            {idx < steps.length - 1 && (
              <div className="h-4 w-px bg-neutral-100 mx-1" />
            )}
          </div>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to these changes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/state/plannerStore.ts frontend/src/modules/planner/components/StepNavigation.tsx
git commit -m "feat: add 'explore' step to planner state and navigation"
```

---

## Task 7: Frontend — ConstraintsDashboard Component

**Files:**
- Create: `frontend/src/modules/planner/components/ConstraintsDashboard.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/modules/planner/components/ConstraintsDashboard.tsx`:

```tsx
"use client";

import type { ExplorationConstraints } from "@/services/plannerService";

interface Props {
  constraints: ExplorationConstraints | null;
  plotSummary: { areaSqm: number; roadWidthM: number; zone: string; authority: string; designation: string } | null;
  isLoading: boolean;
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex justify-between">
          <div className="h-4 w-24 rounded bg-neutral-200" />
          <div className="h-4 w-16 rounded bg-neutral-200" />
        </div>
      ))}
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-neutral-500">{label}</span>
      <span className={`text-xs font-semibold ${highlight ? "text-orange-600" : "text-neutral-900"}`}>
        {value}
      </span>
    </div>
  );
}

export function ConstraintsDashboard({ constraints, plotSummary, isLoading }: Props) {
  if (isLoading || !constraints || !plotSummary) return <Skeleton />;

  const c = constraints;
  const p = plotSummary;

  return (
    <div className="space-y-4">
      <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
        GDCR Constraints
      </h3>

      {/* Plot info */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row label="Plot Area" value={`${p.areaSqm.toFixed(0)} sqm (${(p.areaSqm / 0.8361).toFixed(0)} sq.yd)`} />
        <Row label="Road Width" value={`${p.roadWidthM}m`} />
        <Row label="Zone" value={p.zone} />
        <Row label="Authority" value={p.authority} />
      </div>

      {/* Regulatory limits */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row label="Max Height" value={`${c.maxHeightM}m`} />
        <Row label="Max Floors" value={c.maxFloors} />
        <Row label="Max FSI" value={c.maxFSI} highlight />
        <Row label="Base FSI" value={c.baseFSI} />
        <Row label="Ground Cover" value={`${c.maxGroundCoverPct}%`} />
        <Row label="Max Towers" value={c.maxFeasibleTowers} />
      </div>

      {/* Corridor */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row
          label="Corridor Eligible"
          value={c.corridorEligible ? "Yes" : "No"}
          highlight={c.corridorEligible}
        />
        <p className="text-[10px] text-neutral-400 mt-1">{c.corridorReason}</p>
      </div>

      {/* Setbacks */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row label="Road Setback" value={`${c.setbacks.road}m`} />
        <Row label="Side Setback" value={`${c.setbacks.side}m`} />
        <Row label="Rear Setback" value={`${c.setbacks.rear}m`} />
      </div>

      {/* Premium tiers */}
      {c.premiumTiers.length > 0 && (
        <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3">
          <p className="text-[10px] font-semibold text-neutral-500 mb-2">Premium FSI Tiers</p>
          <div className="space-y-1">
            {c.premiumTiers.map((tier, i) => (
              <div key={i} className="flex justify-between text-[10px]">
                <span className="text-neutral-500">FSI {tier.fromFSI} → {tier.toFSI}</span>
                <span className="font-semibold text-neutral-700">{(tier.rate * 100).toFixed(0)}% premium</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -5`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/planner/components/ConstraintsDashboard.tsx
git commit -m "feat: add ConstraintsDashboard component for plot exploration"
```

---

## Task 8: Frontend — ScenarioCards Component

**Files:**
- Create: `frontend/src/modules/planner/components/ScenarioCards.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/modules/planner/components/ScenarioCards.tsx`:

```tsx
"use client";

import { useState, useCallback } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import type { ExplorationScenario, ExplorationConstraints } from "@/services/plannerService";

interface Props {
  scenarios: ExplorationScenario[];
  constraints: ExplorationConstraints | null;
  unitCompatibility: Record<string, boolean>;
  isLoading: boolean;
  onProceed: (scenario: ExplorationScenario) => void;
}

function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-neutral-200 p-4 space-y-3">
      <div className="h-5 w-32 rounded bg-neutral-200" />
      <div className="h-3 w-48 rounded bg-neutral-100" />
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-8 rounded bg-neutral-100" />
        ))}
      </div>
    </div>
  );
}

function MetricBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-neutral-50 px-2 py-1.5 text-center">
      <div className="text-xs font-bold text-neutral-900">{value}</div>
      <div className="text-[10px] text-neutral-400">{label}</div>
    </div>
  );
}

const SEGMENT_OPTIONS = ["budget", "mid", "premium", "luxury"];
const UNITS_PER_CORE_OPTIONS = [2, 4, 6];
const UNIT_TYPES = ["1BHK", "2BHK", "3BHK", "4BHK"];

export function ScenarioCards({ scenarios, constraints, unitCompatibility, isLoading, onProceed }: Props) {
  const selectedScenario = usePlannerStore((s) => s.selectedScenario);
  const setSelectedScenario = usePlannerStore((s) => s.setSelectedScenario);

  // Local editable copy of the selected scenario
  const [editedScenario, setEditedScenario] = useState<ExplorationScenario | null>(null);

  const handleSelect = useCallback((scenario: ExplorationScenario) => {
    setSelectedScenario(scenario);
    setEditedScenario({ ...scenario });
  }, [setSelectedScenario]);

  const handleEdit = useCallback((field: string, value: unknown) => {
    setEditedScenario((prev) => prev ? { ...prev, [field]: value } : null);
  }, []);

  const handleProceed = useCallback(() => {
    if (editedScenario) {
      setSelectedScenario(editedScenario);
      onProceed(editedScenario);
    }
  }, [editedScenario, setSelectedScenario, onProceed]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
          Generating Scenarios...
        </h3>
        {Array.from({ length: 3 }).map((_, i) => <CardSkeleton key={i} />)}
      </div>
    );
  }

  if (!scenarios.length) return null;

  const isSelected = (s: ExplorationScenario) => selectedScenario?.id === s.id;

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
        Development Scenarios
      </h3>

      {scenarios.map((scenario) => (
        <button
          key={scenario.id}
          type="button"
          onClick={() => handleSelect(scenario)}
          className={`w-full text-left rounded-xl border-2 p-4 transition-all ${
            isSelected(scenario)
              ? "border-orange-500 bg-orange-50/50 shadow-md"
              : "border-neutral-200 bg-white hover:border-neutral-300 hover:shadow-sm"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-bold text-neutral-900">{scenario.label}</h4>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
              scenario.id === "high_density" ? "bg-red-100 text-red-700" :
              scenario.id === "balanced" ? "bg-blue-100 text-blue-700" :
              "bg-purple-100 text-purple-700"
            }`}>
              {scenario.segment}
            </span>
          </div>
          <p className="text-xs text-neutral-500 mb-3">{scenario.description}</p>

          <div className="grid grid-cols-3 gap-1.5">
            <MetricBox label="Towers" value={scenario.towers} />
            <MetricBox label="Floors" value={scenario.floors} />
            <MetricBox label="Est. FSI" value={scenario.estimatedFSI.toFixed(1)} />
            <MetricBox label="Sellable" value={`${(scenario.estimatedSellableAreaSqm / 1000).toFixed(1)}k sqm`} />
            <MetricBox label="Units" value={scenario.estimatedTotalUnits} />
            <MetricBox label="Sell/yd" value={scenario.sellablePerSqYd.toFixed(0)} />
          </div>

          <p className="text-[10px] italic text-neutral-400 mt-2">{scenario.tradeoffNote}</p>
        </button>
      ))}

      {/* Parameter Editor — shown when a scenario is selected */}
      {editedScenario && (
        <div className="rounded-xl border border-orange-200 bg-orange-50/30 p-4 space-y-3">
          <h4 className="text-xs font-bold text-neutral-700">Customize Parameters</h4>

          <div className="grid grid-cols-2 gap-3">
            {/* Towers */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Towers</label>
              <input
                type="number"
                min={1}
                max={constraints?.maxFeasibleTowers ?? 10}
                value={editedScenario.towers}
                onChange={(e) => handleEdit("towers", parseInt(e.target.value) || 1)}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              />
            </div>

            {/* Floors */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Floors</label>
              <input
                type="number"
                min={1}
                max={constraints?.maxFloors ?? 30}
                value={editedScenario.floors}
                onChange={(e) => handleEdit("floors", parseInt(e.target.value) || 1)}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              />
            </div>

            {/* Segment */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Segment</label>
              <select
                value={editedScenario.segment}
                onChange={(e) => handleEdit("segment", e.target.value)}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              >
                {SEGMENT_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
              </select>
            </div>

            {/* Units per core */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Units / Core</label>
              <select
                value={editedScenario.unitsPerCore}
                onChange={(e) => handleEdit("unitsPerCore", parseInt(e.target.value))}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              >
                {UNITS_PER_CORE_OPTIONS.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Unit mix checkboxes */}
          <div>
            <label className="text-[10px] font-medium text-neutral-500">Unit Mix</label>
            <div className="mt-1 flex flex-wrap gap-2">
              {UNIT_TYPES.map((ut) => {
                const compatible = unitCompatibility[ut] !== false;
                const checked = editedScenario.unitMix.includes(ut);
                return (
                  <label
                    key={ut}
                    className={`flex items-center gap-1 text-xs ${!compatible ? "opacity-40" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!compatible}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...editedScenario.unitMix, ut]
                          : editedScenario.unitMix.filter((u) => u !== ut);
                        handleEdit("unitMix", next);
                      }}
                      className="rounded border-neutral-300"
                    />
                    {ut}
                  </label>
                );
              })}
            </div>
          </div>

          {/* Proceed button */}
          <button
            type="button"
            onClick={handleProceed}
            className="w-full rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-orange-700 transition-colors"
          >
            Proceed to Site Plan →
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -5`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/planner/components/ScenarioCards.tsx
git commit -m "feat: add ScenarioCards component with select, edit, and proceed"
```

---

## Task 9: Frontend — PlotExplorationView Component

**Files:**
- Create: `frontend/src/modules/planner/components/PlotExplorationView.tsx`

- [ ] **Step 1: Create the main exploration view**

Create `frontend/src/modules/planner/components/PlotExplorationView.tsx`:

```tsx
"use client";

import { useCallback } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { usePlotExploration } from "@/modules/planner/hooks/usePlannerData";
import { ConstraintsDashboard } from "./ConstraintsDashboard";
import { ScenarioCards } from "./ScenarioCards";
import type { ExplorationScenario } from "@/services/plannerService";
import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { WholeTpMap } from "@/modules/plots/components/WholeTpMap";

export function PlotExplorationView() {
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const setInputs = usePlannerStore((s) => s.setInputs);

  const { data: exploration, isLoading, error } = usePlotExploration(selectedPlotId);
  const { data: plots = [] } = usePlotsQuery({
    tpScheme: locationPreference.tpId,
    city: locationPreference.districtName,
  });

  const handleProceed = useCallback((scenario: ExplorationScenario) => {
    // Pre-fill site plan inputs from selected scenario
    setInputs({
      buildingType: scenario.buildingType,
      floors: scenario.floors,
      segment: scenario.segment,
      unitsPerCore: scenario.unitsPerCore,
      nBuildings: scenario.towers,
      unitMix: scenario.unitMix,
    });
    setPlanningStep("site");
  }, [setInputs, setPlanningStep]);

  return (
    <div className="flex h-full gap-3">
      {/* Left panel: TP Map with plot highlighted */}
      <div className="flex-[3] min-h-0 rounded-xl border border-neutral-200 bg-white overflow-hidden">
        {plots.length > 0 ? (
          <WholeTpMap
            plots={plots}
            width={800}
            height={600}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-neutral-400">
            Loading map...
          </div>
        )}
      </div>

      {/* Right panel: Constraints + Scenarios */}
      <div className="flex-[2] min-h-0 overflow-auto space-y-4 pr-1">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load plot analysis. {(error as Error).message}
          </div>
        ) : (
          <>
            <ConstraintsDashboard
              constraints={exploration?.constraints ?? null}
              plotSummary={exploration?.plotSummary ?? null}
              isLoading={isLoading}
            />
            <ScenarioCards
              scenarios={exploration?.scenarios ?? []}
              constraints={exploration?.constraints ?? null}
              unitCompatibility={exploration?.unitCompatibility ?? {}}
              isLoading={isLoading}
              onProceed={handleProceed}
            />
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -5`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/planner/components/PlotExplorationView.tsx
git commit -m "feat: add PlotExplorationView — split map + constraints + scenario cards"
```

---

## Task 10: Frontend — Wire Exploration into Planner Page

**Files:**
- Modify: `frontend/src/app/(protected)/planner/page.tsx`

- [ ] **Step 1: Import PlotExplorationView**

At the top of `frontend/src/app/(protected)/planner/page.tsx`, add the import (after the FloorPlanningView import, line 9):

```typescript
import { PlotExplorationView } from "@/modules/planner/components/PlotExplorationView";
```

- [ ] **Step 2: Add explore step routing**

In the main content section where `planningStep` routing happens (lines 134-143), replace:

```tsx
            {planningStep === "site" ? (
              <PlannerCanvas
                geometryModel={geometryModel ?? plotOnlyModel}
                isLoading={isPlanLoading}
                loadingProgress={loadingProgress}
              />
            ) : (
              <FloorPlanningView geometryModel={geometryModel} />
            )}
```

With:

```tsx
            {planningStep === "explore" ? (
              <PlotExplorationView />
            ) : planningStep === "site" ? (
              <PlannerCanvas
                geometryModel={geometryModel ?? plotOnlyModel}
                isLoading={isPlanLoading}
                loadingProgress={loadingProgress}
              />
            ) : (
              <FloorPlanningView geometryModel={geometryModel} />
            )}
```

- [ ] **Step 3: Hide sidebar controls during explore step**

The left sidebar (LayerControl, PlanningMetricsPanel) is not needed during exploration. Wrap the aside in a condition (around line 128):

Change:
```tsx
          <aside className="flex w-56 shrink-0 flex-col gap-3 overflow-auto">
```

To:
```tsx
          {planningStep !== "explore" && (
          <aside className="flex w-56 shrink-0 flex-col gap-3 overflow-auto">
```

And add the closing `)}` after the `</aside>` closing tag.

- [ ] **Step 4: Verify TypeScript compiles and page renders**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -10`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(protected\)/planner/page.tsx
git commit -m "feat: wire PlotExplorationView into planner page routing"
```

---

## Task 11: Integration Test — End-to-End Smoke Test

- [ ] **Step 1: Test backend endpoint**

Run: `cd backend && python manage.py shell -c "
from services.plot_exploration_service import explore_plot
try:
    result = explore_plot('FP82')
    print('plotSummary:', result['plotSummary']['plotId'], result['plotSummary']['areaSqm'])
    print('constraints keys:', list(result['constraints'].keys()))
    print('scenarios:', len(result['scenarios']))
    for s in result['scenarios']:
        print(f'  {s[\"id\"]}: towers={s[\"towers\"]} floors={s[\"floors\"]} fsi={s.get(\"estimatedFSI\", \"?\")}')
    print('annotations:', list(result['plotAnnotations'].keys()))
    print('SUCCESS')
except Exception as e:
    print(f'FAILED: {e}')
"`

Expected: `SUCCESS` with 3 scenarios printed (either AI or fallback).

- [ ] **Step 2: Test frontend compiles clean**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | tail -3`
Expected: No errors.

- [ ] **Step 3: Start dev servers and manual test**

1. Start backend: `cd backend && python manage.py runserver`
2. Start frontend: `cd frontend && npm run dev`
3. Open browser → go to planner → select a plot
4. Verify: "Plot Exploration" step is active, constraints dashboard loads, scenario cards appear (or skeletons while loading)
5. Select a scenario → customize → click "Proceed to Site Plan" → verify it transitions to site step with inputs pre-filled

- [ ] **Step 4: Commit any fixes**

If any issues found, fix and commit with: `git commit -m "fix: address integration issues in plot exploration"`
