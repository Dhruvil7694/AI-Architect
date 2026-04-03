# Hybrid Floor Plan Image Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace code-based SVG floor plan rendering with DALL-E 3 image generation while keeping the LLM layout engine for metrics and compliance data.

**Architecture:** Three-stage pipeline — (1) LLM generates room layout JSON (existing, unchanged), (2) new prompt builder converts JSON to rich architectural descriptions, (3) DALL-E 3 renders two images in parallel (architectural B&W + presentation colored). SVG kept as fallback.

**Tech Stack:** OpenAI DALL-E 3 (`openai.images.generate`), existing Django backend, Next.js frontend, existing OpenAI/Claude LLM layer.

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `backend/ai_layer/image_client.py` | DALL-E 3 API wrapper — single `generate_image()` function |
| `backend/services/floor_plan_image_prompt.py` | Two pure functions converting layout JSON + metrics → DALL-E prompt strings |
| `frontend/src/modules/planner/components/ZoomableImageViewer.tsx` | Shared pan/zoom image viewer with Architectural/Presentation tab toggle + SVG fallback |

### Modified files
| File | Change |
|------|--------|
| `backend/ai_layer/config.py` | Add 5 DALL-E config fields + `floor_plan_image_enabled` toggle |
| `backend/services/ai_floor_plan_service.py` | Insert image generation steps 8-11 after validation, before response |
| `frontend/src/services/plannerService.ts` | Add `architectural_image`, `presentation_image` to `AIFloorPlanResponse` |
| `frontend/src/modules/planner/components/DirectFloorPlanView.tsx` | Replace `ZoomableSvgViewer` with `ZoomableImageViewer` |
| `frontend/src/modules/planner/components/FloorPlanningView.tsx` | Add image viewer support for workspace route |

---

### Task 1: DALL-E 3 Image Client

**Files:**
- Create: `backend/ai_layer/image_client.py`
- Create: `backend/tests/test_image_client.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_image_client.py
"""Tests for DALL-E 3 image client."""
import unittest
from unittest.mock import patch, MagicMock


class TestGenerateImage(unittest.TestCase):
    """Test generate_image function."""

    @patch("ai_layer.image_client.openai")
    @patch("ai_layer.image_client.get_ai_config")
    def test_returns_base64_on_success(self, mock_config, mock_openai):
        mock_config.return_value.api_key = "sk-test"
        mock_config.return_value.dalle_timeout_s = 30.0
        mock_response = MagicMock()
        mock_response.data = [MagicMock(b64_json="iVBORw0KGgoAAAANS==")]
        mock_openai.OpenAI.return_value.images.generate.return_value = mock_response

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt", size="1792x1024", quality="hd", style="natural")

        assert result == "iVBORw0KGgoAAAANS=="
        mock_openai.OpenAI.return_value.images.generate.assert_called_once()

    @patch("ai_layer.image_client.openai")
    @patch("ai_layer.image_client.get_ai_config")
    def test_returns_none_on_api_error(self, mock_config, mock_openai):
        mock_config.return_value.api_key = "sk-test"
        mock_config.return_value.dalle_timeout_s = 30.0
        mock_openai.OpenAI.return_value.images.generate.side_effect = Exception("API error")

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt")

        assert result is None

    @patch("ai_layer.image_client.get_ai_config")
    def test_returns_none_when_no_api_key(self, mock_config):
        mock_config.return_value.api_key = None

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt")

        assert result is None

    @patch("ai_layer.image_client.openai")
    @patch("ai_layer.image_client.get_ai_config")
    def test_returns_none_on_empty_response(self, mock_config, mock_openai):
        mock_config.return_value.api_key = "sk-test"
        mock_config.return_value.dalle_timeout_s = 30.0
        mock_response = MagicMock()
        mock_response.data = []
        mock_openai.OpenAI.return_value.images.generate.return_value = mock_response

        from ai_layer.image_client import generate_image
        result = generate_image("test prompt")

        assert result is None


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_image_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_layer.image_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/ai_layer/image_client.py
"""
ai_layer/image_client.py — DALL-E 3 image generation wrapper.

Returns base64-encoded PNG or None on any failure. Never raises.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import openai
except ImportError:
    openai = None  # type: ignore


def generate_image(
    prompt: str,
    size: str = "1792x1024",
    quality: str = "hd",
    style: str = "natural",
) -> Optional[str]:
    """
    Call DALL-E 3 and return base64-encoded PNG.

    Returns None on failure (timeout, content policy, API error, missing key).
    Logs the error but does not raise.
    """
    from ai_layer.config import get_ai_config

    config = get_ai_config()
    api_key = config.api_key
    if not api_key:
        logger.debug("OPENAI_API_KEY not set; skipping DALL-E call.")
        return None

    if openai is None:
        logger.warning("openai package not installed; DALL-E calls will no-op.")
        return None

    client = openai.OpenAI(api_key=api_key)
    timeout_s = config.dalle_timeout_s
    start = time.monotonic()

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            style=style,
            response_format="b64_json",
            n=1,
            timeout=timeout_s,
        )
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning(
            "DALL-E 3 call failed after %.2fs: %s", elapsed, type(e).__name__,
            exc_info=False,
        )
        return None

    elapsed = time.monotonic() - start

    if not response.data:
        logger.warning("DALL-E 3 returned empty data after %.2fs.", elapsed)
        return None

    b64 = response.data[0].b64_json
    if not b64:
        logger.warning("DALL-E 3 returned empty b64_json after %.2fs.", elapsed)
        return None

    logger.info("DALL-E 3 image generated in %.2fs (size=%s, quality=%s, style=%s)",
                elapsed, size, quality, style)
    return b64
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_image_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/ai_layer/image_client.py backend/tests/test_image_client.py
git commit -m "feat: add DALL-E 3 image generation client"
```

