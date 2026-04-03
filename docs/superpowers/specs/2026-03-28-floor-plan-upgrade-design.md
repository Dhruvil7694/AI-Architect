# Floor Plan Generation Upgrade — GDCR-Aware AI Layout + Professional Rendering

**Date:** 2026-03-28
**Status:** Approved
**Scope:** Backend floor plan generation pipeline — AI prompt, validation, SVG rendering
**Target:** Surat (SUDA, Category D1) — GDCR-2017 compliance only

---

## 1. Problem Statement

The current floor plan generation system produces layouts that look algorithm-generated rather than architect-designed:

1. **Rigid grid layout** — all rooms are rectangles packed in horizontal 4-zone strips (Zone A/B/C/D), no spatial hierarchy or architectural flow
2. **Empty units bug** — 3BHK units (and potentially others) render as empty grey boxes with no room subdivision
3. **No architectural intelligence** — bedrooms don't relate to bathrooms naturally, kitchen isn't adjacent to dining, no circulation spine
4. **Poor visual quality** — overlapping labels, no line weight differentiation, basic hatching, missing drawing conventions (north arrow, structural grid, proper title block)
5. **GDCR rules applied post-hoc** — the deterministic engine doesn't understand regulations, it only clamps minimums after layout generation

## 2. Solution Overview

**Approach: GDCR-Aware AI Layout + Deterministic Validation**

- AI (Claude or GPT-4o, admin-switchable) receives GDCR skill content as system prompt context alongside floor plate geometry
- AI generates complete room-level layouts for ALL units with architectural reasoning
- Deterministic validator snaps coordinates, enforces GDCR minimums, aligns wet stacks
- SVG renderer upgraded with professional GDCR drawing conventions

**Key principle change:** AI generates rooms (not just unit envelopes). The deterministic engine becomes a validator and snapper, not a layout generator.

---

## 3. AI Prompt Architecture

### 3.1 System Prompt Structure (Layered Context)

**Layer 1 — Role Definition:**
"You are a GDCR-compliant residential floor plan architect for Surat (SUDA, Category D1). You generate precise room-level layouts that a professional architect would approve."

**Layer 2 — GDCR Regulations (from `.claude/skills/cgdcr-2017.skill`):**

Inject relevant sections from the skill files:
- `definitions.md` — key terms (dwelling unit, built-up area, FSI, balcony, OTS, etc.)
- `part2-margins-height-parking.md` — OTS requirements (Table 6.45), building depth rules (Reg 6.16)
- `part3-performance.md` — room heights (Reg 13.1.7), staircase dimensions (Table 13.2), lift rules (Reg 13.12), ventilation requirements (Reg 13.4), sanitation minimums (Reg 13.9), railing heights (Reg 13.1.11)

**Layer 3 — Architectural Design Principles:**

Explicit instructions injected as prompt rules:

1. **Entry sequence:** Corridor -> Foyer -> Living/Dining (public zone) -> Passage -> Bedrooms (private zone)
2. **Kitchen adjacency:** Must share wall with dining or living; near utility room
3. **Master suite:** Master bedroom on exterior wall with attached bathroom on interior side
4. **Wet zone clustering:** All bathrooms, toilets, kitchen, utility grouped to share plumbing stacks
5. **Balcony access:** From living room or master bedroom; on exterior face
6. **No landlocked rooms:** Every habitable room touches an exterior wall or OTS for ventilation
7. **Passage as spine:** For 2BHK+, a passage connects foyer to bedroom zone (not walking through living room to reach bedrooms)
8. **Proportionality:** No room narrower than 60% of its depth; bedrooms roughly square
9. **Mirroring:** Units on opposite sides of core should be mirror images for structural symmetry

### 3.2 User Prompt (Per-Generation)

Provided per API call:
- Floor plate dimensions (metres)
- Building height (metres), number of floors
- Segment (budget / mid / premium / luxury)
- Unit mix with target carpet areas (e.g., `["2BHK", "3BHK"]`)
- Core position and sizing (pre-computed by existing core placement logic)
- Corridor position and width
- Which side each unit faces (south/north)

### 3.3 Output Schema

AI returns JSON with complete room-level geometry:

