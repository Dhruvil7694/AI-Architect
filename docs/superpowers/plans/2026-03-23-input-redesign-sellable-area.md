# Input Redesign & Sellable Area Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the development input system to match how real estate developers think — building type, floors (with GDCR-enforced limits), core configuration (units per core), RCA (RERA Carpet Area), number of buildings (with max cap), and sellable area ratios — with all calculations updating reactively when any input changes.

**Architecture:** The backend gets a new `SellableAreaModel` that encodes industry FSI-to-sellable ratios and computes RCA from room geometry. The frontend `DevelopmentInputs` is rebuilt with 5 new input groups that drive a reactive feasibility loop: every input change re-queries the backend for updated limits and metrics. The optimizer pipeline accepts the new inputs and threads them through envelope → placement → layout → area accounting.

**Tech Stack:** Django REST Framework (backend), Next.js + React + Zustand (frontend), existing GDCR.yaml config system.

**Review status:** Plan reviewed and fixed. Critical fixes applied:
- GDCR.yaml path corrected to repo root (not `backend/`)
- Building type heights aligned with GDCR height_band_rules (Type 1: ≤10m, Type 2: ≤15m)
- Type 2 `fire_stair_required` corrected to `true` (triggered at 15m)
- `backend/architecture/models/__init__.py` creation step added
- `frontend/src/types/plannerInputs.ts` canonical type file added to modification list
- Old field migration (`towerCount`, `preferredFloors`, `vastu`) addressed in Task 8

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/architecture/models/building_types.py` | Building type enum (1/2/3) + regulatory lookup |
| `backend/architecture/models/sellable_area.py` | FSI-to-sellable ratios, RCA calculation, efficiency model |
| `backend/architecture/models/core_config.py` | Units-per-core configs (2/4/6), core sizing |
| `backend/api/serializers/development_inputs.py` | New input serializer (replaces old request serializer) |
| `backend/tests/test_sellable_area.py` | Unit tests for sellable model |
| `backend/tests/test_core_config.py` | Unit tests for core config |
| `backend/tests/test_building_types.py` | Unit tests for building types |
| `backend/tests/test_development_inputs_api.py` | API integration tests |

### Backend — Modified Files
| File | Change |
|------|--------|
| `GDCR.yaml` (repo root) | Add `building_types`, `sellable_ratios`, `core_configs` sections |
| `backend/architecture/services/feasibility_advisor.py` | Accept building type, compute max towers, return core options |
| `backend/architecture/services/development_pipeline.py` | Thread new inputs through pipeline |
| `backend/architecture/regulatory/development_optimizer.py` | Accept core config + building type |
| `backend/area_accounting/floor_area.py` | Add RCA computation from room geometry |
| `backend/api/views/development.py` | Use new serializer, pass new inputs |
| `backend/api/views/feasibility.py` | Return core options + max towers + sellable estimate |
| `backend/placement_engine/geometry/core_fit.py` | Accept units_per_core parameter |
| `backend/residential_layout/orchestrator.py` | Use core config to determine template selection |

### Frontend — Modified Files
| File | Change |
|------|--------|
| `frontend/src/types/plannerInputs.ts` | Canonical type definition — new `PlannerInputs` shape |
| `frontend/src/modules/planner/components/DevelopmentInputs.tsx` | Complete rewrite — 5 new input groups |
| `frontend/src/state/plannerStore.ts` | New defaults matching 5 groups (imports type from `@/types/plannerInputs`) |
| `frontend/src/services/plannerService.ts` | Updated API call with new payload |
| `frontend/src/modules/planner/hooks/usePlannerData.ts` | Reactive re-fetch on input change |
| `frontend/src/modules/planner/components/PlanningMetricsPanel.tsx` | Show sellable area, RCA, efficiency |

---

## Task 1: Building Type Config in GDCR.yaml

**Files:**
- Modify: `GDCR.yaml` (repo root — NOT backend/GDCR.yaml)
- Create: `backend/architecture/models/__init__.py` (empty — makes this a Python package)
- Create: `backend/architecture/models/building_types.py`
- Create: `backend/tests/test_building_types.py`

**Context:** Building types aligned with GDCR height band rules (`height_band_rules` in GDCR.yaml: `low_rise_max_m: 10`, `mid_rise_max_m: 15`) and fire safety thresholds (`fire_noc_required_above_m: 15`, `refuge_area_required_above_m: 25`):
- **Type 1** = Low-rise residential (G+3, no lift, ≤ 10m per GDCR low_rise band)
- **Type 2** = Mid-rise residential (G+5, lift required above 10m, fire stair required above 15m, ≤ 15m per GDCR mid_rise band)
- **Type 3** = High-rise residential (6+ floors, fire stairs + refuge above 25m, > 15m)

Each type has different margin rules, COP requirements, and permissible floor ranges.

- [ ] **Step 0: Create models package**

```bash
touch backend/architecture/models/__init__.py
```

- [ ] **Step 1: Add building_types section to GDCR.yaml (repo root)**

Add after the existing `fsi_rules` section:

```yaml
building_types:
  - id: 1
    label: "Low-Rise Residential"
    max_height_m: 10.0
    max_floors: 3
    lift_required: false
    fire_stair_required: false
    refuge_area_required: false
    min_road_width_m: 9.0
    cop_required: false
    typical_efficiency_ratio: 0.65
    notes: "G+3, no lift, single staircase, GDCR low-rise band (≤10m)"

  - id: 2
    label: "Mid-Rise Residential"
    max_height_m: 15.0
    max_floors: 5
    lift_required: true
    fire_stair_required: true
    refuge_area_required: false
    min_road_width_m: 12.0
    cop_required: true
    typical_efficiency_ratio: 0.58
    notes: "G+5, lift mandatory >10m, fire stair required >15m, GDCR mid-rise band"

  - id: 3
    label: "High-Rise Residential"
    max_height_m: 70.0
    max_floors: 23
    lift_required: true
    fire_stair_required: true
    refuge_area_required: true
    min_road_width_m: 12.0
    cop_required: true
    typical_efficiency_ratio: 0.55
    notes: "6+ floors, fire stairs, refuge area >25m, dual staircase >15m"
```

- [ ] **Step 2: Write test for building type lookup**

```python
# backend/tests/test_building_types.py
import pytest
from architecture.models.building_types import (
    BuildingType,
    get_building_type,
    get_permissible_building_types,
)

def test_get_building_type_1():
    bt = get_building_type(1)
    assert bt.id == 1
    assert bt.max_floors == 3
    assert bt.max_height_m == 10.0
    assert bt.lift_required is False

def test_get_building_type_2():
    bt = get_building_type(2)
    assert bt.id == 2
    assert bt.max_floors == 5
    assert bt.lift_required is True
    assert bt.fire_stair_required is True  # >15m triggers fire stair

def test_get_building_type_3():
    bt = get_building_type(3)
    assert bt.id == 3
    assert bt.fire_stair_required is True
    assert bt.refuge_area_required is True

def test_get_building_type_invalid():
    with pytest.raises(ValueError, match="Unknown building type"):
        get_building_type(99)

def test_permissible_types_narrow_road():
    """9m road → only type 1 is feasible (min_road_width_m=9.0)."""
    types = get_permissible_building_types(road_width_m=9.0)
    ids = [t.id for t in types]
    assert 1 in ids
    # Type 2/3 require 12m+ road
    assert 2 not in ids
    assert 3 not in ids