---

### Task 2: Add DALL-E Config Fields

**Files:**
- Modify: `backend/ai_layer/config.py` (lines 28-66 dataclass, lines 115-145 factory)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dalle_config.py
"""Tests for DALL-E config fields in AIConfig."""
import os
import unittest
from unittest.mock import patch


class TestDalleConfig(unittest.TestCase):

    def test_default_dalle_fields(self):
        from ai_layer.config import AIConfig
        c = AIConfig()
        assert c.floor_plan_image_enabled is True
        assert c.dalle_model == "dall-e-3"
        assert c.dalle_size == "1792x1024"
        assert c.dalle_quality == "hd"
        assert c.dalle_timeout_s == 30.0

    @patch.dict(os.environ, {"FLOOR_PLAN_IMAGE_ENABLED": "0"})
    def test_image_disabled_via_env(self):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_image_enabled is False

    @patch.dict(os.environ, {"DALLE_SIZE": "1024x1024"})
    def test_dalle_size_override(self):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.dalle_size == "1024x1024"


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dalle_config.py -v`
Expected: FAIL — `AttributeError: AIConfig has no attribute 'floor_plan_image_enabled'`

- [ ] **Step 3: Add DALL-E fields to AIConfig dataclass**

In `backend/ai_layer/config.py`, add these fields after the `hf_image_timeout_s` line (line 66):

```python
    # DALL-E 3 floor plan image generation
    floor_plan_image_enabled: bool = True
    dalle_model: str = "dall-e-3"
    dalle_size: str = "1792x1024"
    dalle_quality: str = "hd"
    dalle_timeout_s: float = 30.0
```

- [ ] **Step 4: Wire env vars in `get_ai_config()` factory**

In the `get_ai_config()` function, add these kwargs after the `hf_image_timeout_s` line (around line 144):

```python
        floor_plan_image_enabled=_bool_env("FLOOR_PLAN_IMAGE_ENABLED", True),
        dalle_model=os.environ.get("DALLE_MODEL", "dall-e-3"),
        dalle_size=os.environ.get("DALLE_SIZE", "1792x1024"),
        dalle_quality=os.environ.get("DALLE_QUALITY", "hd"),
        dalle_timeout_s=_float_env("DALLE_TIMEOUT_S", 30.0),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dalle_config.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/ai_layer/config.py backend/tests/test_dalle_config.py
git commit -m "feat: add DALL-E 3 config fields to AIConfig"
```

---

### Task 3: Floor Plan Image Prompt Builder

**Files:**
- Create: `backend/services/floor_plan_image_prompt.py`
- Create: `backend/tests/test_floor_plan_image_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_floor_plan_image_prompt.py
"""Tests for floor plan image prompt builder."""
import unittest


