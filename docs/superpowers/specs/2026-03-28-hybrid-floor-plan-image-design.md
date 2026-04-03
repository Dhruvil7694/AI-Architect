# Hybrid Floor Plan Image Generation — Design Spec

**Goal:** Replace the code-based SVG floor plan renderer with DALL-E 3 image generation, producing architect-grade floor plan visuals while keeping the LLM-powered layout engine for precise room data and GDCR compliance metrics.

**Architecture:** Three-stage pipeline — (1) LLM generates room layout JSON (existing), (2) prompt builder converts JSON to rich architectural descriptions (new), (3) DALL-E 3 renders two images in parallel: a technical architectural drawing and a presentation-quality rendering (new). The existing SVG renderer stays as a fallback.

**Tech Stack:** OpenAI DALL-E 3 (`openai.images.generate`), existing Claude/GPT-4o LLM, Django backend, Next.js frontend.

---

## 1. Pipeline Overview

### Current flow (being replaced as primary)
```
LLM (Claude/GPT-4o) → room JSON → validate → snap to grid
  → convert to GeoJSON → render SVG → return SVG string
```

### New flow
```
LLM (Claude/GPT-4o) → room JSON → validate → snap to grid
  → build 2 DALL-E prompts from JSON    (new step)
  → call DALL-E 3 twice in parallel      (new step)
  → also render SVG as fallback           (existing, kept)
  → return images + metrics + SVG fallback
```

### What stays unchanged
- LLM prompt (`ai_floor_plan_prompt.py`) — no changes
- LLM validation & retry loop (`ai_floor_plan_service.py` steps 1-7) — no changes
- Metrics computation — still derived from LLM JSON, not from images
- API endpoint path: `POST /api/development/ai-floor-plan/`
- Request payload: `AIFloorPlanRequest` — no changes
- `ai_to_geojson_converter.py` and `svg_blueprint_renderer.py` — kept intact for fallback

---

## 2. New Backend Files

### `backend/services/floor_plan_image_prompt.py`

Two pure functions that convert LLM layout JSON + metrics into DALL-E 3 prompts. No AI calls, no side effects — deterministic string builders.

#### `build_architectural_prompt(layout_json: dict, metrics: dict) -> str`

Produces a prompt for a **black-and-white technical architectural floor plan** in municipal submission style.

Prompt structure:
1. **Style directive:** "Professional architectural floor plan, black and white line drawing, top-down orthographic view, scale 1:100"
2. **Floor plate:** dimensions from metrics (`floorLengthM x floorDepthM`)
3. **Core:** position, stairs count, lifts count, lobby
4. **Corridor:** width, orientation
5. **For each unit:** type (2BHK/3BHK), carpet area, side (north/south)
6. **For each room in unit:** type, dimensions (w x h), relative position described spatially ("kitchen adjacent to dining on the east side")
7. **Architectural conventions:** "Diagonal hatching on wet zones (kitchen, bathrooms, toilets). Door swing arcs shown as quarter-circle arcs. Windows as double lines on exterior walls. Dimension lines on all rooms. Structural column grid at 4.5m centers shown as dashed lines with circle markers."
8. **Title block:** "Typical Floor Plan — {units_per_core} units/core — {segment} — Scale 1:100"
9. **Finish:** "Clean white background, no color, architectural drafting convention, thin precise black lines, professional quality."

#### `build_presentation_prompt(layout_json: dict, metrics: dict) -> str`

Produces a prompt for a **colored real estate brochure rendering**.

Prompt structure:
1. **Style directive:** "Luxury residential floor plan, top-down bird's-eye view, photorealistic architectural rendering, soft warm lighting"
2. **Floor plate:** same dimensions
3. **Core and corridor:** described with material finishes ("marble-floored corridor", "stainless steel lift doors")
4. **For each unit:** type, carpet area, segment-appropriate finishes
5. **For each room:** type, dimensions, furnished ("living room with L-shaped sofa and coffee table", "master bedroom with king bed and wardrobe", "kitchen with L-shaped counter and appliances")
6. **Material palette based on segment:**
   - Budget: laminate flooring, basic tiles
   - Mid: vitrified tiles, modular kitchen
   - Premium: wooden flooring, granite counters, designer fixtures
   - Luxury: Italian marble, imported fixtures, walk-in wardrobes
7. **Balconies:** "planters with greenery, outdoor seating"
8. **Finish:** "No perspective distortion, perfectly orthographic top-down view, clean edges, magazine-quality rendering, warm ambient lighting with soft shadows."