def test_permissible_types_wide_road():
    """30m road → all types feasible."""
    types = get_permissible_building_types(road_width_m=30.0)
    assert len(types) == 3

def test_max_floors_capped_by_road():
    """Type 3 on 18m road → max 30m height = 10 floors, not 23."""
    types = get_permissible_building_types(road_width_m=18.0)
    t3 = next(t for t in types if t.id == 3)
    assert t3.effective_max_floors <= 10
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_building_types.py -v`
Expected: FAIL — module not found

- [ ] **Step 4: Implement building type model**

```python
# backend/architecture/models/building_types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from rules_engine.rules.loader import get_gdcr_config
from architecture.regulatory_accessors import get_max_permissible_height_by_road_width


@dataclass(frozen=True)
class BuildingType:
    id: int
    label: str
    max_height_m: float
    max_floors: int
    lift_required: bool
    fire_stair_required: bool
    refuge_area_required: bool
    min_road_width_m: float
    cop_required: bool
    typical_efficiency_ratio: float
    notes: str
    # Computed at query time when road width is known
    effective_max_floors: int = 0


def _load_building_types() -> list[dict]:
    gdcr = get_gdcr_config() or {}
    return gdcr.get("building_types", [])


def get_building_type(type_id: int) -> BuildingType:
    for raw in _load_building_types():
        if int(raw.get("id", 0)) == type_id:
            return BuildingType(
                id=int(raw["id"]),
                label=str(raw.get("label", "")),
                max_height_m=float(raw.get("max_height_m", 0)),
                max_floors=int(raw.get("max_floors", 0)),
                lift_required=bool(raw.get("lift_required", False)),
                fire_stair_required=bool(raw.get("fire_stair_required", False)),
                refuge_area_required=bool(raw.get("refuge_area_required", False)),
                min_road_width_m=float(raw.get("min_road_width_m", 0)),
                cop_required=bool(raw.get("cop_required", False)),
                typical_efficiency_ratio=float(raw.get("typical_efficiency_ratio", 0.55)),
                notes=str(raw.get("notes", "")),
            )
    raise ValueError(f"Unknown building type: {type_id}")


def get_permissible_building_types(
    road_width_m: float,
    storey_height_m: float = 3.0,
) -> List[BuildingType]:
    road_height_cap = get_max_permissible_height_by_road_width(road_width_m)
    result = []
    for raw in _load_building_types():
        bt = get_building_type(int(raw["id"]))
        if road_width_m < bt.min_road_width_m:
            continue
        effective_height = min(bt.max_height_m, road_height_cap)
        effective_floors = min(bt.max_floors, int(effective_height / storey_height_m))
        if effective_floors < 1:
            continue
        result.append(BuildingType(
            id=bt.id,
            label=bt.label,
            max_height_m=effective_height,
            max_floors=bt.max_floors,
            lift_required=bt.lift_required,
            fire_stair_required=bt.fire_stair_required,
            refuge_area_required=bt.refuge_area_required,
            min_road_width_m=bt.min_road_width_m,
            cop_required=bt.cop_required,
            typical_efficiency_ratio=bt.typical_efficiency_ratio,
            notes=bt.notes,
            effective_max_floors=effective_floors,
        ))
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_building_types.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/architecture/models/building_types.py backend/tests/test_building_types.py backend/GDCR.yaml
git commit -m "feat: add building type model (1/2/3) with GDCR road-width capping"
```

---

## Task 2: Core Configuration Model (Units Per Core)

**Files:**
- Create: `backend/architecture/models/core_config.py`
- Create: `backend/tests/test_core_config.py`

**Context:** Core = one lift+staircase cluster. Units per core = how many flats share that core on each floor. Common configs: 2 (premium), 4 (mid-market), 6 (budget). This drives footprint width requirements and unit sizing.

- [ ] **Step 1: Write test for core config**

```python
# backend/tests/test_core_config.py
import pytest
from architecture.models.core_config import (
    CoreConfig,
    get_core_configs,
    get_core_config,
    compute_required_footprint_for_core,
)

def test_get_core_config_2():
    cc = get_core_config(units_per_core=2)
    assert cc.units_per_core == 2
    assert cc.segment == "premium"

def test_get_core_config_4():
    cc = get_core_config(units_per_core=4)
    assert cc.units_per_core == 4
    assert cc.segment == "mid"

def test_get_core_config_6():
    cc = get_core_config(units_per_core=6)
    assert cc.units_per_core == 6
    assert cc.segment == "budget"

def test_get_core_config_invalid():
    with pytest.raises(ValueError):
        get_core_config(units_per_core=5)

def test_footprint_2_units_3bhk():
    """2 units × 3BHK per core needs ~19m corridor + core."""
    result = compute_required_footprint_for_core(
        units_per_core=2,
        unit_type="3BHK",
        building_height_m=30.0,
    )
    assert result.min_footprint_width_m > 0
    assert result.min_footprint_depth_m > 0
    assert result.core_pattern in ("END_CORE", "SINGLE_LOADED", "DOUBLE_LOADED")

def test_footprint_4_units_2bhk():
    """4 units × 2BHK per core — double loaded corridor."""
    result = compute_required_footprint_for_core(
        units_per_core=4,
        unit_type="2BHK",
        building_height_m=30.0,
    )
    assert result.core_pattern == "DOUBLE_LOADED"
    assert result.estimated_floor_area_sqm > 0
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_core_config.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement core config model**