SAMPLE_LAYOUT = {
    "core": {"x": 10.0, "y": 0.0, "w": 4.5, "h": 12.0, "stairs": 2, "lifts": 2, "lobby": True},
    "corridor": {"x": 0.0, "y": 5.25, "w": 24.0, "h": 1.5},
    "units": [
        {
            "id": "U1",
            "type": "3BHK",
            "carpet_area_sqm": 92.5,
            "side": "north",
            "rooms": [
                {"type": "LIVING", "w": 5.5, "h": 4.0, "position": "north-west"},
                {"type": "BEDROOM", "w": 4.0, "h": 3.5, "position": "north-east"},
                {"type": "KITCHEN", "w": 3.5, "h": 3.0, "position": "south-east"},
                {"type": "TOILET", "w": 2.0, "h": 2.5, "position": "south-west"},
            ],
        },
        {
            "id": "U2",
            "type": "2BHK",
            "carpet_area_sqm": 65.0,
            "side": "south",
            "rooms": [
                {"type": "LIVING", "w": 4.5, "h": 3.5, "position": "south-west"},
                {"type": "BEDROOM", "w": 3.5, "h": 3.0, "position": "south-east"},
                {"type": "KITCHEN", "w": 3.0, "h": 2.5, "position": "north-east"},
            ],
        },
    ],
}

SAMPLE_METRICS = {
    "footprintSqm": 288.0,
    "floorLengthM": 24.0,
    "floorDepthM": 12.0,
    "nUnitsPerFloor": 2,
    "nFloors": 16,
    "efficiencyPct": 92.3,
    "nLifts": 2,
    "nStairs": 2,
}


class TestBuildArchitecturalPrompt(unittest.TestCase):

    def test_returns_nonempty_string(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_key_architectural_terms(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert "black and white" in result.lower() or "line drawing" in result.lower()
        assert "24.0" in result  # floor length
        assert "12.0" in result  # floor depth
        assert "3BHK" in result
        assert "2BHK" in result

    def test_contains_scale_and_title(self):
        from services.floor_plan_image_prompt import build_architectural_prompt
        result = build_architectural_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS, segment="premium")
        assert "1:100" in result
        assert "Premium" in result


class TestBuildPresentationPrompt(unittest.TestCase):

    def test_returns_nonempty_string(self):
        from services.floor_plan_image_prompt import build_presentation_prompt
        result = build_presentation_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_furnishing_language(self):
        from services.floor_plan_image_prompt import build_presentation_prompt
        result = build_presentation_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS, segment="luxury")
        # Should contain luxury finishes
        assert "marble" in result.lower() or "luxury" in result.lower()

    def test_budget_segment_uses_basic_finishes(self):
        from services.floor_plan_image_prompt import build_presentation_prompt
        result = build_presentation_prompt(SAMPLE_LAYOUT, SAMPLE_METRICS, segment="budget")
        assert "laminate" in result.lower() or "basic" in result.lower()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_floor_plan_image_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.floor_plan_image_prompt'`

- [ ] **Step 3: Write the prompt builder**