```json
{
  "core": {
    "x": float, "y": float, "w": float, "h": float,
    "stairs": [{"x": float, "y": float, "w": float, "h": float}],
    "lifts": [{"x": float, "y": float, "w": float, "h": float}],
    "lobby": {"x": float, "y": float, "w": float, "h": float}
  },
  "corridor": {"x": 0.0, "y": float, "w": float, "h": 1.5},
  "units": [
    {
      "id": "U1",
      "type": "2BHK",
      "side": "south",
      "x": float, "y": float, "w": float, "h": float,
      "rooms": [
        {
          "id": "U1_R1",
          "type": "foyer",
          "x": float, "y": float, "w": float, "h": float
        },
        {
          "id": "U1_R2",
          "type": "living",
          "x": float, "y": float, "w": float, "h": float
        }
      ],
      "balcony": {"x": float, "y": float, "w": float, "h": float}
    }
  ],
  "design_notes": "string"
}
```

Room coordinates are relative to the floor plate origin (0,0 = bottom-left corner). All dimensions in metres.

### 3.4 AI Configuration

| Parameter | Value |
|-----------|-------|
| Temperature | 0.2 |
| Max tokens | 8192 (increased from 4096 for room-level detail) |
| Timeout | 60 seconds (increased for larger prompt) |
| Retries | 3 attempts with error feedback loop |

---

## 4. Model Switching & API Integration

### 4.1 Admin Toggle

- New config field: `FLOOR_PLAN_AI_MODEL` — values: `claude` / `gpt-4o`
- Stored in `.env` as default; overridable via Django admin settings (database) if admin panel model exists
- For POC: `.env` toggle is sufficient. Admin UI toggle is a follow-up enhancement.
- Only admin users can change the model selection
- Default: `claude`

### 4.2 Model Abstraction

Extend `backend/ai_layer/client.py` with unified interface:

```python
def generate_floor_plan_layout(
    system_prompt: str,
    user_prompt: str,
    model: str = "claude",  # "claude" | "gpt-4o"
) -> dict:
    """Returns parsed JSON layout regardless of model."""
```

**Claude integration:**
- SDK: `anthropic` Python package
- API key: `CLAUDE_API_KEY` from `.env`
- Model: `claude-sonnet-4-6` (configurable)
- Same retry logic as GPT-4o (3 attempts with error feedback)

**GPT-4o integration:**
- Existing OpenAI integration in `ai_layer/client.py`
- No changes needed except routing through unified interface

### 4.3 Environment Config

Add to `backend/backend/settings.py`:
```python
CLAUDE_API_KEY = env("CLAUDE_API_KEY", default="")
FLOOR_PLAN_AI_MODEL = env("FLOOR_PLAN_AI_MODEL", default="claude")
```

---

## 5. Room Layout Intelligence

### 5.1 Room Programs by Unit Type

**1BHK:**
- Foyer, Living, Kitchen, Bedroom, Bathroom, Balcony

**2BHK:**
- Foyer, Living, Kitchen, Utility, Bedroom 1 (master + attached bathroom), Bedroom 2, Bathroom, Toilet, Balcony

**3BHK:**
- Foyer, Living+Dining, Kitchen, Utility, Bedroom 1 (master + attached bathroom), Bedroom 2 (attached bathroom), Bedroom 3, Bathroom, Toilet, Balcony

**4BHK:**
- Foyer, Living, Dining, Kitchen, Utility, Bedroom 1-4 (master + 3 attached bathrooms), Bathroom, Toilet, Balcony

### 5.2 GDCR Constraints Enforced in Prompt

| Rule | GDCR Source | Constraint |
|------|-------------|-----------|
| Habitable room ventilation | Part 3 Reg 13.4 | Openings >= 1/10th floor area; rooms must touch exterior wall |
| Min room clear height | Part 3 Reg 13.1.7 | 2.9m floor-to-floor for habitable rooms; 2.1m for circulation/service |
| Bathroom ventilation | Part 3 Reg 13.4 | Min 0.25 sqm opening; OTS >= 0.9x0.9m |
| Staircase dimensions | Part 3 Table 13.2 | Width 1.2m (<=12m height) to 2.0m (>25m); tread >=250mm; riser <=180mm |
| Lift requirement | Part 3 Reg 13.12 | Mandatory >10m height; fire lift >25m; 1 per 30 DUs |
| Railing height | Part 3 Reg 13.1.11 | Min 1.15m at balcony/terrace edges |
| Min WC area | Part 3 Reg 13.9 | 0.9 sqm per dwelling unit |
| Balcony definition | Definitions | Horizontal projection with parapet/handrail; min depth 1.2m |
| OTS requirement | Part 2 Reg 6.16 | Building depth >9m: OTS of 5.6 sqm (min side 1.8m) per 9m depth |

### 5.3 GDCR Minimum Room Areas (Existing, Retained)