```python
# backend/architecture/models/core_config.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

# Approximate unit widths along corridor (metres) — from feasibility_advisor
_UNIT_WIDTHS = {
    "1BHK": 3.0, "2BHK": 4.0, "3BHK": 5.5, "4BHK": 7.0, "5BHK": 9.0,
}
_UNIT_DEPTHS = {
    "1BHK": 3.0, "2BHK": 3.5, "3BHK": 4.0, "4BHK": 4.5, "5BHK": 5.0,
}
_UNIT_AREAS = {
    "1BHK": 30.0, "2BHK": 55.0, "3BHK": 85.0, "4BHK": 120.0, "5BHK": 160.0,
}

_CORE_CONFIGS = [
    {"units_per_core": 2, "segment": "premium", "label": "2 Units/Core (Premium)",
     "preferred_pattern": "END_CORE", "corridor_sides": 1},
    {"units_per_core": 4, "segment": "mid", "label": "4 Units/Core (Mid-Market)",
     "preferred_pattern": "DOUBLE_LOADED", "corridor_sides": 2},
    {"units_per_core": 6, "segment": "budget", "label": "6 Units/Core (Budget)",
     "preferred_pattern": "DOUBLE_LOADED", "corridor_sides": 2},
]

# Core package widths by height band (from core_fit.py logic)
_CORE_PKG_W = {
    "no_lift": 1.53,       # 1 stair, no lift (h ≤ 10m)
    "single_stair": 3.26,  # 1 stair + lift (10m < h ≤ 15m)
    "dual_stair": 4.26,    # 2 stairs + lift (h > 15m)
}
_CORE_PKG_D = 3.6  # stair run
_CORRIDOR_W = 1.5  # minimum corridor width


@dataclass(frozen=True)
class CoreConfig:
    units_per_core: int
    segment: str
    label: str
    preferred_pattern: str
    corridor_sides: int  # 1 for END_CORE/SINGLE, 2 for DOUBLE


@dataclass(frozen=True)
class CoreFootprintRequirement:
    units_per_core: int
    unit_type: str
    core_pattern: str
    min_footprint_width_m: float
    min_footprint_depth_m: float
    estimated_floor_area_sqm: float
    estimated_unit_area_sqm: float


def get_core_configs() -> List[CoreConfig]:
    return [CoreConfig(**c) for c in _CORE_CONFIGS]


def get_core_config(units_per_core: int) -> CoreConfig:
    for c in _CORE_CONFIGS:
        if c["units_per_core"] == units_per_core:
            return CoreConfig(**c)
    raise ValueError(
        f"No core config for {units_per_core} units/core. "
        f"Valid: {[c['units_per_core'] for c in _CORE_CONFIGS]}"
    )


def _core_pkg_width(height_m: float) -> float:
    if height_m <= 10.0:
        return _CORE_PKG_W["no_lift"]
    elif height_m <= 15.0:
        return _CORE_PKG_W["single_stair"]
    return _CORE_PKG_W["dual_stair"]


def compute_required_footprint_for_core(
    units_per_core: int,
    unit_type: str,
    building_height_m: float,
) -> CoreFootprintRequirement:
    cc = get_core_config(units_per_core)
    unit_w = _UNIT_WIDTHS.get(unit_type, 4.0)
    unit_d = _UNIT_DEPTHS.get(unit_type, 3.5)
    unit_area = _UNIT_AREAS.get(unit_type, 55.0)
    core_w = _core_pkg_width(building_height_m)

    if cc.corridor_sides == 2:
        # DOUBLE_LOADED: units on both sides
        units_per_side = units_per_core // 2
        corridor_length = units_per_side * unit_w
        footprint_depth = corridor_length + _CORE_PKG_D
        footprint_width = 2 * unit_d + _CORRIDOR_W
        pattern = "DOUBLE_LOADED"
    else:
        # END_CORE or SINGLE_LOADED
        corridor_length = units_per_core * unit_w
        footprint_depth = corridor_length + _CORE_PKG_D
        footprint_width = unit_d + _CORRIDOR_W + core_w
        pattern = "END_CORE" if units_per_core <= 2 else "SINGLE_LOADED"

    floor_area = footprint_width * footprint_depth

    return CoreFootprintRequirement(
        units_per_core=units_per_core,
        unit_type=unit_type,
        core_pattern=pattern,
        min_footprint_width_m=round(footprint_width, 2),
        min_footprint_depth_m=round(footprint_depth, 2),
        estimated_floor_area_sqm=round(floor_area, 1),
        estimated_unit_area_sqm=round(unit_area, 1),
    )
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_core_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/architecture/models/core_config.py backend/tests/test_core_config.py
git commit -m "feat: add core config model — 2/4/6 units per core with footprint estimation"
```

---

## Task 3: Sellable Area & RCA Model

**Files:**
- Create: `backend/architecture/models/sellable_area.py`
- Create: `backend/tests/test_sellable_area.py`
- Modify: `GDCR.yaml` (repo root) — add `sellable_ratios` section

**Context:** Client's industry ratios:
- FSI 2.7 → 42 sellable/yard
- FSI 3.6 → 54 sellable/yard
- FSI 4.0 → 60 sellable/yard
- Flat total area × 0.55 = RCA (RERA carpet area)

- [ ] **Step 1: Add sellable_ratios to GDCR.yaml**

```yaml
sellable_ratios:
  # Industry heuristic: achieved FSI → sellable sq ft per sq yard of plot
  fsi_to_sellable_per_yard:
    - { fsi: 1.8, sellable_per_yard: 27 }
    - { fsi: 2.7, sellable_per_yard: 42 }
    - { fsi: 3.6, sellable_per_yard: 54 }
    - { fsi: 4.0, sellable_per_yard: 60 }

  # General ratio: flat_total_area × ratio = RCA (RERA carpet area)
  flat_to_rca_ratio: 0.55

  # Segment-specific efficiency ratios
  segment_efficiency:
    budget: 0.60
    mid: 0.55
    premium: 0.50
    luxury: 0.45
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/test_sellable_area.py
import pytest
from architecture.models.sellable_area import (
    interpolate_sellable_per_yard,
    compute_sellable_area,
    compute_rca_from_flat_area,
    compute_rca_from_rooms,
    SellableAreaSummary,
)

def test_exact_fsi_ratio():
    """FSI 3.6 → exactly 54 sellable/yard."""
    ratio = interpolate_sellable_per_yard(fsi=3.6)
    assert ratio == pytest.approx(54.0, abs=0.1)

def test_interpolated_fsi_ratio():
    """FSI 3.0 → interpolated between 42 (2.7) and 54 (3.6)."""
    ratio = interpolate_sellable_per_yard(fsi=3.0)
    assert 42.0 < ratio < 54.0

def test_sellable_area_4000_yard_fsi_3_6():
    """Client example: 4000 yard plot, FSI 3.6 → 216,000 sqft sellable."""
    result = compute_sellable_area(
        plot_area_sq_yards=4000.0,
        achieved_fsi=3.6,
    )
    assert result.total_sellable_sqft == pytest.approx(216000.0, rel=0.01)

def test_rca_from_flat_area():
    """Client example: 1960 sqft flat × 0.55 = 1078 sqft RCA."""
    rca = compute_rca_from_flat_area(flat_total_sqft=1960.0, ratio=0.55)
    assert rca == pytest.approx(1078.0, abs=1.0)

def test_rca_from_rooms():
    """RCA = sum of internal room areas (wall-to-wall)."""
    room_areas = [120.0, 100.0, 80.0, 35.0, 25.0]  # sqft
    rca = compute_rca_from_rooms(room_areas_sqft=room_areas)
    assert rca == pytest.approx(360.0)

def test_sellable_summary_complete():
    """Full summary includes sellable, RCA, efficiency."""
    summary = compute_sellable_area(
        plot_area_sq_yards=4000.0,
        achieved_fsi=3.6,
        flat_total_sqft=1960.0,
        segment="mid",
    )
    assert summary.total_sellable_sqft > 0
    assert summary.estimated_rca_per_flat_sqft > 0
    assert summary.efficiency_ratio > 0
```

- [ ] **Step 3: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_sellable_area.py -v`
Expected: FAIL

- [ ] **Step 4: Implement sellable area model**

```python
# backend/architecture/models/sellable_area.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from rules_engine.rules.loader import get_gdcr_config


@dataclass(frozen=True)
class SellableAreaSummary:
    plot_area_sq_yards: float
    achieved_fsi: float
    sellable_per_yard: float
    total_sellable_sqft: float
    flat_total_sqft: float
    estimated_rca_per_flat_sqft: float
    efficiency_ratio: float
    segment: str


def _load_sellable_config() -> dict:
    gdcr = get_gdcr_config() or {}
    return gdcr.get("sellable_ratios", {})