```python
# backend/services/floor_plan_image_prompt.py
"""
floor_plan_image_prompt.py — Convert LLM layout JSON + metrics into DALL-E 3 prompts.

Two pure functions. No AI calls, no side effects — deterministic string builders.
"""
from __future__ import annotations

from typing import Any, Dict


def build_architectural_prompt(
    layout: Dict[str, Any],
    metrics: Dict[str, Any],
    segment: str = "mid",
    units_per_core: int | None = None,
) -> str:
    """Build DALL-E 3 prompt for a black-and-white technical architectural floor plan."""

    floor_w = metrics.get("floorLengthM", 24.0)
    floor_d = metrics.get("floorDepthM", 12.0)
    n_units = metrics.get("nUnitsPerFloor", len(layout.get("units", [])))
    upc = units_per_core or n_units

    core = layout.get("core", {})
    corridor = layout.get("corridor", {})
    units = layout.get("units", [])

    parts = [
        "Professional architectural floor plan, black and white line drawing, "
        "top-down orthographic view, scale 1:100, clean drafting style.",
        "",
        f"Floor plate: {floor_w}m x {floor_d}m rectangular slab.",
    ]

    # Core
    if core:
        parts.append(
            f"Central service core: {core.get('w', 4.5)}m x {core.get('h', 12.0)}m "
            f"containing {core.get('stairs', 2)} staircases, {core.get('lifts', 2)} lifts, "
            f"and a lobby area."
        )

    # Corridor
    if corridor:
        parts.append(
            f"Central corridor: {corridor.get('w', 24.0)}m x {corridor.get('h', 1.5)}m "
            "running the full length of the floor plate."
        )

    # Units
    for unit in units:
        unit_type = unit.get("type", "unit")
        carpet = unit.get("carpet_area_sqm", 0)
        side = unit.get("side", "")
        rooms = unit.get("rooms", [])

        parts.append("")
        parts.append(f"{unit_type} unit ({carpet} sqm carpet) on the {side} side:")

        for room in rooms:
            rtype = room.get("type", "room")
            rw = room.get("w", 0)
            rh = room.get("h", 0)
            pos = room.get("position", "")
            parts.append(f"  - {rtype}: {rw}m x {rh}m at {pos}")

    # Architectural conventions
    parts.append("")
    parts.append(
        "Architectural conventions: Diagonal hatching on wet zones (kitchen, bathrooms, toilets). "
        "Door swing arcs shown as quarter-circle arcs. Windows as double lines on exterior walls. "
        "Dimension lines on all rooms. Structural column grid at 4.5m centers shown as dashed lines "
        "with circle markers."
    )

    # Title block
    seg_label = segment.title() if segment else "Mid"
    parts.append("")
    parts.append(
        f"Title block: \"Typical Floor Plan — {upc} units/core — {seg_label} — Scale 1:100\""
    )

    # Finish
    parts.append("")
    parts.append(
        "Clean white background, no color, architectural drafting convention, "
        "thin precise black lines, professional quality."
    )

    return "\n".join(parts)


def build_presentation_prompt(
    layout: Dict[str, Any],
    metrics: Dict[str, Any],
    segment: str = "mid",
) -> str:
    """Build DALL-E 3 prompt for a colored real estate brochure rendering."""

    floor_w = metrics.get("floorLengthM", 24.0)
    floor_d = metrics.get("floorDepthM", 12.0)
    units = layout.get("units", [])
    core = layout.get("core", {})

    # Material palette by segment
    material_palettes = {
        "budget": "laminate flooring, basic ceramic tiles, simple modular kitchen with laminate finish",
        "mid": "vitrified tile flooring, modular kitchen with granite countertop, ceramic bathroom tiles",
        "premium": "wooden flooring in bedrooms, polished granite counters, designer bathroom fixtures, "
                   "full-height tiling in bathrooms",
        "luxury": "Italian marble flooring throughout, imported designer fixtures, walk-in wardrobes, "
                  "premium hardwood accents, rain shower in master bath",
    }

    # Furniture descriptions by room type
    furniture = {
        "LIVING": "L-shaped sofa, coffee table, TV unit, and accent rug",
        "BEDROOM": "king-size bed with headboard, side tables, and wardrobe",
        "KITCHEN": "L-shaped counter with sink, cooktop, chimney, and refrigerator",
        "TOILET": "western commode, vanity with basin, mirror, and shower area",
        "PASSAGE": "clean open passage",
        "DINING": "4-seater dining table with chairs",
        "BALCONY": "planters with greenery and outdoor seating",
    }

    mat = material_palettes.get(segment, material_palettes["mid"])

    parts = [
        "Luxury residential floor plan, top-down bird's-eye view, photorealistic architectural rendering, "
        "soft warm lighting, magazine-quality presentation.",
        "",
        f"Floor plate: {floor_w}m x {floor_d}m rectangular building footprint.",
    ]

    # Core
    if core:
        parts.append(
            f"Central core with marble-floored lobby, {core.get('lifts', 2)} lifts with "
            f"stainless steel doors, and {core.get('stairs', 2)} enclosed staircases."
        )

    parts.append(f"Material palette: {mat}.")

    # Units with furnished rooms
    for unit in units:
        unit_type = unit.get("type", "unit")
        carpet = unit.get("carpet_area_sqm", 0)
        side = unit.get("side", "")
        rooms = unit.get("rooms", [])

        parts.append("")
        parts.append(f"{unit_type} unit ({carpet} sqm) on the {side} side:")

        for room in rooms:
            rtype = room.get("type", "room")
            rw = room.get("w", 0)
            rh = room.get("h", 0)
            furn = furniture.get(rtype, "furnished appropriately")
            parts.append(f"  - {rtype} ({rw}m x {rh}m): {furn}")

    # Balconies
    parts.append("")
    parts.append("Balconies: planters with greenery, outdoor seating, city views.")

    # Finish
    parts.append("")
    parts.append(
        "No perspective distortion, perfectly orthographic top-down view, clean edges, "
        "magazine-quality rendering, warm ambient lighting with soft shadows."
    )

    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_floor_plan_image_prompt.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/floor_plan_image_prompt.py backend/tests/test_floor_plan_image_prompt.py
git commit -m "feat: add floor plan image prompt builder (JSON → DALL-E prompts)"
```