### `backend/ai_layer/image_client.py`

Single function for DALL-E 3 image generation.

```python
def generate_image(
    prompt: str,
    size: str = "1792x1024",
    quality: str = "hd",
    style: str = "natural",
    timeout_s: float = 30.0,
) -> Optional[str]:
    """
    Call DALL-E 3 and return base64-encoded PNG.

    Returns None on failure (timeout, content policy, API error).
    Logs the error but does not raise.
    """
```

- Uses `openai.images.generate(model="dall-e-3", response_format="b64_json", ...)`
- Size `1792x1024` — landscape, best aspect ratio for floor plans
- Quality `"hd"` — higher detail for architectural line work
- Style `"natural"` for architectural drawing, `"vivid"` for presentation rendering
- Returns base64 string or `None` on any failure
- Timeout: 30s (DALL-E 3 typically responds in 10-20s)

---

## 3. Modified Backend Files

### `backend/services/ai_floor_plan_service.py`

The `generate_ai_floor_plan()` function changes after step 7 (snap/align).

New steps 8-11:
```python
# Step 8: Build image prompts from validated layout JSON
arch_prompt = build_architectural_prompt(ai_layout, metrics)
pres_prompt = build_presentation_prompt(ai_layout, metrics)

# Step 9: Generate images in parallel (best-effort)
if config.floor_plan_image_enabled:
    with ThreadPoolExecutor(max_workers=2) as pool:
        arch_future = pool.submit(generate_image, arch_prompt, style="natural")
        pres_future = pool.submit(generate_image, pres_prompt, style="vivid")
    architectural_image = arch_future.result()
    presentation_image = pres_future.result()
else:
    architectural_image = None
    presentation_image = None

# Step 10: Always generate SVG fallback (fast, <100ms)
geojson = convert_ai_layout_to_geojson(ai_layout, floor_width_m, floor_depth_m)
svg = render_blueprint_svg(geojson, floor_width_m, floor_depth_m, ...)

# Step 11: Assemble response
return {
    "status": "ok",
    "source": "ai",
    "layout_json": ai_layout,
    "architectural_image": architectural_image,  # base64 or null
    "presentation_image": presentation_image,    # base64 or null
    "svg_blueprint": svg,                        # always present
    "metrics": metrics,
    "design_notes": design_notes,
}
```

### `backend/ai_layer/config.py`

New fields:
```python
floor_plan_image_enabled: bool = True
dalle_model: str = "dall-e-3"
dalle_size: str = "1792x1024"
dalle_quality: str = "hd"
dalle_timeout_s: float = 30.0
```

---

## 4. API Response Shape

```json
{
  "status": "ok",
  "source": "ai",
  "layout_json": {
    "core": { "x": 10.0, "y": 0.0, "w": 4.5, "h": 12.0, ... },
    "corridor": { "x": 0.0, "y": 5.25, "w": 24.0, "h": 1.5 },
    "units": [ ... ],
    "design_notes": "..."
  },
  "architectural_image": "<base64 PNG or null>",
  "presentation_image": "<base64 PNG or null>",
  "svg_blueprint": "<SVG string, always present>",
  "metrics": {
    "footprintSqm": 611.7,
    "nUnitsPerFloor": 2,
    "nTotalUnits": 32,
    "efficiencyPct": 92.3,
    "coreSqm": 73.4,
    "corridorSqm": 47.1,
    "netBuaSqm": 9033,
    "grossBuaSqm": 9787,
    "nLifts": 2,
    "nStairs": 2,
    "nFloors": 16,
    "buildingHeightM": 48
  },
  "design_notes": "Dual 3BHK floor plate with central core..."
}
```

---

## 5. Frontend Changes

### `frontend/src/services/plannerService.ts`

Updated response type:
```typescript
export interface AIFloorPlanResponse {
  status: "ok" | "error";
  source: "ai";
  layout_json: Record<string, unknown>;
  architectural_image: string | null;   // base64 PNG
  presentation_image: string | null;    // base64 PNG
  svg_blueprint: string;                // SVG fallback, always present
  metrics: AIFloorPlanMetrics;
  design_notes: string;
  error?: string;
}
```

### Display Component (both routes)

The floor plan viewer (used by `DirectFloorPlanView`, `FloorCanvas`, and `FloorPlanningView`) changes:

1. **View toggle:** Two tabs at top — "Architectural" | "Presentation"
   - Default: Architectural
   - If one image is null, that tab is hidden
   - If both null, fall back to SVG viewer