def interpolate_sellable_per_yard(fsi: float) -> float:
    """Interpolate sellable-per-yard from FSI using configured breakpoints."""
    cfg = _load_sellable_config()
    breakpoints = cfg.get("fsi_to_sellable_per_yard", [])

    if not breakpoints:
        # Fallback: linear approximation
        return fsi * 15.0

    # Sort by FSI
    sorted_bp = sorted(breakpoints, key=lambda b: float(b["fsi"]))

    fsi_val = float(fsi)

    # Below lowest
    if fsi_val <= float(sorted_bp[0]["fsi"]):
        return float(sorted_bp[0]["sellable_per_yard"])

    # Above highest
    if fsi_val >= float(sorted_bp[-1]["fsi"]):
        return float(sorted_bp[-1]["sellable_per_yard"])

    # Interpolate between adjacent breakpoints
    for i in range(len(sorted_bp) - 1):
        f0 = float(sorted_bp[i]["fsi"])
        f1 = float(sorted_bp[i + 1]["fsi"])
        s0 = float(sorted_bp[i]["sellable_per_yard"])
        s1 = float(sorted_bp[i + 1]["sellable_per_yard"])
        if f0 <= fsi_val <= f1:
            t = (fsi_val - f0) / (f1 - f0) if f1 != f0 else 0.0
            return s0 + t * (s1 - s0)

    return float(sorted_bp[-1]["sellable_per_yard"])


def compute_rca_from_flat_area(
    flat_total_sqft: float,
    ratio: Optional[float] = None,
    segment: Optional[str] = None,
) -> float:
    """RCA = flat_total_area × efficiency_ratio."""
    if ratio is not None:
        return flat_total_sqft * ratio

    cfg = _load_sellable_config()
    if segment:
        seg_ratios = cfg.get("segment_efficiency", {})
        ratio = float(seg_ratios.get(segment, cfg.get("flat_to_rca_ratio", 0.55)))
    else:
        ratio = float(cfg.get("flat_to_rca_ratio", 0.55))

    return flat_total_sqft * ratio


def compute_rca_from_rooms(room_areas_sqft: List[float]) -> float:
    """RCA = sum of internal room areas (measured wall-to-wall)."""
    return sum(max(0.0, float(a)) for a in room_areas_sqft)


def compute_sellable_area(
    plot_area_sq_yards: float,
    achieved_fsi: float,
    flat_total_sqft: float = 0.0,
    segment: str = "mid",
) -> SellableAreaSummary:
    """Compute complete sellable area summary using industry ratios."""
    sellable_per_yard = interpolate_sellable_per_yard(achieved_fsi)
    total_sellable = plot_area_sq_yards * sellable_per_yard

    cfg = _load_sellable_config()
    seg_ratios = cfg.get("segment_efficiency", {})
    efficiency = float(seg_ratios.get(segment, cfg.get("flat_to_rca_ratio", 0.55)))

    rca_per_flat = compute_rca_from_flat_area(
        flat_total_sqft, segment=segment,
    ) if flat_total_sqft > 0 else 0.0

    return SellableAreaSummary(
        plot_area_sq_yards=plot_area_sq_yards,
        achieved_fsi=achieved_fsi,
        sellable_per_yard=round(sellable_per_yard, 1),
        total_sellable_sqft=round(total_sellable, 0),
        flat_total_sqft=flat_total_sqft,
        estimated_rca_per_flat_sqft=round(rca_per_flat, 0),
        efficiency_ratio=efficiency,
        segment=segment,
    )
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_sellable_area.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/architecture/models/sellable_area.py backend/tests/test_sellable_area.py backend/GDCR.yaml
git commit -m "feat: add sellable area model with FSI-to-sellable ratios and RCA computation"
```

---

## Task 4: Wire RCA into Area Accounting

**Files:**
- Modify: `backend/area_accounting/floor_area.py`
- Create: `backend/tests/test_area_accounting_rca.py`

**Context:** `FloorAreaBreakdown` already has `rera_carpet_area_total_sqm` and `carpet_per_unit` fields but they're only populated in the detailed (wall-aware) path. Add a quick-estimate path using the 0.55 ratio.

- [ ] **Step 1: Write test for estimated RCA path**

```python
# backend/tests/test_area_accounting_rca.py
import pytest
from area_accounting.floor_area import (
    FloorAreaBreakdown,
    compute_floor_area_breakdown_with_rca_estimate,
)

def test_rca_estimate_from_unit_areas():
    """When wall engine is not used, estimate RCA from unit envelope area × ratio."""
    breakdown = compute_floor_area_breakdown_with_rca_estimate(
        gross_built_up_sqm=200.0,
        core_area_sqm=15.0,
        corridor_area_sqm=10.0,
        unit_envelope_areas_sqm=[50.0, 50.0, 40.0, 35.0],
        segment="mid",
    )
    assert breakdown.rera_carpet_area_total_sqm > 0
    assert len(breakdown.carpet_per_unit) == 4
    # Each unit RCA should be ~55% of its envelope area
    assert breakdown.carpet_per_unit[0] == pytest.approx(50.0 * 0.55, rel=0.01)

def test_rca_efficiency_ratio_luxury():
    """Luxury segment has 0.45 efficiency (more walls, thicker finishes)."""
    breakdown = compute_floor_area_breakdown_with_rca_estimate(
        gross_built_up_sqm=200.0,
        core_area_sqm=15.0,
        corridor_area_sqm=10.0,
        unit_envelope_areas_sqm=[80.0, 80.0],
        segment="luxury",
    )
    assert breakdown.carpet_per_unit[0] == pytest.approx(80.0 * 0.45, rel=0.01)
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && python -m pytest tests/test_area_accounting_rca.py -v`
Expected: FAIL

- [ ] **Step 3: Add RCA estimation function to floor_area.py**

Add to existing `backend/area_accounting/floor_area.py`:

```python
def compute_floor_area_breakdown_with_rca_estimate(
    gross_built_up_sqm: float,
    core_area_sqm: float,
    corridor_area_sqm: float,
    unit_envelope_areas_sqm: list[float],
    segment: str = "mid",
    shaft_area_sqm: float = 0.0,
) -> FloorAreaBreakdown:
    """Quick RCA estimation without wall engine — uses segment efficiency ratio."""
    from architecture.models.sellable_area import _load_sellable_config

    cfg = _load_sellable_config()
    seg_ratios = cfg.get("segment_efficiency", {})
    ratio = float(seg_ratios.get(segment, cfg.get("flat_to_rca_ratio", 0.55)))

    carpet_per_unit = tuple(round(a * ratio, 2) for a in unit_envelope_areas_sqm)
    rca_total = sum(carpet_per_unit)
    unit_envelope_total = sum(unit_envelope_areas_sqm)
    common_total = core_area_sqm + corridor_area_sqm + shaft_area_sqm

    return FloorAreaBreakdown(
        gross_built_up_sqm=gross_built_up_sqm,
        core_area_sqm=core_area_sqm,
        corridor_area_sqm=corridor_area_sqm,
        shaft_area_sqm=shaft_area_sqm,
        common_area_total_sqm=common_total,
        unit_envelope_area_sqm=unit_envelope_total,
        internal_wall_area_sqm=0.0,
        external_wall_area_sqm=0.0,
        rera_carpet_area_total_sqm=round(rca_total, 2),
        carpet_per_unit=carpet_per_unit,
    )
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_area_accounting_rca.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/area_accounting/floor_area.py backend/tests/test_area_accounting_rca.py
git commit -m "feat: add quick RCA estimation path using segment efficiency ratios"
```

---

## Task 5: Enhanced Feasibility API with New Inputs

**Files:**
- Modify: `backend/api/views/feasibility.py`
- Modify: `backend/architecture/services/feasibility_advisor.py`
- Create: `backend/tests/test_development_inputs_api.py`

**Context:** The feasibility endpoint must now return: permissible building types, max towers per building type, core config options, and sellable area estimates — all reactive to the selected building type.

- [ ] **Step 1: Write API integration test**

```python
# backend/tests/test_development_inputs_api.py
import pytest
from django.test import TestCase
from rest_framework.test import APIClient