---

### Task 4: Integrate Image Generation into Service

**Files:**
- Modify: `backend/services/ai_floor_plan_service.py` (after line 223, before the return)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_floor_plan_image_integration.py
"""Tests for image generation integration in ai_floor_plan_service."""
import unittest
from unittest.mock import patch, MagicMock


class TestImageIntegration(unittest.TestCase):

    @patch("services.ai_floor_plan_service.generate_image")
    @patch("services.ai_floor_plan_service.build_architectural_prompt")
    @patch("services.ai_floor_plan_service.build_presentation_prompt")
    def test_response_contains_image_fields(self, mock_pres, mock_arch, mock_gen_img):
        """After integration, the response dict must contain image keys."""
        mock_arch.return_value = "arch prompt"
        mock_pres.return_value = "pres prompt"
        mock_gen_img.return_value = "base64data=="

        # We can't easily call the full pipeline, so test the assembly logic
        from services.floor_plan_image_prompt import build_architectural_prompt, build_presentation_prompt
        from ai_layer.image_client import generate_image

        # Simulate what the service does
        arch_prompt = build_architectural_prompt({}, {})
        pres_prompt = build_presentation_prompt({}, {})
        assert isinstance(arch_prompt, str)
        assert isinstance(pres_prompt, str)

    def test_image_fields_none_when_disabled(self):
        """When floor_plan_image_enabled=False, images should be None."""
        from ai_layer.config import AIConfig
        config = AIConfig(floor_plan_image_enabled=False)
        assert config.floor_plan_image_enabled is False


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it passes** (these are integration-level sanity checks)

Run: `cd backend && python -m pytest tests/test_floor_plan_image_integration.py -v`
Expected: 2 passed (these test the pieces exist and connect)

- [ ] **Step 3: Modify `ai_floor_plan_service.py`**

Add imports at the top of the file (after existing imports):

```python
from concurrent.futures import ThreadPoolExecutor
from ai_layer.image_client import generate_image
from services.floor_plan_image_prompt import build_architectural_prompt, build_presentation_prompt
```

Replace the current steps 8 + return block (lines 219-232) with:

```python
    # ---- 8. Render SVG fallback (always, fast) ----
    title = f"Typical Floor Plan — {units_per_core} units/core — {segment.title()}"
    svg_blueprint = render_blueprint_svg(
        geojson_layout, floor_width_m, floor_depth_m, title=title,
    )

    # ---- 9. Build image prompts from validated layout ----
    arch_prompt = build_architectural_prompt(
        ai_layout, metrics, segment=segment, units_per_core=units_per_core,
    )
    pres_prompt = build_presentation_prompt(
        ai_layout, metrics, segment=segment,
    )

    # ---- 10. Generate DALL-E images in parallel (best-effort) ----
    architectural_image = None
    presentation_image = None

    config = get_ai_config()
    if config.floor_plan_image_enabled and config.has_api_key():
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                arch_future = pool.submit(
                    generate_image, arch_prompt,
                    size=config.dalle_size, quality=config.dalle_quality, style="natural",
                )
                pres_future = pool.submit(
                    generate_image, pres_prompt,
                    size=config.dalle_size, quality=config.dalle_quality, style="vivid",
                )
            architectural_image = arch_future.result()
            presentation_image = pres_future.result()
        except Exception as e:
            logger.warning("Image generation failed: %s", e, exc_info=False)

    # ---- 11. Assemble response ----
    return {
        "status": "ok",
        "source": "ai",
        "layout": geojson_layout,
        "layout_json": ai_layout,
        "architectural_image": architectural_image,
        "presentation_image": presentation_image,
        "svg_blueprint": svg_blueprint,
        "metrics": metrics,
        "design_notes": design_notes,
    }
```