| Room Type | Min Area (sqm) | Min Width (m) |
|-----------|---------------|---------------|
| Living | 9.5 | 3.0 |
| Master Bedroom | 9.5 | 2.7 |
| Secondary Bedroom | 7.5 | 2.5 |
| Kitchen | 5.5 | 1.8 |
| Bathroom | 2.16 | 1.2 |
| Toilet | 1.65 | 1.1 |
| Utility | 1.80 | 1.2 |
| Foyer | 1.80 | 1.5 |
| Balcony | — | min depth 1.2m |

### 5.4 Architectural Design Principles (Prompt Rules)

1. **Entry sequence:** Corridor -> Foyer -> Living/Dining (public) -> Passage -> Bedrooms (private)
2. **Kitchen adjacency:** Shares wall with dining or living; adjacent to utility
3. **Master suite:** Exterior wall with attached bathroom on interior side
4. **Wet zone clustering:** Bathrooms, toilets, kitchen, utility share plumbing stacks
5. **Balcony access:** From living room or master bedroom on exterior face
6. **No landlocked rooms:** Every habitable room touches exterior wall or OTS
7. **Passage as spine:** For 2BHK+, passage connects foyer to bedroom zone
8. **Proportionality:** No room narrower than 60% of its depth
9. **Mirroring:** Opposite-side units are structural mirror images

---

## 6. Deterministic Validation & Repair

The deterministic engine shifts from layout generator to validator/repairer:

### 6.1 Room Completeness Check
- For each unit, verify all expected rooms for its type are present
- Missing rooms -> validation failure -> retry AI with explicit error message
- Extra rooms (passage, closet) -> warning, allow

### 6.2 GDCR Area/Width Enforcement
- Clamp room areas up to minimums if AI undersizes
- Clamp room widths to minimums
- Log any adjustments made

### 6.3 Wet Stack Alignment
- Group units by side (south/north)
- Pair wet rooms (bathroom, toilet, kitchen, utility) across adjacent units
- Snap left-edges to averaged X position (tolerance: 0.30m)

### 6.4 Structural Grid Snapping
- Grid spacing: 4.5m (reinforced concrete columns)
- Snap room right-edges to nearest grid line
- Skip if would reduce room below minimum width

### 6.5 Coordinate Snapping
- All coordinates snapped to 50mm grid (0.05m)

### 6.6 Overlap/Gap Detection
- Check all room pairs within a unit for geometric overlap
- Check for gaps between rooms (uncovered area within unit envelope)
- Repair by adjusting widths/positions of adjacent rooms

### 6.7 Ventilation Compliance Check
- Verify every habitable room (living, dining, bedroom) touches an exterior wall
- Flag violations for AI retry or manual review

### 6.8 Fallback
- If AI fails after 3 retries for a specific unit, use existing `unit_layout_engine.py` as fallback for that unit only
- Log fallback usage for monitoring

---

## 7. SVG Rendering Upgrade

### 7.1 Line Weights

| Element | Stroke Width (at 1:100) | Color |
|---------|------------------------|-------|
| External walls (230mm) | 0.5mm | #000000 |
| Internal walls (115mm) | 0.25mm | #333333 |
| Partition walls | 0.15mm | #666666 |
| Dimension lines | 0.1mm | #444444 |
| Structural grid lines | 0.1mm dashed | #999999 |

### 7.2 Hatching Patterns (Distinct Per Room Type)