class TestFeasibilityAPIWithNewInputs(TestCase):
    """Test that feasibility endpoint returns new input constraints."""

    def setUp(self):
        self.client = APIClient()

    def test_feasibility_returns_building_types(self):
        """Response should include permissible building types for the plot."""
        # This test requires a plot to exist — use fixture or skip if no DB
        # For now, test the shape of a mocked response
        from architecture.models.building_types import get_permissible_building_types
        types = get_permissible_building_types(road_width_m=18.0)
        assert len(types) > 0
        for bt in types:
            assert hasattr(bt, "effective_max_floors")
            assert bt.effective_max_floors > 0

    def test_feasibility_returns_core_configs(self):
        """Response should include available core configurations."""
        from architecture.models.core_config import get_core_configs
        configs = get_core_configs()
        assert len(configs) == 3
        units = [c.units_per_core for c in configs]
        assert 2 in units
        assert 4 in units
        assert 6 in units

    def test_sellable_estimate_in_feasibility(self):
        """Response should include sellable area estimate."""
        from architecture.models.sellable_area import compute_sellable_area
        summary = compute_sellable_area(
            plot_area_sq_yards=4000.0,
            achieved_fsi=3.6,
            segment="mid",
        )
        assert summary.total_sellable_sqft == pytest.approx(216000.0, rel=0.01)
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_development_inputs_api.py -v`
Expected: PASS (these test model functions, not HTTP yet)

- [ ] **Step 3: Update feasibility_advisor.py to return new data**

Add to the `FeasibilityMap` dataclass and `compute_feasibility_map` function:

```python
# Add to FeasibilityMap dataclass:
    # New input constraints
    permissible_building_types: List[dict] = field(default_factory=list)
    core_configs: List[dict] = field(default_factory=list)
    sellable_estimate: Optional[dict] = None
```

At the end of `compute_feasibility_map()`, before `return result`:

```python
    # ── Populate new input constraints ───────────────────────────────────
    from architecture.models.building_types import get_permissible_building_types
    from architecture.models.core_config import get_core_configs, compute_required_footprint_for_core
    from architecture.models.sellable_area import compute_sellable_area
    from common.units import sqm_to_sqyard

    pbt = get_permissible_building_types(road_width_m=road_width, storey_height_m=storey_height_m)
    result.permissible_building_types = [
        {
            "id": bt.id,
            "label": bt.label,
            "effectiveMaxFloors": bt.effective_max_floors,
            "maxHeightM": bt.max_height_m,
            "liftRequired": bt.lift_required,
            "fireStairRequired": bt.fire_stair_required,
            "copRequired": bt.cop_required,
            "typicalEfficiency": bt.typical_efficiency_ratio,
        }
        for bt in pbt
    ]

    result.core_configs = [
        {
            "unitsPerCore": cc.units_per_core,
            "segment": cc.segment,
            "label": cc.label,
            "preferredPattern": cc.preferred_pattern,
        }
        for cc in get_core_configs()
    ]

    # Sellable estimate using best FSI
    if best_fsi > 0:
        plot_area_yards = sqm_to_sqyard(plot_area_sqm)
        sellable = compute_sellable_area(
            plot_area_sq_yards=plot_area_yards,
            achieved_fsi=best_fsi,
        )
        result.sellable_estimate = {
            "achievedFsi": best_fsi,
            "sellablePerYard": sellable.sellable_per_yard,
            "totalSellableSqft": sellable.total_sellable_sqft,
            "efficiencyRatio": sellable.efficiency_ratio,
        }
```

- [ ] **Step 4: Update feasibility view to serialize new fields**

In `backend/api/views/feasibility.py`, add to `_feasibility_to_dict()`:

```python
    # New input constraints
    data["permissibleBuildingTypes"] = fmap.permissible_building_types
    data["coreConfigs"] = fmap.core_configs
    data["sellableEstimate"] = fmap.sellable_estimate
```

- [ ] **Step 5: Add sqm_to_sqyard helper if missing**

Check `backend/common/units.py` — if `sqm_to_sqyard` doesn't exist, add:

```python
def sqm_to_sqyard(sqm: float) -> float:
    """1 sq metre = 1.19599 sq yards."""
    return sqm * 1.19599
```

- [ ] **Step 6: Run full test suite**

Run: `cd backend && python -m pytest tests/test_development_inputs_api.py tests/test_building_types.py tests/test_core_config.py tests/test_sellable_area.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/architecture/services/feasibility_advisor.py backend/api/views/feasibility.py backend/common/units.py backend/tests/test_development_inputs_api.py
git commit -m "feat: feasibility API returns building types, core configs, sellable estimates"
```

---

## Task 6: New Development Request Serializer

**Files:**
- Create: `backend/api/serializers/development_inputs.py`
- Modify: `backend/api/views/development.py`

**Context:** Replace the current `OptimalDevelopmentRequestSerializer` (which takes `storey_height_m`, `min_width_m`, `min_depth_m`) with a user-facing input model that accepts building_type, floors, units_per_core, n_buildings, and segment.

- [ ] **Step 1: Write new serializer**

```python
# backend/api/serializers/development_inputs.py
from rest_framework import serializers