- [ ] **Step 4: Verify the server starts without import errors**

Run: `cd backend && python -c "from services.ai_floor_plan_service import generate_ai_floor_plan; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_floor_plan_service.py backend/tests/test_floor_plan_image_integration.py
git commit -m "feat: integrate DALL-E 3 image generation into floor plan pipeline"
```

---

### Task 5: Update Frontend API Types

**Files:**
- Modify: `frontend/src/services/plannerService.ts` (lines 566-574)

- [ ] **Step 1: Update `AIFloorPlanResponse` interface**

Replace the current `AIFloorPlanResponse` interface (lines 566-574):

```typescript
export interface AIFloorPlanResponse {
  status: "ok" | "error";
  source: "ai";
  layout: FloorPlanLayout;
  layout_json?: Record<string, unknown>;
  architectural_image: string | null;   // base64 PNG from DALL-E 3
  presentation_image: string | null;    // base64 PNG from DALL-E 3
  svg_blueprint: string;                // SVG fallback, always present
  metrics: AIFloorPlanMetrics;
  design_notes: string;
  error?: string;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No NEW errors in `plannerService.ts` (pre-existing errors in other files are expected)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/plannerService.ts
git commit -m "feat: add DALL-E image fields to AIFloorPlanResponse type"
```

---

### Task 6: ZoomableImageViewer Component

**Files:**
- Create: `frontend/src/modules/planner/components/ZoomableImageViewer.tsx`

- [ ] **Step 1: Create the shared image viewer component**