| Room Type | Pattern | Color |
|-----------|---------|-------|
| Bathroom/Toilet | Diagonal crosshatch (45 deg) | Blue-grey (#b0c4de) |
| Kitchen | Diagonal single hatch | Light orange (#fde0c0) |
| Utility | Dot pattern | Light grey (#e0e0e0) |
| Balcony | Dashed outline, no fill | — |
| Foyer/Passage | Solid fill | Light grey (#f0f0f0) |
| Living/Dining/Bedroom | No fill | White (#ffffff) |
| Core (lift+stair) | Solid fill | Dark grey (#555555) |
| Corridor | Stipple | Light (#f5f5f5) |

### 7.3 Labeling

- Room name in **bold**, area in sqm below — single clean label per room
- Unit label at centroid: "U1 (2BHK) -- 86 sqm carpet" in larger font
- No label if room area < 2 sqm
- Room dimensions (width x depth) inside each room in small text
- Dimension text along dimension lines, not inside rooms
- All text horizontal (no rotated text)

### 7.4 Dimension Lines

- Overall floor plate width and depth with tick marks and labels (metres)
- Unit widths along corridor edge
- Room dimensions inside rooms (width x depth in metres)

### 7.5 Drawing Elements

| Element | Description |
|---------|-------------|
| North arrow | Top-right corner, simple arrow with "N" |
| Title block | Bottom-right: "Typical Floor Plan -- {units_per_core} units/core -- {segment} -- Scale 1:100" |
| Structural column grid | Dashed circles at 4.5m intervals along structural grid |
| Scale bar | 5m reference with 1m subdivisions at bottom-left |
| Door arcs | Proper swing arcs with hinge point and radius |
| Windows | Blue glass rectangles on exterior walls with mullion lines |

### 7.6 No Furniture

This is a planning/regulatory tool. No furniture symbols, appliance outlines, or decorative elements.

---

## 8. Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `backend/services/ai_floor_plan_prompt.py` | **Rewrite** | GDCR skills as system context, room-level output schema, architectural principles |
| `backend/services/ai_floor_plan_service.py` | **Refactor** | AI generates rooms, validator replaces layout engine as primary path |
| `backend/services/ai_floor_plan_validator.py` | **Expand** | Room completeness, ventilation check, GDCR area enforcement |
| `backend/ai_layer/client.py` | **Extend** | Add Claude SDK support via Anthropic Python package |
| `backend/ai_layer/config.py` | **Extend** | Claude model config, admin toggle field |
| `backend/services/ai_to_geojson_converter.py` | **Update** | Handle new room types (passage, attached_bath) |
| `backend/services/svg_blueprint_renderer.py` | **Major rewrite** | Line weights, hatching, labels, structural grid, north arrow, title block |
| `backend/backend/settings.py` | **Update** | Add CLAUDE_API_KEY, FLOOR_PLAN_AI_MODEL config |
| `backend/requirements.txt` | **Update** | Add `anthropic` SDK package |

### Files Unchanged

| File | Reason |
|------|--------|
| `backend/services/unit_layout_engine.py` | Kept as fallback only |
| `backend/services/unit_block_engine.py` | Envelope placement unchanged |
| `backend/services/core_engine.py` | Core placement unchanged |
| `backend/api/views/ai_floor_plan.py` | API endpoint unchanged |
| Frontend files | Consumes same GeoJSON format |

---

## 9. Pipeline Flow

```
Input (footprint, floors, height, segment, unit_mix, model_choice)
    |
    +--[1] PROMPT ASSEMBLY
    |   +-- System: Role + GDCR skills (definitions, margins, performance regs)
    |   +-- System: Architectural design principles (adjacency, circulation, ventilation)
    |   +-- User: Floor plate dims, core position, unit mix, target areas
    |
    +--[2] AI GENERATION (Claude or GPT-4o via admin toggle)
    |   +-- Returns: Complete room-level JSON for all units
    |
    +--[3] DETERMINISTIC VALIDATION & REPAIR
    |   +-- Room completeness check (no empty units -> retry if failed)
    |   +-- GDCR minimum area/width enforcement (clamp up if below)
    |   +-- Wet stack alignment across adjacent units
    |   +-- Structural grid snapping (4.5m)
    |   +-- Coordinate snapping (50mm grid)
    |   +-- Overlap/gap detection and repair
    |   +-- Ventilation check (habitable rooms touch exterior)
    |
    +--[4] GeoJSON CONVERSION
    |   +-- Wall generation (external 230mm, internal 115mm)
    |   +-- Door placement (entry + internal, skip open-plan pairs)
    |   +-- Window placement (by room type on exterior walls)
    |   +-- Stair/lift/lobby graphics
    |
    +--[5] SVG RENDERING (upgraded)
    |   +-- Professional line weights
    |   +-- Distinct hatching per room type
    |   +-- Clean labeling (no overlap)
    |   +-- Structural column grid (dashed)
    |   +-- Dimension lines with ticks
    |   +-- North arrow + title block
    |   +-- Scale bar
    |
    +-- Output: GeoJSON + SVG + Metrics
```

---

## 10. Success Criteria

1. **No empty units** — every unit in output has complete room subdivision matching its type
2. **GDCR compliance** — all room areas, widths, ventilation, staircase dims meet GDCR-2017 Part III requirements
3. **Architectural quality** — room adjacency follows professional patterns (entry sequence, wet clustering, master suite, passage spine)
4. **Professional rendering** — SVG output has proper line weights, distinct hatching, clean labels, north arrow, structural grid, scale bar
5. **Model switching** — admin can toggle between Claude and GPT-4o; both produce valid layouts
6. **Fallback safety** — if AI fails after retries, deterministic engine produces a valid (if less elegant) layout
7. **Same API contract** — frontend receives identical GeoJSON structure, no frontend changes needed