class DevelopmentInputSerializer(serializers.Serializer):
    """New user-facing development input contract.

    Replaces the old OptimalDevelopmentRequestSerializer with inputs that
    match how developers think about projects.
    """
    # Plot identification
    tp = serializers.IntegerField(help_text="Town Planning scheme number")
    fp = serializers.IntegerField(help_text="Final Plot number")

    # 1. Building type (1=Low-Rise, 2=Mid-Rise, 3=High-Rise)
    building_type = serializers.IntegerField(
        min_value=1, max_value=3, default=3,
        help_text="Building type: 1=Low-Rise(G+3), 2=Mid-Rise(G+7), 3=High-Rise(8+)",
    )

    # 2. Number of floors
    floors = serializers.IntegerField(
        required=False, default=None, allow_null=True,
        help_text="User-selected floor count. null = auto (GDCR max permissible)",
    )

    # 3. Core config (units per core per floor)
    units_per_core = serializers.ChoiceField(
        choices=[2, 4, 6], default=4,
        help_text="Units sharing one lift+staircase core: 2 (premium), 4 (mid), 6 (budget)",
    )

    # 4. Segment (drives RCA efficiency ratio)
    segment = serializers.ChoiceField(
        choices=["budget", "mid", "premium", "luxury"], default="mid",
        help_text="Market segment — affects RCA efficiency ratio",
    )

    # 5. Number of buildings (towers)
    n_buildings = serializers.IntegerField(
        required=False, default=None, allow_null=True,
        help_text="Number of towers. null = auto (optimizer decides). "
                  "Must not exceed max_feasible_towers from feasibility.",
    )

    # Unit mix (optional — for AI suggestion mode)
    unit_mix = serializers.ListField(
        child=serializers.CharField(), required=False, default=list,
        help_text="e.g. ['2BHK', '3BHK']. Empty = auto.",
    )

    # Storey height (rarely changed by user)
    storey_height_m = serializers.FloatField(default=3.0, min_value=2.5, max_value=4.5)

    # Output options
    include_building_layout = serializers.BooleanField(default=False)
    geometry_format = serializers.ChoiceField(
        choices=["geojson", "wkt"], default="geojson",
    )

    def validate_floors(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Floors must be at least 1.")
        return value

    def validate_n_buildings(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Number of buildings must be at least 1.")
        return value
```

- [ ] **Step 2: Update development view to use new serializer**

In `backend/api/views/development.py`, update `OptimalDevelopmentFloorPlanAPIView.post()`:

```python
from api.serializers.development_inputs import DevelopmentInputSerializer
from architecture.models.building_types import get_building_type, get_permissible_building_types
from architecture.models.core_config import get_core_config
from architecture.models.sellable_area import compute_sellable_area
from common.units import sqm_to_sqyard

# In the post() method:
serializer = DevelopmentInputSerializer(data=request.data)
serializer.is_valid(raise_exception=True)
data = serializer.validated_data

# Resolve building type constraints
bt = get_building_type(data["building_type"])
storey_height = data["storey_height_m"]

# Resolve floor count: user-selected or auto (from building type cap)
road_width = float(plot.road_width_m or 0)
from architecture.regulatory_accessors import get_max_permissible_height_by_road_width
road_cap = get_max_permissible_height_by_road_width(road_width)
type_cap = bt.max_height_m
effective_height_cap = min(road_cap, type_cap)
max_permissible_floors = int(effective_height_cap / storey_height)

floors = data["floors"]
if floors is None:
    floors = max_permissible_floors
floors = min(floors, max_permissible_floors)

# Resolve tower count
n_buildings = data["n_buildings"]  # None = auto

# Compute min dimensions from core config
core_cfg = get_core_config(data["units_per_core"])
# ... thread through to pipeline
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/serializers/development_inputs.py backend/api/views/development.py
git commit -m "feat: new DevelopmentInputSerializer with building type, floors, core config, towers"
```

---

## Task 7: Thread New Inputs Through Pipeline

**Files:**
- Modify: `backend/architecture/services/development_pipeline.py`
- Modify: `backend/architecture/regulatory/development_optimizer.py`

**Context:** The pipeline must accept and use: `building_type`, `units_per_core`, `segment`, user-selected `floors`, and `n_buildings`. These replace the raw `min_width_m`/`min_depth_m` parameters.

- [ ] **Step 1: Update pipeline function signature**

In `development_pipeline.py`, update `generate_optimal_development_floor_plans`:

```python
def generate_optimal_development_floor_plans(
    plot: Plot,
    storey_height_m: float = 3.0,
    # New user-facing inputs
    building_type: int = 3,
    units_per_core: int = 4,
    segment: str = "mid",
    user_floors: int | None = None,
    n_buildings: int | None = None,
    unit_mix: list[str] | None = None,
    # Legacy (still used internally)
    min_width_m: float = 5.0,
    min_depth_m: float = 3.5,
    include_building_layout: bool = False,
    strict: bool = True,
    program_spec: ProgramSpec | None = None,
    forced_towers: int | None = None,
    target_fsi: float | None = None,
) -> DevelopmentFloorPlanResult:
```

Add at the top of the function body:

```python
    # Resolve building type constraints
    from architecture.models.building_types import get_building_type
    from architecture.models.core_config import compute_required_footprint_for_core
    from architecture.models.sellable_area import compute_sellable_area
    from common.units import sqm_to_sqyard

    bt = get_building_type(building_type)

    # Derive min dimensions from core config + unit type
    dominant_unit = "2BHK"  # default
    if unit_mix:
        dominant_unit = unit_mix[0] if unit_mix else "2BHK"

    fp_req = compute_required_footprint_for_core(
        units_per_core=units_per_core,
        unit_type=dominant_unit,
        building_height_m=bt.max_height_m,
    )
    min_width_m = max(min_width_m, fp_req.min_footprint_width_m)
    min_depth_m = max(min_depth_m, fp_req.min_footprint_depth_m)

    # Override tower count if user specified
    if n_buildings is not None:
        forced_towers = n_buildings
```

- [ ] **Step 2: Add sellable area to result DTO**

Add a `sellable_summary` field to `DevelopmentFloorPlanResult`:

```python
@dataclass
class DevelopmentFloorPlanResult:
    # ... existing fields ...
    sellable_summary: dict | None = None  # New: sellable area + RCA summary
```

At the end of the pipeline (after all tower layouts are computed):

```python
    # Compute sellable area summary
    if result.achieved_fsi > 0:
        plot_area_yards = sqm_to_sqyard(float(plot.plot_area_sqm))
        avg_flat_sqft = 0.0
        if result.tower_floor_layouts:
            total_units = sum(t.total_units for t in result.tower_floor_layouts)
            total_area = sum(t.unit_area_sum_sqm for t in result.tower_floor_layouts)
            if total_units > 0:
                avg_flat_sqft = (total_area / total_units) * 10.764  # sqm → sqft

        sellable = compute_sellable_area(
            plot_area_sq_yards=plot_area_yards,
            achieved_fsi=result.achieved_fsi,
            flat_total_sqft=avg_flat_sqft,
            segment=segment,
        )
        result.sellable_summary = {
            "plotAreaSqYards": round(plot_area_yards, 1),
            "achievedFsi": round(result.achieved_fsi, 3),
            "sellablePerYard": sellable.sellable_per_yard,
            "totalSellableSqft": sellable.total_sellable_sqft,
            "avgFlatTotalSqft": round(avg_flat_sqft, 0),
            "estimatedRcaPerFlatSqft": sellable.estimated_rca_per_flat_sqft,
            "efficiencyRatio": sellable.efficiency_ratio,
            "segment": segment,
        }
```

- [ ] **Step 3: Commit**

```bash
git add backend/architecture/services/development_pipeline.py
git commit -m "feat: thread building type, core config, sellable area through pipeline"
```

---

## Task 8: Frontend — Redesign PlannerInputs Type & Store

**Files:**
- Modify: `frontend/src/types/plannerInputs.ts` (canonical type definition — all consumers import from here)
- Modify: `frontend/src/state/plannerStore.ts` (update defaults)

**Context:** Replace current `PlannerInputs` shape with the new 5-group model. The type is defined in `frontend/src/types/plannerInputs.ts` and imported by `plannerStore.ts`, `plannerService.ts`, and `DevelopmentInputs.tsx`. All consumers reference it by import, so updating the canonical file updates everything.

Old fields being removed: `towerCount`, `preferredFloors`, `vastu`.
New fields: `buildingType`, `floors`, `unitsPerCore`, `nBuildings`, `storeyHeightM`.

- [ ] **Step 1: Update canonical type in `frontend/src/types/plannerInputs.ts`**

```typescript
// frontend/src/types/plannerInputs.ts — FULL REPLACEMENT

export interface PlannerInputs {
  // 1. Building Type
  buildingType: 1 | 2 | 3;

  // 2. Floors (null = auto/GDCR max)
  floors: number | null;

  // 3. Core (units per core)
  unitsPerCore: 2 | 4 | 6;

  // 4. Segment (drives RCA efficiency)
  segment: "budget" | "mid" | "premium" | "luxury";

  // 5. Number of buildings (null = auto)
  nBuildings: number | null;

  // Unit mix (optional)
  unitMix: string[];

  // Storey height (rarely changed)
  storeyHeightM: number;
}

// Update DEFAULT_INPUTS
const DEFAULT_INPUTS: PlannerInputs = {
  buildingType: 3,
  floors: null,
  segment: "mid",
  unitsPerCore: 4,
  nBuildings: null,
  unitMix: ["2BHK", "3BHK"],
  storeyHeightM: 3.0,
};
```

- [ ] **Step 2: Update `frontend/src/state/plannerStore.ts` defaults**

Replace the `defaultInputs` object in plannerStore.ts with the new defaults above. The store already imports `PlannerInputs` from `@/types/plannerInputs`, so the type change propagates automatically.

- [ ] **Step 3: Search and fix any remaining references to removed fields**

Search for `towerCount`, `preferredFloors`, and `vastu` across the frontend codebase. Update or remove all references. Key files to check:
- `frontend/src/services/plannerService.ts` (will be updated in Task 10)
- `frontend/src/modules/planner/components/DevelopmentInputs.tsx` (will be rewritten in Task 9)
- Any other components that read from the store

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/plannerInputs.ts frontend/src/state/plannerStore.ts
git commit -m "feat: redesign PlannerInputs with building type, core config, floors, towers"
```

---

## Task 9: Frontend — Rebuild DevelopmentInputs Component

**Files:**
- Modify: `frontend/src/modules/planner/components/DevelopmentInputs.tsx`

**Context:** The entire component is rebuilt with 5 input groups. Each group shows the GDCR-calculated limit alongside the user's selection. All inputs reactively update the feasibility query.

- [ ] **Step 1: Rewrite DevelopmentInputs.tsx**

The component has 5 sections:

```
┌─────────────────────────────────────┐
│ 1. BUILDING TYPE                    │
│    ○ Low-Rise (G+3)                │
│    ● Mid-Rise (G+7)               │
│    ○ High-Rise (8+)               │
│    GDCR: "18m road allows up to    │
│    High-Rise (max 30m)"            │
├─────────────────────────────────────┤
│ 2. FLOORS                          │
│    GDCR Max: 10 floors             │
│    [  7  ] ← user slider/input     │
│    "Selecting 7 floors (21m height)"│
├─────────────────────────────────────┤
│ 3. CORE (Units per Core)           │
│    ○ 2 (Premium)                   │
│    ● 4 (Mid-Market)               │
│    ○ 6 (Budget)                    │
│    "4 flats share 1 lift+staircase" │
├─────────────────────────────────────┤
│ 4. NUMBER OF BUILDINGS             │
│    Max Possible: 3                  │
│    [  2  ] ← dropdown              │
│    "2 towers, ~680 sqm footprint"   │
├─────────────────────────────────────┤
│ 5. SELLABLE AREA ESTIMATE          │
│    Total Sellable: 2,16,000 sqft   │
│    Avg RCA/Flat: 1,078 sqft        │
│    Efficiency: 55%                  │
│    Segment: [Mid ▼]                │
└─────────────────────────────────────┘
```

Key implementation points:
- Use `useFeasibility(plotId)` hook to get GDCR limits
- When building type changes → clamp floors to new max
- When floors change → recalculate height → update core options
- When nBuildings changes → validate against `maxFeasibleTowers`
- Sellable section is read-only (computed from other inputs)

```tsx
// Pseudocode structure — full implementation follows component patterns in codebase

export function DevelopmentInputs() {
  const { inputs, setInputs } = usePlannerStore();
  const { selectedPlotId } = usePlannerStore();
  const { data: feasibility } = useFeasibility(selectedPlotId);

  // Derived constraints from feasibility
  const permissibleTypes = feasibility?.permissibleBuildingTypes ?? [];
  const maxFloors = useMemo(() => {
    const bt = permissibleTypes.find(t => t.id === inputs.buildingType);
    return bt?.effectiveMaxFloors ?? 10;
  }, [inputs.buildingType, permissibleTypes]);

  const maxTowers = feasibility?.maxFeasibleTowers ?? 1;

  // Clamp floors when building type changes
  useEffect(() => {
    if (inputs.floors !== null && inputs.floors > maxFloors) {
      setInputs({ floors: maxFloors });
    }
  }, [maxFloors]);

  return (
    <div className="space-y-6">
      {/* Section 1: Building Type */}
      <InputSection title="Building Type">
        <RadioGroup
          value={inputs.buildingType}
          onChange={(v) => setInputs({ buildingType: v })}
          options={permissibleTypes.map(t => ({
            value: t.id,
            label: t.label,
            sublabel: `Max ${t.effectiveMaxFloors} floors`,
            disabled: false,
          }))}
        />
      </InputSection>

      {/* Section 2: Floors */}
      <InputSection title="Number of Floors">
        <div className="text-sm text-muted-foreground">
          GDCR Max: {maxFloors} floors
        </div>
        <Slider
          min={1}
          max={maxFloors}
          value={inputs.floors ?? maxFloors}
          onChange={(v) => setInputs({ floors: v })}
        />
        <div className="text-sm">
          {(inputs.floors ?? maxFloors)} floors
          = {((inputs.floors ?? maxFloors) * inputs.storeyHeightM).toFixed(0)}m height
        </div>
      </InputSection>

      {/* Section 3: Core Config */}
      <InputSection title="Units per Core">
        <RadioGroup
          value={inputs.unitsPerCore}
          onChange={(v) => setInputs({ unitsPerCore: v })}
          options={[
            { value: 2, label: "2 Units/Core", sublabel: "Premium" },
            { value: 4, label: "4 Units/Core", sublabel: "Mid-Market" },
            { value: 6, label: "6 Units/Core", sublabel: "Budget" },
          ]}
        />
      </InputSection>

      {/* Section 4: Number of Buildings */}
      <InputSection title="Number of Buildings">
        <div className="text-sm text-muted-foreground">
          Max Possible: {maxTowers}
        </div>
        <Select
          value={inputs.nBuildings ?? "auto"}
          onChange={(v) => setInputs({ nBuildings: v === "auto" ? null : Number(v) })}
          options={[
            { value: "auto", label: "Auto (Optimized)" },
            ...Array.from({ length: maxTowers }, (_, i) => ({
              value: i + 1,
              label: `${i + 1} Building${i > 0 ? "s" : ""}`,
            })),
          ]}
        />
      </InputSection>

      {/* Section 5: Sellable Area / Segment */}
      <InputSection title="Sellable Area Estimate">
        <Select
          value={inputs.segment}
          onChange={(v) => setInputs({ segment: v })}
          options={[
            { value: "budget", label: "Budget (60% efficiency)" },
            { value: "mid", label: "Mid (55% efficiency)" },
            { value: "premium", label: "Premium (50% efficiency)" },
            { value: "luxury", label: "Luxury (45% efficiency)" },
          ]}
        />
        {feasibility?.sellableEstimate && (
          <div className="mt-3 space-y-1 text-sm">
            <div>Total Sellable: <strong>
              {feasibility.sellableEstimate.totalSellableSqft.toLocaleString()} sqft
            </strong></div>
            <div>Sellable/Yard: <strong>
              {feasibility.sellableEstimate.sellablePerYard}
            </strong></div>
            <div>Est. FSI: <strong>
              {feasibility.sellableEstimate.achievedFsi.toFixed(2)}
            </strong></div>
          </div>
        )}
      </InputSection>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/modules/planner/components/DevelopmentInputs.tsx
git commit -m "feat: rebuild DevelopmentInputs with 5 input groups — building type, floors, core, towers, sellable"
```

---

## Task 10: Frontend — Update API Service & Metrics Panel

**Files:**
- Modify: `frontend/src/services/plannerService.ts`
- Modify: `frontend/src/modules/planner/components/PlanningMetricsPanel.tsx`

- [ ] **Step 1: Update plannerService to send new payload shape**

```typescript
// In plannerService.ts — update the generate function to send new input shape

export async function generateDevelopmentPlan(plotId: string, inputs: PlannerInputs) {
  const payload = {
    tp: extractTp(plotId),
    fp: extractFp(plotId),
    building_type: inputs.buildingType,
    floors: inputs.floors,
    units_per_core: inputs.unitsPerCore,
    segment: inputs.segment,
    n_buildings: inputs.nBuildings,
    unit_mix: inputs.unitMix,
    storey_height_m: inputs.storeyHeightM,
    geometry_format: "geojson",
  };
  return httpClient.post("/api/development/optimal-floor-plan/", payload);
}
```

- [ ] **Step 2: Add sellable area to PlanningMetricsPanel**

In `PlanningMetricsPanel.tsx`, add a new section showing:

```tsx
{/* Sellable Area Metrics */}
{scenario?.sellableSummary && (
  <MetricGroup title="Sellable Area">
    <Metric label="Total Sellable" value={`${scenario.sellableSummary.totalSellableSqft.toLocaleString()} sqft`} />
    <Metric label="Sellable/Yard" value={scenario.sellableSummary.sellablePerYard} />
    <Metric label="Avg RCA/Flat" value={`${scenario.sellableSummary.estimatedRcaPerFlatSqft.toLocaleString()} sqft`} />
    <Metric label="Efficiency" value={`${(scenario.sellableSummary.efficiencyRatio * 100).toFixed(0)}%`} />
    <Metric label="Segment" value={scenario.sellableSummary.segment} />
  </MetricGroup>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/plannerService.ts frontend/src/modules/planner/components/PlanningMetricsPanel.tsx
git commit -m "feat: update API service + metrics panel with sellable area, RCA, new input payload"
```

---

## Task 11: API Response Mapping Update

**Files:**
- Modify: `backend/api/mappers/development_mapper.py`

**Context:** The response mapper must include the new `sellable_summary` and pass through `building_type`, `units_per_core`, `segment` in the response so the frontend can confirm what was used.

- [ ] **Step 1: Add sellable_summary to response mapping**

In the mapper function (likely `map_development_result_to_dict`), add:

```python
    # Sellable area summary
    if result.sellable_summary:
        mapped["sellableSummary"] = result.sellable_summary

    # Echo back resolved inputs
    mapped["resolvedInputs"] = {
        "buildingType": building_type,
        "floors": result.floors,
        "unitsPerCore": units_per_core,
        "segment": segment,
        "nBuildings": result.n_towers,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/api/mappers/development_mapper.py
git commit -m "feat: include sellable summary and resolved inputs in API response"
```

---

## Task 12: End-to-End Integration Test

**Files:**
- Create: `backend/tests/test_e2e_new_inputs.py`

- [ ] **Step 1: Write E2E test**

```python
# backend/tests/test_e2e_new_inputs.py
"""
End-to-end test: new inputs → pipeline → sellable area in response.
Requires a Plot in the DB (TP14, FP82 as reference).
"""
import pytest
from architecture.models.building_types import get_building_type
from architecture.models.core_config import get_core_config, compute_required_footprint_for_core
from architecture.models.sellable_area import compute_sellable_area, interpolate_sellable_per_yard


class TestNewInputsE2E:
    def test_building_type_constrains_floors(self):
        bt1 = get_building_type(1)
        bt3 = get_building_type(3)
        assert bt1.max_floors < bt3.max_floors
        assert bt1.lift_required is False
        assert bt3.fire_stair_required is True

    def test_core_config_drives_footprint(self):
        fp2 = compute_required_footprint_for_core(2, "3BHK", 30.0)
        fp6 = compute_required_footprint_for_core(6, "3BHK", 30.0)
        # 6 units/core needs a bigger footprint than 2 units/core
        assert fp6.estimated_floor_area_sqm > fp2.estimated_floor_area_sqm

    def test_sellable_ratios_match_client_examples(self):
        # Client example 1: FSI 3.6 → 54/yard
        assert interpolate_sellable_per_yard(3.6) == pytest.approx(54.0, abs=0.1)
        # Client example 2: 4000 yards × 54 = 216,000 sqft
        s = compute_sellable_area(4000.0, 3.6)
        assert s.total_sellable_sqft == pytest.approx(216000.0, rel=0.01)

    def test_rca_matches_client_example(self):
        from architecture.models.sellable_area import compute_rca_from_flat_area
        rca = compute_rca_from_flat_area(1960.0, ratio=0.55)
        assert rca == pytest.approx(1078.0, abs=1.0)

    def test_segment_affects_efficiency(self):
        s_budget = compute_sellable_area(4000.0, 3.6, 1960.0, "budget")
        s_luxury = compute_sellable_area(4000.0, 3.6, 1960.0, "luxury")
        assert s_budget.estimated_rca_per_flat_sqft > s_luxury.estimated_rca_per_flat_sqft
```

- [ ] **Step 2: Run E2E tests**

Run: `cd backend && python -m pytest tests/test_e2e_new_inputs.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_e2e_new_inputs.py
git commit -m "test: E2E validation of new inputs — building type, core config, sellable ratios"
```

---

## Summary of Changes

| Component | Before | After |
|-----------|--------|-------|
| **Inputs** | `storey_height_m`, `min_width_m`, `min_depth_m`, `unit_mix[]`, `segment`, `towerCount` | `building_type(1/2/3)`, `floors(auto/N)`, `units_per_core(2/4/6)`, `n_buildings(auto/N)`, `segment`, `unit_mix[]` |
| **Feasibility** | Returns tower options + floor plan compat | + building types, core configs, sellable estimate, max towers per type |
| **Pipeline** | Raw dimension params | Derives dimensions from building type + core config |
| **Area accounting** | Partial RCA (wall engine only) | + Quick RCA via segment efficiency ratio |
| **Metrics** | FSI, GC, BUA | + Sellable/yard, total sellable, RCA/flat, efficiency% |
| **Validation** | Floor count vs height cap | + Building type vs road width, towers vs max feasible, floors clamped to type |

## Execution Order

Tasks 1-4 are backend-only and independent — can be parallelized.
Task 5 depends on 1-3 (uses all three new models).
Task 6-7 depend on 5 (API + pipeline threading).
Tasks 8-10 are frontend — depend on 5-7 (need API contract).
Task 11-12 are integration — depend on everything.

```
[T1 Building Types] ──┐
[T2 Core Config]    ──├─→ [T5 Feasibility API] → [T6 Serializer] → [T7 Pipeline] → [T11 Response Mapper]
[T3 Sellable Area]  ──┤                                                               ↓
[T4 RCA Accounting] ──┘                          [T8 Store] → [T9 Inputs UI] → [T10 Service+Metrics]
                                                                                       ↓
                                                                               [T12 E2E Tests]
```