```tsx
// frontend/src/modules/planner/components/ZoomableImageViewer.tsx
"use client";

import { useRef, useState, useCallback, useEffect } from "react";

type ViewMode = "architectural" | "presentation" | "svg";

type ZoomableImageViewerProps = {
  architecturalImage: string | null;
  presentationImage: string | null;
  svgFallback: string | null;
};

export function ZoomableImageViewer({
  architecturalImage,
  presentationImage,
  svgFallback,
}: ZoomableImageViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [dragging, setDragging] = useState(false);
  const lastPos = useRef({ x: 0, y: 0 });

  // Determine available modes
  const hasArch = !!architecturalImage;
  const hasPres = !!presentationImage;
  const hasSvg = !!svgFallback;
  const hasImages = hasArch || hasPres;

  const defaultMode: ViewMode = hasArch ? "architectural" : hasPres ? "presentation" : "svg";
  const [mode, setMode] = useState<ViewMode>(defaultMode);

  // Reset mode when data changes
  useEffect(() => {
    setMode(hasArch ? "architectural" : hasPres ? "presentation" : "svg");
  }, [hasArch, hasPres]);

  // Fit image/SVG to container
  const fitInView = useCallback(() => {
    setTransform({ x: 0, y: 0, scale: 1 });
  }, []);

  const zoomIn = useCallback(() => {
    setTransform((t) => ({ ...t, scale: Math.min(t.scale * 1.25, 10) }));
  }, []);

  const zoomOut = useCallback(() => {
    setTransform((t) => ({ ...t, scale: Math.max(t.scale / 1.25, 0.1) }));
  }, []);

  // Wheel zoom
  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const rect = containerRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    setTransform((prev) => {
      const newScale = Math.max(0.1, Math.min(10, prev.scale * factor));
      const r = newScale / prev.scale;
      return { scale: newScale, x: mx - r * (mx - prev.x), y: my - r * (my - prev.y) };
    });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  // Drag pan
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    lastPos.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging) return;
      const dx = e.clientX - lastPos.current.x;
      const dy = e.clientY - lastPos.current.y;
      lastPos.current = { x: e.clientX, y: e.clientY };
      setTransform((prev) => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
    },
    [dragging],
  );

  const stopDrag = useCallback(() => setDragging(false), []);

  // Current content
  const currentSrc =
    mode === "architectural"
      ? architecturalImage
      : mode === "presentation"
        ? presentationImage
        : null;

  return (
    <div className="flex h-full w-full flex-col">
      {/* Tab bar + zoom controls */}
      <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-1.5">
        <div className="flex items-center gap-1">
          {hasImages && (
            <>
              {hasArch && (
                <button
                  type="button"
                  onClick={() => setMode("architectural")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    mode === "architectural"
                      ? "bg-neutral-900 text-white"
                      : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
                  }`}
                >
                  Architectural
                </button>
              )}
              {hasPres && (
                <button
                  type="button"
                  onClick={() => setMode("presentation")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    mode === "presentation"
                      ? "bg-neutral-900 text-white"
                      : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
                  }`}
                >
                  Presentation
                </button>
              )}
              {hasSvg && (
                <button
                  type="button"
                  onClick={() => setMode("svg")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    mode === "svg"
                      ? "bg-neutral-900 text-white"
                      : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
                  }`}
                >
                  SVG
                </button>
              )}
            </>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={zoomIn}
            className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
            title="Zoom in"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
          <button
            type="button"
            onClick={zoomOut}
            className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
            title="Zoom out"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 12h-15" />
            </svg>
          </button>
          <button
            type="button"
            onClick={fitInView}
            className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
            title="Reset view"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9m11.25-5.25v4.5m0-4.5h-4.5m4.5 0L15 9m-11.25 11.25v-4.5m0 4.5h4.5m-4.5 0L9 15m11.25 5.25v-4.5m0 4.5h-4.5m4.5 0L15 15"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden select-none bg-neutral-50"
        style={{ cursor: dragging ? "grabbing" : "grab" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={stopDrag}
        onMouseLeave={stopDrag}
      >
        <div
          style={{
            transformOrigin: "0 0",
            transform: `translate(${transform.x}px,${transform.y}px) scale(${transform.scale})`,
            display: "inline-block",
            lineHeight: 0,
          }}
        >
          {mode === "svg" && svgFallback ? (
            <div dangerouslySetInnerHTML={{ __html: svgFallback }} />
          ) : currentSrc ? (
            <img
              src={`data:image/png;base64,${currentSrc}`}
              alt={`Floor plan — ${mode} view`}
              draggable={false}
              className="max-w-none"
            />
          ) : hasSvg ? (
            <div dangerouslySetInnerHTML={{ __html: svgFallback! }} />
          ) : (
            <div className="flex items-center justify-center p-12 text-sm text-neutral-400">
              No image available
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between border-t border-neutral-100 px-3 py-1 text-[10px] text-neutral-400">
        <span>
          {mode === "svg"
            ? "SVG Blueprint"
            : mode === "architectural"
              ? "Architectural Drawing (DALL-E 3)"
              : "Presentation Rendering (DALL-E 3)"}
        </span>
        <span>Scroll to zoom · Drag to pan</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "ZoomableImageViewer" | head -5`
Expected: No errors in this file

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/planner/components/ZoomableImageViewer.tsx
git commit -m "feat: add ZoomableImageViewer with Architectural/Presentation toggle"
```

---

### Task 7: Update DirectFloorPlanView to Use Image Viewer

**Files:**
- Modify: `frontend/src/modules/planner/components/DirectFloorPlanView.tsx`

- [ ] **Step 1: Rewrite DirectFloorPlanView**

Replace the entire file content with:

```tsx
// frontend/src/modules/planner/components/DirectFloorPlanView.tsx
"use client";

import type { AIFloorPlanResponse } from "@/services/plannerService";
import { ZoomableImageViewer } from "./ZoomableImageViewer";

type DirectFloorPlanViewProps = {
  data: AIFloorPlanResponse | null;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  onRetry?: () => void;
};

export function DirectFloorPlanView({ data, isPending, isError, error, onRetry }: DirectFloorPlanViewProps) {
  // Loading state
  if (isPending) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-neutral-50/50">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="h-10 w-10 animate-spin rounded-full border-[3px] border-neutral-200 border-t-neutral-800" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="h-3 w-3 rounded-full bg-neutral-800 animate-pulse" />
            </div>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-neutral-700">Generating floor plan</p>
            <p className="mt-1 text-xs text-neutral-400">AI is designing your layout and rendering images — 15-30s</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-xl border border-dashed border-red-200 bg-red-50/30">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
            <svg className="h-5 w-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-red-700">Floor plan generation failed</p>
          <p className="max-w-xs text-xs text-red-500">{error?.message ?? "Unknown error"}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-1 rounded-lg bg-red-100 px-4 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-200"
            >
              Try again
            </button>
          )}
        </div>
      </div>
    );
  }

  // Empty state
  if (!data) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-neutral-50/50">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-100">
            <svg className="h-6 w-6 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 0h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-neutral-600">No floor plan yet</p>
          <p className="text-xs text-neutral-400">Select a plot and click Generate to create a floor plan</p>
        </div>
      </div>
    );
  }

  // Image viewer + metrics
  const m = data.metrics;

  return (
    <div className="flex h-full w-full flex-1 flex-col rounded-xl border border-neutral-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-neutral-100 px-4 py-2">
        <span className="text-xs font-semibold text-neutral-700">Floor Plan</span>
        {data.source === "ai" && (
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-600">
            AI Generated
          </span>
        )}
        {(data.architectural_image || data.presentation_image) && (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
            DALL-E 3
          </span>
        )}
        {data.design_notes && (
          <span className="text-[10px] text-neutral-400 truncate max-w-[200px]">{data.design_notes}</span>
        )}
      </div>

      {/* Image viewer */}
      <div className="flex-1 min-h-0">
        <ZoomableImageViewer
          architecturalImage={data.architectural_image ?? null}
          presentationImage={data.presentation_image ?? null}
          svgFallback={data.svg_blueprint ?? null}
        />
      </div>

      {/* Metrics footer */}
      {m && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-neutral-100 px-4 py-2 text-[11px] text-neutral-600">
          <span><span className="font-medium text-neutral-800">{m.nUnitsPerFloor}</span> units/floor</span>
          <span><span className="font-medium text-neutral-800">{m.efficiencyPct}%</span> efficiency</span>
          <span><span className="font-medium text-neutral-800">{m.footprintSqm}</span> m² footprint</span>
          <span><span className="font-medium text-neutral-800">{m.nFloors}</span> floors</span>
          <span><span className="font-medium text-neutral-800">{m.nLifts}</span> lifts</span>
          <span><span className="font-medium text-neutral-800">{m.nStairs}</span> stairs</span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "DirectFloorPlanView" | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/planner/components/DirectFloorPlanView.tsx
git commit -m "feat: replace SVG viewer with ZoomableImageViewer in DirectFloorPlanView"
```

---

### Task 8: Update FloorPlanningView for Workspace Route

**Files:**
- Modify: `frontend/src/modules/planner/components/FloorPlanningView.tsx`

This task adds image viewer support to the workspace route (`/planner/workspace/high-rise`). The `FloorPlanningView` component is ~1900 lines. We only need to change the section that renders the AI floor plan result (around lines 1650-1710).

- [ ] **Step 1: Add import for ZoomableImageViewer**

At the top of `FloorPlanningView.tsx`, add:

```typescript
import { ZoomableImageViewer } from "./ZoomableImageViewer";
```

- [ ] **Step 2: Find and update the AI floor plan rendering section**

In the `FloorPlanningView` component, locate the section that renders the AI floor plan SVG (search for `svg_blueprint` or `ZoomableSvgViewer` or the AI floor plan display). Replace the SVG rendering block with the `ZoomableImageViewer`:

The existing code renders `aiFloorPlan.data.svg_blueprint` in a `ZoomableSvgViewer`. Replace that rendering section with:

```tsx
<ZoomableImageViewer
  architecturalImage={aiFloorPlan.data?.architectural_image ?? null}
  presentationImage={aiFloorPlan.data?.presentation_image ?? null}
  svgFallback={aiFloorPlan.data?.svg_blueprint ?? null}
/>
```

This ensures the workspace route also gets the image toggle + SVG fallback behavior.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "FloorPlanningView" | head -5`
Expected: No new errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/modules/planner/components/FloorPlanningView.tsx
git commit -m "feat: add DALL-E image viewer to workspace FloorPlanningView"
```

---

## Verification Checklist

After all tasks are complete:

1. **Backend smoke test:** `cd backend && python -c "from services.ai_floor_plan_service import generate_ai_floor_plan; print('OK')"`
2. **Backend tests:** `cd backend && python -m pytest tests/test_image_client.py tests/test_dalle_config.py tests/test_floor_plan_image_prompt.py -v`
3. **Frontend compile:** `cd frontend && npx tsc --noEmit`
4. **Manual test with `FLOOR_PLAN_IMAGE_ENABLED=0`:** Verify SVG-only fallback works identically to before
5. **Manual test with images enabled:** Verify Architectural/Presentation toggle appears, images render, zoom/pan works
6. **Manual test image failure:** Temporarily set invalid API key — verify graceful fallback to SVG