2. **Image viewer:** Replaces `ZoomableSvgViewer`
   - Renders `<img src="data:image/png;base64,..." />`
   - Same pan/zoom behavior (mouse wheel zoom, drag to pan)
   - Fit-to-view, zoom in/out, reset buttons

3. **Fallback logic:**
   ```
   if (architectural_image || presentation_image) → show image viewer with toggle
   else if (svg_blueprint) → show SVG viewer (current behavior)
   else → show error state
   ```

4. **Metrics sidebar:** unchanged — reads from `metrics` field

### Shared image viewer component

A new `ZoomableImageViewer` component is extracted into its own file (`frontend/src/modules/planner/components/ZoomableImageViewer.tsx`). It provides:
- Pan/zoom on a base64 `<img>`
- Architectural/Presentation tab toggle
- SVG fallback when images are null
- Toolbar (zoom in/out, fit, reset)

This component is used by all three routes:
- **Main planner page** (`/planner`) — `DirectFloorPlanView` wraps `ZoomableImageViewer`
- **Workspace high-rise** (`/planner/workspace/high-rise`) — `FloorPlanningView` wraps `ZoomableImageViewer`
- **Floor plans page** (`/planner/floor-plans`) — delegates to `FloorPlanningView`

All three routes consume the same `AIFloorPlanResponse` type, so the change propagates uniformly.

---

## 6. Error Handling & Fallbacks

| Failure | Behavior |
|---------|----------|
| DALL-E content policy rejection | Log warning, return `null` for that image. SVG fallback used. |
| DALL-E timeout (>30s) | Return `null` for that image. Other image may succeed. |
| Both images fail | Frontend falls back to SVG viewer. User sees current experience. |
| LLM fails all 3 retries | Existing deterministic fallback. Its JSON also goes through image pipeline. |
| OpenAI API key missing | `floor_plan_image_enabled` effectively false. SVG only. |
| Image generation disabled via config | `floor_plan_image_enabled: false`. SVG only. No DALL-E calls. |

---

## 7. Config Toggle

In `backend/ai_layer/config.py`:
```python
floor_plan_image_enabled: bool = True
```

When `False`:
- No DALL-E calls made
- Response contains `architectural_image: null`, `presentation_image: null`
- SVG fallback is the primary output
- Identical behavior to today's pipeline
- Zero additional cost

---

## 8. Cost & Performance

| Item | Latency | Cost |
|------|---------|------|
| LLM layout JSON (existing) | 5-15s | $0.01-0.05 |
| DALL-E 3 architectural image | 10-20s | $0.08 (1792x1024 HD) |
| DALL-E 3 presentation image | 10-20s | $0.08 (1792x1024 HD) |
| SVG fallback generation | <100ms | $0 |
| **Total per generation** | **15-25s** (LLM + images in parallel) | **~$0.17-0.21** |

Images are generated in parallel with each other, and the SVG fallback is generated in parallel with images. The LLM call is sequential (must complete first). Total wall-clock time: LLM time + max(image1, image2) ≈ 15-25 seconds.

---

## 9. Files Changed Summary

### New files
| File | Purpose |
|------|---------|
| `backend/services/floor_plan_image_prompt.py` | JSON → DALL-E prompt builder (2 functions) |
| `backend/ai_layer/image_client.py` | DALL-E 3 API wrapper |
| `frontend/src/modules/planner/components/ZoomableImageViewer.tsx` | Shared image viewer with toggle + zoom + SVG fallback |

### Modified files
| File | Change |
|------|--------|
| `backend/services/ai_floor_plan_service.py` | Add image generation after validation, before response |
| `backend/ai_layer/config.py` | Add DALL-E config fields + `floor_plan_image_enabled` toggle |
| `frontend/src/services/plannerService.ts` | Update `AIFloorPlanResponse` type |
| `frontend/src/modules/planner/components/DirectFloorPlanView.tsx` | Image viewer + Architectural/Presentation toggle |
| `frontend/src/modules/planner/components/FloorPlanningView.tsx` | Same image viewer change for workspace route |

### Untouched files (kept for fallback)
| File | Reason kept |
|------|-------------|
| `backend/services/ai_to_geojson_converter.py` | SVG fallback needs GeoJSON |
| `backend/services/svg_blueprint_renderer.py` | SVG fallback renderer |
| `backend/services/ai_floor_plan_prompt.py` | LLM prompts unchanged |
| `backend/services/ai_floor_plan_validator.py` | Validation unchanged |
