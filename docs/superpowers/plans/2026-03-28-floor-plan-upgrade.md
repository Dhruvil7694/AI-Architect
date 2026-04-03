# Floor Plan Generation Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the floor plan generator from rigid 4-zone strip layouts to AI-driven room-level layouts with GDCR compliance and professional SVG rendering.

**Architecture:** The AI (Claude or GPT-4o, admin-switchable) receives GDCR regulation context and architectural design principles as system prompt, then generates complete room-level JSON for all units. A deterministic validator snaps coordinates, enforces GDCR minimums, aligns wet stacks, and checks room completeness. The SVG renderer is rewritten with professional line weights, distinct hatching, structural grid, and proper drawing elements.

**Tech Stack:** Django, Python 3.11+, Anthropic SDK (`anthropic`), OpenAI SDK (`openai`), SVG generation (xml.sax)

**Spec:** `docs/superpowers/specs/2026-03-28-floor-plan-upgrade-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/ai_layer/config.py` | Add Claude API key, model toggle, updated floor plan config |
| `backend/ai_layer/client.py` | Add `call_claude()` function + unified `call_llm()` dispatcher |
| `backend/services/ai_floor_plan_prompt.py` | Complete rewrite — GDCR-aware system prompt with skills content, room-level output schema |
| `backend/services/ai_floor_plan_validator.py` | Expand — room completeness check, ventilation check, GDCR area enforcement per room |
| `backend/services/ai_floor_plan_service.py` | Refactor — AI generates rooms directly, validator replaces layout engine |
| `backend/services/ai_to_geojson_converter.py` | Minor update — handle `passage`, `attached_bath` room types |
| `backend/services/svg_blueprint_renderer.py` | Major rewrite — hatching, line weights, north arrow, structural grid, title block |
| `backend/requirements.txt` | Add `anthropic>=0.40` |
| `backend/tests/test_floor_plan_validator.py` | New — unit tests for expanded validator |
| `backend/tests/test_floor_plan_prompt.py` | New — unit tests for prompt builder |
| `backend/tests/test_svg_renderer.py` | New — unit tests for SVG renderer |

---

### Task 1: Add Anthropic SDK dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add anthropic to requirements.txt**

Add the `anthropic` package after the existing `openai` line in `backend/requirements.txt`:

```
# LLM — room layout generation (Stage 3)
openai>=1.0
anthropic>=0.40
```

- [ ] **Step 2: Install the dependency**

Run: `cd backend && pip install anthropic>=0.40`
Expected: Successfully installed anthropic

- [ ] **Step 3: Verify import works**

Run: `cd backend && python -c "import anthropic; print(anthropic.__version__)"`
Expected: Prints version number (e.g., `0.42.0`)

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add anthropic SDK dependency for Claude floor plan generation"
```

---

### Task 2: Extend AI layer config with Claude support

**Files:**
- Modify: `backend/ai_layer/config.py`
- Test: `backend/tests/test_floor_plan_prompt.py` (config portion)

- [ ] **Step 1: Write failing test for Claude config fields**

Create `backend/tests/test_ai_config.py`:

```python
"""Tests for ai_layer/config.py — Claude + model toggle support."""

import os
import pytest
from unittest.mock import patch


def test_config_has_claude_api_key():
    """AIConfig exposes claude_api_key from environment."""
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test-123"}):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.claude_api_key == "sk-test-123"


def test_config_floor_plan_model_default():
    """Default floor plan AI model is 'claude'."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FLOOR_PLAN_AI_MODEL", None)
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_ai_model == "claude"


def test_config_floor_plan_model_env_override():
    """FLOOR_PLAN_AI_MODEL env var overrides default."""
    with patch.dict(os.environ, {"FLOOR_PLAN_AI_MODEL": "gpt-4o"}):
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_ai_model == "gpt-4o"


def test_config_floor_plan_max_tokens_increased():
    """Floor plan max tokens default is 8192 (up from 4096)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_FLOOR_PLAN_MAX_TOKENS", None)
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_max_tokens == 8192


def test_config_floor_plan_timeout_increased():
    """Floor plan timeout default is 60s (up from 45s)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_FLOOR_PLAN_TIMEOUT_S", None)
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        assert config.floor_plan_timeout_s == 60.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ai_config.py -v`
Expected: FAIL — `AIConfig` has no `claude_api_key` or `floor_plan_ai_model` attributes

- [ ] **Step 3: Add Claude fields to AIConfig**

In `backend/ai_layer/config.py`, add to the `AIConfig` dataclass (after line 56):

```python
    # Claude / model toggle
    floor_plan_ai_model: str = "claude"  # "claude" | "gpt-4o"
    claude_model: str = "claude-sonnet-4-6"
    claude_timeout_s: float = 60.0
    claude_max_tokens: int = 8192
```

Add the `claude_api_key` property (after the existing `api_key` property, line 74):

```python
    @property
    def claude_api_key(self) -> Optional[str]:
        return os.environ.get("CLAUDE_API_KEY")

    def has_claude_api_key(self) -> bool:
        return bool(self.claude_api_key)
```

Update `get_ai_config()` to read new env vars. In the `return AIConfig(...)` block, add:

```python
        floor_plan_ai_model=os.environ.get("FLOOR_PLAN_AI_MODEL", "claude"),
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        claude_timeout_s=_float_env("CLAUDE_TIMEOUT_S", 60.0),
        claude_max_tokens=_int_env("CLAUDE_MAX_TOKENS", 8192),
```

Update the existing floor plan defaults:

```python
        floor_plan_timeout_s=_float_env("AI_FLOOR_PLAN_TIMEOUT_S", 60.0),  # was 45.0
        floor_plan_max_tokens=_int_env("AI_FLOOR_PLAN_MAX_TOKENS", 8192),  # was 4096
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_ai_config.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ai_layer/config.py backend/tests/test_ai_config.py
git commit -m "feat: add Claude API config and model toggle to AIConfig"
```

---

### Task 3: Add Claude API client function

**Files:**
- Modify: `backend/ai_layer/client.py`
- Test: `backend/tests/test_ai_client.py`

- [ ] **Step 1: Write failing test for call_claude**

Create `backend/tests/test_ai_client.py`:

```python
"""Tests for ai_layer/client.py — Claude client + unified call_llm."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_call_claude_returns_none_without_key():
    """call_claude returns None when CLAUDE_API_KEY is not set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CLAUDE_API_KEY", None)
        from ai_layer.client import call_claude
        result = call_claude(
            model="claude-sonnet-4-6",
            system_prompt="test",
            user_prompt="test",
        )
        assert result is None


def test_call_claude_returns_text_on_success():
    """call_claude returns message text when API call succeeds."""
    mock_client_cls = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"units": []}')]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_client_cls.return_value.messages.create.return_value = mock_response

    with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test"}):
        with patch("ai_layer.client.anthropic") as mock_mod:
            mock_mod.Anthropic = mock_client_cls
            from importlib import reload
            import ai_layer.client as client_mod
            reload(client_mod)
            result = client_mod.call_claude(
                model="claude-sonnet-4-6",
                system_prompt="You are an architect",
                user_prompt="Generate layout",
                max_tokens=8192,
            )
            assert result == '{"units": []}'


def test_call_llm_routes_to_claude():
    """call_llm with model='claude' routes to call_claude."""
    with patch("ai_layer.client.call_claude", return_value='{"test": true}') as mock_claude:
        from importlib import reload
        import ai_layer.client as client_mod
        reload(client_mod)
        result = client_mod.call_llm(
            model_choice="claude",
            system_prompt="sys",
            user_prompt="usr",
        )
        mock_claude.assert_called_once()
        assert result == '{"test": true}'


def test_call_llm_routes_to_openai():
    """call_llm with model='gpt-4o' routes to call_openai."""
    with patch("ai_layer.client.call_openai", return_value='{"test": true}') as mock_openai:
        from importlib import reload
        import ai_layer.client as client_mod
        reload(client_mod)
        result = client_mod.call_llm(
            model_choice="gpt-4o",
            system_prompt="sys",
            user_prompt="usr",
        )
        mock_openai.assert_called_once()
        assert result == '{"test": true}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ai_client.py -v`
Expected: FAIL — `call_claude` and `call_llm` don't exist

- [ ] **Step 3: Implement call_claude and call_llm**

Add to `backend/ai_layer/client.py` after the existing `call_openai` function (after line 108):

```python
try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore


def call_claude(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: float = 60.0,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> Optional[str]:
    """
    Call Anthropic Claude Messages API. Returns raw response text or None on failure.
    """
    if anthropic is None:
        logger.warning("anthropic package not installed; Claude calls will no-op.")
        return None

    from ai_layer.config import get_ai_config
    config = get_ai_config()
    api_key = config.claude_api_key
    if not api_key:
        logger.debug("CLAUDE_API_KEY not set; skipping Claude call.")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    start = time.monotonic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.warning("Claude API call failed after %.2fs: %s", elapsed, type(e).__name__, exc_info=False)
        return None

    elapsed = time.monotonic() - start
    if not response.content:
        logger.warning("Claude returned empty content.")
        return None

    text = response.content[0].text.strip()
    usage = getattr(response, "usage", None)
    if usage:
        logger.info(
            "Claude model=%s usage: input_tokens=%s output_tokens=%s (%.2fs)",
            model, getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None), elapsed,
        )
    return text


def call_llm(
    model_choice: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: float = 60.0,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> Optional[str]:
    """
    Unified LLM dispatcher. Routes to Claude or OpenAI based on model_choice.

    model_choice: "claude" → call_claude, "gpt-4o" → call_openai
    """
    if model_choice == "claude":
        from ai_layer.config import get_ai_config
        config = get_ai_config()
        return call_claude(
            model=config.claude_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        return call_openai(
            model=model_choice,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=timeout_s,
            temperature=temperature,
            rate_limit_kind="interpreter",
            max_tokens=max_tokens,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_ai_client.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ai_layer/client.py backend/tests/test_ai_client.py
git commit -m "feat: add Claude API client and unified call_llm dispatcher"
```

---

### Task 4: Rewrite the floor plan prompt builder

**Files:**
- Modify: `backend/services/ai_floor_plan_prompt.py` (rewrite)
- Test: `backend/tests/test_floor_plan_prompt.py`

- [ ] **Step 1: Write failing test for the new prompt builder**

Create `backend/tests/test_floor_plan_prompt.py`:

```python
"""Tests for the GDCR-aware floor plan prompt builder."""

import pytest


def test_build_system_prompt_contains_gdcr_rules():
    """System prompt must include GDCR room minimums and architectural principles."""
    from services.ai_floor_plan_prompt import build_system_prompt
    prompt = build_system_prompt()
    # Must contain GDCR room minimums
    assert "9.5" in prompt  # living room min area
    assert "2.7" in prompt  # master bedroom min width
    assert "5.5" in prompt  # kitchen min area
    # Must contain architectural principles
    assert "Entry sequence" in prompt or "entry sequence" in prompt.lower()
    assert "Wet zone" in prompt or "wet zone" in prompt.lower()
    assert "ventilation" in prompt.lower()


def test_build_system_prompt_contains_role():
    """System prompt starts with GDCR-compliant architect role for Surat."""
    from services.ai_floor_plan_prompt import build_system_prompt
    prompt = build_system_prompt()
    assert "GDCR" in prompt
    assert "Surat" in prompt or "SUDA" in prompt


def test_build_system_prompt_requests_room_level_output():
    """System prompt asks for room-level geometry, not just unit envelopes."""
    from services.ai_floor_plan_prompt import build_system_prompt
    prompt = build_system_prompt()
    assert "rooms" in prompt.lower()
    # Must NOT say 'no interior rooms needed' (old prompt)
    assert "no interior rooms needed" not in prompt.lower()


def test_build_user_prompt_includes_floor_params():
    """User prompt includes floor plate dimensions and unit mix."""
    from services.ai_floor_plan_prompt import build_user_prompt
    prompt = build_user_prompt(
        floor_width_m=31.4,
        floor_depth_m=14.0,
        n_floors=12,
        building_height_m=36.0,
        units_per_core=4,
        segment="mid",
        unit_mix=["2BHK", "3BHK"],
        n_lifts=2,
        n_stairs=2,
    )
    assert "31.4" in prompt
    assert "14.0" in prompt
    assert "2BHK" in prompt
    assert "3BHK" in prompt


def test_room_program_completeness():
    """ROOM_PROGRAMS has entries for 1BHK, 2BHK, 3BHK, 4BHK with correct room counts."""
    from services.ai_floor_plan_prompt import ROOM_PROGRAMS
    assert "1BHK" in ROOM_PROGRAMS
    assert "2BHK" in ROOM_PROGRAMS
    assert "3BHK" in ROOM_PROGRAMS
    assert "4BHK" in ROOM_PROGRAMS
    # 2BHK should have: foyer, living, kitchen, utility, bedroom1, bedroom2, bathroom, toilet, balcony
    assert len(ROOM_PROGRAMS["2BHK"]) >= 9
    # 3BHK should have: foyer, living_dining, kitchen, utility, bed1, bed2, bed3, bath1, bath2, toilet, balcony
    assert len(ROOM_PROGRAMS["3BHK"]) >= 11


def test_gdcr_minimums_dict():
    """GDCR_ROOM_MINIMUMS dict has correct values per spec."""
    from services.ai_floor_plan_prompt import GDCR_ROOM_MINIMUMS
    assert GDCR_ROOM_MINIMUMS["living"] == {"min_area": 9.5, "min_width": 3.0}
    assert GDCR_ROOM_MINIMUMS["bedroom"] == {"min_area": 9.5, "min_width": 2.7}
    assert GDCR_ROOM_MINIMUMS["bedroom2"] == {"min_area": 7.5, "min_width": 2.5}
    assert GDCR_ROOM_MINIMUMS["kitchen"] == {"min_area": 5.5, "min_width": 1.8}
    assert GDCR_ROOM_MINIMUMS["bathroom"] == {"min_area": 2.16, "min_width": 1.2}
    assert GDCR_ROOM_MINIMUMS["toilet"] == {"min_area": 1.65, "min_width": 1.1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_floor_plan_prompt.py -v`
Expected: FAIL — new exports `ROOM_PROGRAMS`, `GDCR_ROOM_MINIMUMS` don't exist, prompt content differs

- [ ] **Step 3: Rewrite the prompt builder**

Rewrite `backend/services/ai_floor_plan_prompt.py` completely. The new file must:

1. Define `GDCR_ROOM_MINIMUMS` dict with per-room-type `{min_area, min_width}` values
2. Define `ROOM_PROGRAMS` dict mapping unit types to lists of required room types
3. Load GDCR skill content from `.claude/skills/` files (definitions.md, part3-performance.md)
4. `build_system_prompt()` returns a layered prompt with:
   - Role: GDCR-compliant architect for Surat (SUDA, D1)
   - GDCR regulations: room minimums, ventilation (1/10th floor area), staircase dims, lift requirements
   - Architectural principles: entry sequence, kitchen adjacency, master suite, wet zone clustering, balcony access, no landlocked rooms, passage spine, proportionality
   - Output schema: room-level JSON (not just unit envelopes)
5. `build_user_prompt()` returns per-generation parameters (floor dims, height, unit mix, core position)
6. Keep existing exports: `n_lifts_required`, `n_stairs_required`, `CORRIDOR_W`, `ROOM_LIST`

```python
"""
services/ai_floor_plan_prompt.py
---------------------------------
GDCR-aware system + user prompt for AI floor plan generation.

The LLM generates complete room-level layouts for all units.
Walls, doors, and windows are added deterministically by the converter.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---- GDCR room minimums ----

GDCR_ROOM_MINIMUMS: Dict[str, Dict[str, float]] = {
    "living":    {"min_area": 9.5,  "min_width": 3.0},
    "dining":    {"min_area": 7.5,  "min_width": 2.5},
    "bedroom":   {"min_area": 9.5,  "min_width": 2.7},   # master/principal
    "bedroom2":  {"min_area": 7.5,  "min_width": 2.5},   # secondary
    "kitchen":   {"min_area": 5.5,  "min_width": 1.8},
    "bathroom":  {"min_area": 2.16, "min_width": 1.2},
    "toilet":    {"min_area": 1.65, "min_width": 1.1},
    "utility":   {"min_area": 1.80, "min_width": 1.2},
    "foyer":     {"min_area": 1.80, "min_width": 1.5},
    "balcony":   {"min_area": 0.0,  "min_width": 1.2},   # min depth
    "passage":   {"min_area": 0.0,  "min_width": 1.0},
}

# ---- Room programs per unit type ----

ROOM_PROGRAMS: Dict[str, List[str]] = {
    "1BHK": [
        "foyer", "living", "kitchen", "bedroom", "bathroom", "balcony",
    ],
    "2BHK": [
        "foyer", "living", "kitchen", "utility",
        "bedroom",        # master
        "bathroom",       # attached to master
        "bedroom2",       # secondary
        "toilet",         # common
        "balcony",
    ],
    "3BHK": [
        "foyer", "living", "dining", "kitchen", "utility",
        "bedroom",        # master
        "bathroom",       # attached to master
        "bedroom2",       # secondary with attached bath
        "bathroom",       # attached to bedroom2
        "bedroom2",       # third bedroom
        "toilet",         # common
        "balcony",
    ],
    "4BHK": [
        "foyer", "living", "dining", "kitchen", "utility",
        "bedroom",        # master
        "bathroom",       # attached to master
        "bedroom2",       # bed 2
        "bathroom",       # attached to bed 2
        "bedroom2",       # bed 3
        "bedroom2",       # bed 4
        "bathroom",       # attached to bed 3 or 4
        "toilet",         # common
        "balcony",
    ],
}

# ---- Room list descriptions (kept for backward compat) ----

ROOM_LIST: Dict[str, str] = {
    "1BHK": "foyer, living, kitchen, toilet, bedroom, bathroom, balcony",
    "2BHK": (
        "foyer, living, kitchen, utility, "
        "bedroom-1 (master with attached bathroom-1), "
        "bedroom-2, toilet (common), balcony"
    ),
    "3BHK": (
        "foyer, living+dining, kitchen, utility, "
        "bedroom-1 (master with attached bathroom-1), "
        "bedroom-2 (with attached bathroom-2), "
        "bedroom-3, toilet (common), balcony"
    ),
    "4BHK": (
        "foyer, living, dining, kitchen, utility, "
        "bedroom-1 (master with attached bathroom-1), "
        "bedroom-2 (with attached bathroom-2), "
        "bedroom-3, bedroom-4 (with attached bathroom-3), "
        "toilet (common), balcony"
    ),
}

# ---- Core sizing constants ----

LIFT_SHAFT_W = 1.85
LIFT_SHAFT_D = 1.80
STAIR_W = 1.20
STAIR_D = 3.50
LOBBY_D = 2.00
CORRIDOR_W = 1.50
WALL_T = 0.23
BALCONY_DEPTH = 1.50


def n_lifts_required(height_m: float, total_units: int) -> int:
    """GDCR Part III SS 13.12.2 - minimum lifts for residential."""
    if height_m <= 10.0:
        return 0
    min_by_height = 2 if height_m > 25.0 else 1
    by_units = math.ceil(total_units / 30) if total_units > 0 else 0
    return max(min_by_height, by_units)


def n_stairs_required(height_m: float) -> int:
    """Table 13.2: residential > 15 m needs 2 staircases."""
    return 2 if height_m > 15.0 else 1


def _load_gdcr_skill_content() -> str:
    """Load GDCR regulation content from skill files for prompt injection."""
    skills_dir = Path(__file__).resolve().parent.parent.parent / ".claude" / "skills"
    sections = []
    for filename in ["definitions.md", "part3-performance.md", "part2-margins-height-parking.md"]:
        filepath = skills_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            sections.append(f"### {filename}\n{content}")
    if not sections:
        # Fallback: inline GDCR minimums if skill files not found
        return _inline_gdcr_rules()
    return "\n\n".join(sections)


def _inline_gdcr_rules() -> str:
    """Fallback inline GDCR rules when skill files are not available."""
    lines = ["## GDCR Room Minimums (CGDCR-2017 Part III)"]
    for room_type, mins in GDCR_ROOM_MINIMUMS.items():
        lines.append(f"  {room_type}: area >= {mins['min_area']} sqm, width >= {mins['min_width']} m")
    lines.append("")
    lines.append("## Key GDCR Performance Rules")
    lines.append("  - Habitable room ventilation: openings >= 1/10th floor area (Reg 13.4)")
    lines.append("  - Min clear height: 2.9m floor-to-floor for habitable rooms (Reg 13.1.7)")
    lines.append("  - Bathroom ventilation: min 0.25 sqm opening (Reg 13.4)")
    lines.append("  - Staircase: width 1.2m (<=12m height), 1.5m (<=25m), 2.0m (>25m) (Table 13.2)")
    lines.append("  - Lift mandatory >10m height; fire lift >25m (Reg 13.12)")
    lines.append("  - Railing height min 1.15m at balcony/terrace (Reg 13.1.11)")
    lines.append("  - Min 1 WC of 0.9 sqm per dwelling unit (Reg 13.9)")
    lines.append("  - Balcony min depth 1.2m")
    return "\n".join(lines)


def _gdcr_minimums_table() -> str:
    """Format GDCR minimums as a prompt-friendly table."""
    lines = ["GDCR ROOM MINIMUMS (mandatory — never generate rooms smaller than these):"]
    lines.append("  Room Type      | Min Area (sqm) | Min Width (m)")
    lines.append("  -------------- | -------------- | -------------")
    display_names = {
        "living": "Living/Hall", "dining": "Dining", "bedroom": "Master Bedroom",
        "bedroom2": "Secondary Bedroom", "kitchen": "Kitchen", "bathroom": "Bathroom",
        "toilet": "WC/Toilet", "utility": "Utility", "foyer": "Foyer",
        "balcony": "Balcony (depth)", "passage": "Passage",
    }
    for room_type, mins in GDCR_ROOM_MINIMUMS.items():
        name = display_names.get(room_type, room_type.title())
        lines.append(f"  {name:<16}| {mins['min_area']:<14} | {mins['min_width']}")
    return "\n".join(lines)


def build_system_prompt() -> str:
    """
    Build the GDCR-aware system prompt for room-level floor plan generation.

    Three layers:
    1. Role definition (GDCR architect for Surat)
    2. GDCR regulations (from skill files or inline fallback)
    3. Architectural design principles
    """
    gdcr_content = _load_gdcr_skill_content()
    minimums_table = _gdcr_minimums_table()

    return f"""\
You are a GDCR-compliant residential floor plan architect for Surat (SUDA, Category D1).
You generate precise room-level layouts that a professional architect would approve.

Your task is to generate a COMPLETE floor plan with room-level detail for every unit.
You must place: core (lifts + stairs + lobby), corridor, and ALL rooms within each unit.

## COORDINATE SYSTEM
- Floor plate: X = 0 to floor_width_m, Y = 0 to floor_depth_m
- All values in METRES, 2 decimal places
- Y = 0 → SOUTH face (road-facing); Y = floor_depth_m → NORTH face

## FLOOR PLATE STRUCTURE
Three horizontal bands along Y:
  SOUTH BAND (Y = 0 → corridor_y) → south-facing units
  CORRIDOR (Y = corridor_y → corridor_y+{CORRIDOR_W}) → {CORRIDOR_W}m shared passage
  NORTH BAND (Y = corridor_y+{CORRIDOR_W} → floor_depth_m) → north-facing units

## GDCR REGULATIONS
{gdcr_content}

## ROOM SIZE REQUIREMENTS
{minimums_table}

## ARCHITECTURAL DESIGN PRINCIPLES (mandatory)

1. ENTRY SEQUENCE: Corridor → Foyer → Living/Dining (public zone) → Passage → Bedrooms (private zone)
2. KITCHEN ADJACENCY: Kitchen must share a wall with dining or living room; place utility room adjacent to kitchen
3. MASTER SUITE: Master bedroom on exterior wall with attached bathroom on interior side
4. WET ZONE CLUSTERING: Group all bathrooms, toilets, kitchen, and utility to share plumbing stacks (align vertically across floors)
5. BALCONY ACCESS: Balcony accessible from living room or master bedroom; placed on exterior face only
6. NO LANDLOCKED ROOMS: Every habitable room (living, dining, bedroom) must touch an exterior wall for ventilation (GDCR Reg 13.4)
7. PASSAGE AS SPINE: For 2BHK and larger, a passage connects the foyer to the bedroom zone — do NOT route through the living room to reach bedrooms
8. PROPORTIONALITY: No room should be narrower than 60% of its depth; bedrooms should be roughly square
9. MIRRORING: Units on opposite sides of the core should be mirror images for structural symmetry

## ROOM PROGRAMS

1BHK rooms: {ROOM_LIST["1BHK"]}
2BHK rooms: {ROOM_LIST["2BHK"]}
3BHK rooms: {ROOM_LIST["3BHK"]}
4BHK rooms: {ROOM_LIST["4BHK"]}

## OUTPUT FORMAT
Return ONLY a JSON object (no markdown fences, no prose):

{{
  "core": {{
    "x": <float>, "y": <float>, "w": <float>, "h": <float>,
    "stairs": [{{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}],
    "lifts":  [{{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}],
    "lobby":  {{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}
  }},
  "corridor": {{"x": 0.0, "y": <float>, "w": <float>, "h": {CORRIDOR_W}}},
  "units": [
    {{
      "id": "U1",
      "type": "2BHK",
      "side": "south",
      "x": <float>, "y": <float>, "w": <float>, "h": <float>,
      "rooms": [
        {{
          "id": "U1_R1",
          "type": "foyer",
          "x": <float>, "y": <float>, "w": <float>, "h": <float>
        }},
        {{
          "id": "U1_R2",
          "type": "living",
          "x": <float>, "y": <float>, "w": <float>, "h": <float>
        }}
      ],
      "balcony": {{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}
    }}
  ],
  "design_notes": "<one sentence>"
}}

CRITICAL RULES:
- Every unit MUST have a "rooms" array with ALL rooms listed in its room program above
- Room coordinates are ABSOLUTE (relative to floor plate origin 0,0), NOT relative to unit
- All rooms must fit within their unit's bounding box (x, y, w, h)
- No two rooms may overlap within a unit
- Rooms must tile the unit area with minimal gaps
- Balcony projects OUTSIDE the unit envelope on the exterior face
"""


def build_user_prompt(
    floor_width_m: float,
    floor_depth_m: float,
    n_floors: int,
    building_height_m: float,
    units_per_core: int,
    segment: str,
    unit_mix: List[str],
    n_lifts: int,
    n_stairs: int,
    design_brief: str = "",
) -> str:
    """Build the user prompt with specific floor plate parameters."""
    effective_mix = unit_mix if unit_mix else {
        "budget": ["1BHK", "2BHK"],
        "mid": ["2BHK", "3BHK"],
        "premium": ["3BHK", "3BHK"],
        "luxury": ["3BHK", "4BHK"],
    }.get(segment, ["2BHK", "3BHK"])

    # Compute layout geometry
    core_w = max(LIFT_SHAFT_W * n_lifts + STAIR_W * n_stairs + WALL_T * 4, 4.0)
    corridor_y = round((floor_depth_m - CORRIDOR_W) / 2, 2)
    south_band_depth = round(corridor_y, 2)
    north_band_depth = round(floor_depth_m - corridor_y - CORRIDOR_W, 2)

    n_south = units_per_core // 2
    n_north = units_per_core - n_south
    if n_south == 0:
        n_south, n_north = 1, max(units_per_core - 1, 1)

    avail_width = floor_width_m - core_w
    south_unit_width = round(avail_width / n_south, 2) if n_south > 0 else 0
    north_unit_width = round(avail_width / n_north, 2) if n_north > 0 else 0

    # Assign unit types to positions
    unit_assignments = []
    idx = 0
    for i in range(n_south):
        utype = effective_mix[idx % len(effective_mix)] if effective_mix else "2BHK"
        unit_assignments.append(f"  South U{i+1}: {utype} (~{south_unit_width:.1f}m x {south_band_depth:.1f}m)")
        idx += 1
    for i in range(n_north):
        utype = effective_mix[idx % len(effective_mix)] if effective_mix else "2BHK"
        unit_assignments.append(f"  North U{n_south+i+1}: {utype} (~{north_unit_width:.1f}m x {north_band_depth:.1f}m)")
        idx += 1

    prompt = f"""\
Design a complete room-level floor plan for this residential tower:

FLOOR PLATE: {floor_width_m:.1f}m wide (X) x {floor_depth_m:.1f}m deep (Y) = {floor_width_m * floor_depth_m:.0f} sqm
BUILDING: {n_floors} floors, {building_height_m:.1f}m tall
SEGMENT: {segment}
UNITS PER CORE: {units_per_core}

LAYOUT GEOMETRY:
  Corridor: Y = {corridor_y:.2f} to Y = {corridor_y + CORRIDOR_W:.2f} (width {CORRIDOR_W}m)
  South band: Y = 0 to {south_band_depth:.2f} (depth {south_band_depth:.2f}m) — {n_south} unit(s)
  North band: Y = {corridor_y + CORRIDOR_W:.2f} to {floor_depth_m:.2f} (depth {north_band_depth:.2f}m) — {n_north} unit(s)
  Core: centered at X ≈ {floor_width_m/2:.1f}, width ≈ {core_w:.1f}m

UNIT ASSIGNMENTS:
{chr(10).join(unit_assignments)}

CORE COMPONENTS:
  {n_lifts} lift(s) ({LIFT_SHAFT_W}x{LIFT_SHAFT_D}m each)
  {n_stairs} stair(s) ({STAIR_W}x{STAIR_D}m each)
  1 lobby ({LOBBY_D}m deep)

Generate the JSON with COMPLETE room-level detail for EVERY unit. Each unit must have ALL rooms from its room program.
"""
    if design_brief:
        prompt += f"\nDesign brief: {design_brief}\n"

    return prompt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_floor_plan_prompt.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_floor_plan_prompt.py backend/tests/test_floor_plan_prompt.py
git commit -m "feat: rewrite floor plan prompt with GDCR skills and room-level output"
```

---

### Task 5: Expand the validator with room completeness and ventilation checks

**Files:**
- Modify: `backend/services/ai_floor_plan_validator.py`
- Test: `backend/tests/test_floor_plan_validator.py`

- [ ] **Step 1: Write failing tests for new validation rules**

Create `backend/tests/test_floor_plan_validator.py`:

```python
"""Tests for expanded floor plan validator — room completeness + GDCR enforcement."""

import pytest
from copy import deepcopy


def _make_unit(unit_id="U1", unit_type="2BHK", side="south",
               x=0, y=0, w=10, h=6, rooms=None, balcony=None):
    """Helper to build a unit dict."""
    return {
        "id": unit_id, "type": unit_type, "side": side,
        "x": x, "y": y, "w": w, "h": h,
        "rooms": rooms or [],
        "balcony": balcony,
    }


def _make_room(room_id, room_type, x, y, w, h):
    return {"id": room_id, "type": room_type, "x": x, "y": y, "w": w, "h": h}


def _make_layout(units, core=None, corridor=None):
    return {
        "core": core or {"x": 10, "y": 0, "w": 4, "h": 12, "stairs": [], "lifts": [], "lobby": {"x": 10, "y": 5, "w": 4, "h": 2}},
        "corridor": corridor or {"x": 0, "y": 5.25, "w": 20, "h": 1.5},
        "units": units,
    }


def test_room_completeness_pass():
    """2BHK with all required rooms passes completeness check."""
    from services.ai_floor_plan_validator import check_room_completeness
    rooms = [
        _make_room("R1", "foyer", 0, 0, 2, 1.5),
        _make_room("R2", "living", 2, 0, 4, 3),
        _make_room("R3", "kitchen", 6, 0, 3, 3),
        _make_room("R4", "utility", 6, 3, 2, 1.8),
        _make_room("R5", "bedroom", 0, 3, 5, 3),
        _make_room("R6", "bathroom", 0, 1.5, 2, 1.8),
        _make_room("R7", "bedroom2", 5, 3, 4, 3),
        _make_room("R8", "toilet", 8, 3, 1.5, 1.8),
    ]
    unit = _make_unit(rooms=rooms)
    errors = check_room_completeness(unit)
    assert errors == []


def test_room_completeness_missing_rooms():
    """2BHK missing bedroom2 and toilet triggers errors."""
    from services.ai_floor_plan_validator import check_room_completeness
    rooms = [
        _make_room("R1", "foyer", 0, 0, 2, 1.5),
        _make_room("R2", "living", 2, 0, 4, 3),
        _make_room("R3", "kitchen", 6, 0, 3, 3),
        _make_room("R4", "bedroom", 0, 3, 5, 3),
        _make_room("R5", "bathroom", 0, 1.5, 2, 1.8),
    ]
    unit = _make_unit(rooms=rooms)
    errors = check_room_completeness(unit)
    assert len(errors) > 0
    assert any("bedroom2" in e.lower() or "toilet" in e.lower() for e in errors)


def test_room_completeness_empty_unit():
    """Unit with no rooms at all triggers error."""
    from services.ai_floor_plan_validator import check_room_completeness
    unit = _make_unit(rooms=[])
    errors = check_room_completeness(unit)
    assert len(errors) > 0


def test_gdcr_area_enforcement_clamps_small_room():
    """Room below GDCR minimum area gets clamped up."""
    from services.ai_floor_plan_validator import enforce_gdcr_minimums
    rooms = [_make_room("R1", "living", 0, 0, 2.5, 3.0)]  # 7.5 sqm < 9.5
    adjusted, warnings = enforce_gdcr_minimums(rooms)
    area = adjusted[0]["w"] * adjusted[0]["h"]
    assert area >= 9.5
    assert len(warnings) > 0


def test_gdcr_width_enforcement_clamps_narrow_room():
    """Room below GDCR minimum width gets width clamped."""
    from services.ai_floor_plan_validator import enforce_gdcr_minimums
    rooms = [_make_room("R1", "kitchen", 0, 0, 1.5, 4.0)]  # width 1.5 < 1.8
    adjusted, warnings = enforce_gdcr_minimums(rooms)
    assert adjusted[0]["w"] >= 1.8
    assert len(warnings) > 0


def test_ventilation_check_habitable_on_exterior():
    """Living room touching exterior wall (y=0 for south unit) passes ventilation."""
    from services.ai_floor_plan_validator import check_ventilation
    unit = _make_unit(side="south", y=0, h=6)
    rooms = [_make_room("R1", "living", 0, 0, 4, 3)]  # y=0 touches south exterior
    errors = check_ventilation(unit, rooms)
    assert errors == []


def test_ventilation_check_landlocked_room_fails():
    """Living room not touching any exterior wall triggers ventilation error."""
    from services.ai_floor_plan_validator import check_ventilation
    unit = _make_unit(side="south", x=5, y=0, w=10, h=6)
    # Living room at interior position — doesn't touch any exterior edge
    rooms = [_make_room("R1", "living", 7, 2, 3, 2)]
    errors = check_ventilation(unit, rooms)
    assert len(errors) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_floor_plan_validator.py -v`
Expected: FAIL — `check_room_completeness`, `enforce_gdcr_minimums`, `check_ventilation` don't exist

- [ ] **Step 3: Add new validation functions**

Add to `backend/services/ai_floor_plan_validator.py` (after line 31, before `validate_ai_floor_plan`):

```python
# ---- Room programs for completeness checking ----
_REQUIRED_ROOMS: Dict[str, Dict[str, int]] = {
    "1BHK": {"foyer": 1, "living": 1, "kitchen": 1, "bedroom": 1, "bathroom": 1},
    "2BHK": {"foyer": 1, "living": 1, "kitchen": 1, "utility": 1, "bedroom": 1, "bathroom": 1, "bedroom2": 1, "toilet": 1},
    "3BHK": {"foyer": 1, "living": 1, "dining": 1, "kitchen": 1, "utility": 1, "bedroom": 1, "bathroom": 2, "bedroom2": 2, "toilet": 1},
    "4BHK": {"foyer": 1, "living": 1, "dining": 1, "kitchen": 1, "utility": 1, "bedroom": 1, "bathroom": 3, "bedroom2": 3, "toilet": 1},
}

# Habitable room types that require exterior wall contact for ventilation
_HABITABLE_ROOMS = {"living", "dining", "bedroom", "bedroom2"}

# Tolerance for "touching exterior wall" check (metres)
_EXTERIOR_TOL = 0.15


def check_room_completeness(unit: Dict[str, Any]) -> List[str]:
    """
    Check that a unit has all required rooms for its type.

    Returns list of error strings (empty if all rooms present).
    """
    unit_type = unit.get("type", "2BHK").upper()
    rooms = unit.get("rooms", [])
    uid = unit.get("id", "?")

    required = _REQUIRED_ROOMS.get(unit_type)
    if not required:
        return [f"Unit {uid}: unknown type '{unit_type}'"]

    if not rooms:
        return [f"Unit {uid} ({unit_type}): has NO rooms — expected {sum(required.values())} rooms"]

    # Count room types present
    type_counts: Dict[str, int] = {}
    for r in rooms:
        rtype = r.get("type", "").lower()
        # Normalize: bedroom1/bedroom_1/master_bedroom → bedroom
        if rtype in ("bedroom1", "bedroom_1", "master_bedroom"):
            rtype = "bedroom"
        elif rtype in ("bedroom3", "bedroom_3", "bedroom4", "bedroom_4"):
            rtype = "bedroom2"
        type_counts[rtype] = type_counts.get(rtype, 0) + 1

    errors = []
    for room_type, min_count in required.items():
        actual = type_counts.get(room_type, 0)
        if actual < min_count:
            errors.append(
                f"Unit {uid} ({unit_type}): missing {room_type} "
                f"(has {actual}, need {min_count})"
            )
    return errors


def enforce_gdcr_minimums(
    rooms: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Clamp room dimensions up to GDCR minimums.

    Returns (adjusted_rooms, warnings).
    """
    adjusted = copy.deepcopy(rooms)
    warnings: List[str] = []

    for room in adjusted:
        rtype = room.get("type", "").lower()
        if rtype in ("bedroom1", "bedroom_1", "master_bedroom"):
            lookup_type = "bedroom"
        elif rtype in ("bedroom3", "bedroom_3", "bedroom4", "bedroom_4"):
            lookup_type = "bedroom2"
        else:
            lookup_type = rtype

        mins = GDCR_MINIMUMS.get(lookup_type)
        if not mins:
            continue

        min_area, min_width = mins
        w = room.get("w", 0)
        h = room.get("h", 0)
        rid = room.get("id", "?")

        # Clamp width
        if w < min_width and min_width > 0:
            warnings.append(f"Room {rid} ({rtype}): width {w:.2f}m < min {min_width:.2f}m, clamped")
            room["w"] = min_width
            w = min_width

        # Clamp area by increasing depth if needed
        area = w * h
        if area < min_area and min_area > 0:
            needed_h = min_area / max(w, 0.1)
            warnings.append(f"Room {rid} ({rtype}): area {area:.2f} sqm < min {min_area:.2f} sqm, depth increased")
            room["h"] = round(needed_h, 2)

    return adjusted, warnings


def check_ventilation(
    unit: Dict[str, Any],
    rooms: List[Dict[str, Any]],
) -> List[str]:
    """
    Check that all habitable rooms touch an exterior wall (GDCR Reg 13.4).

    Exterior walls for a unit are:
    - South unit: y=0 (south exterior), x=unit.x (left), x=unit.x+unit.w (right)
    - North unit: y=unit.y+unit.h (north exterior), x=unit.x (left), x=unit.x+unit.w (right)
    """
    errors = []
    uid = unit.get("id", "?")
    ux = unit.get("x", 0)
    uy = unit.get("y", 0)
    uw = unit.get("w", 0)
    uh = unit.get("h", 0)
    side = unit.get("side", "south")

    for room in rooms:
        rtype = room.get("type", "").lower()
        if rtype not in _HABITABLE_ROOMS:
            continue

        rx = room.get("x", 0)
        ry = room.get("y", 0)
        rw = room.get("w", 0)
        rh = room.get("h", 0)
        rid = room.get("id", "?")

        touches_exterior = False

        # Left exterior wall of unit
        if abs(rx - ux) < _EXTERIOR_TOL:
            touches_exterior = True
        # Right exterior wall of unit
        if abs((rx + rw) - (ux + uw)) < _EXTERIOR_TOL:
            touches_exterior = True
        # South exterior (south units: y=0 is exterior)
        if side == "south" and abs(ry - uy) < _EXTERIOR_TOL:
            touches_exterior = True
        # North exterior (north units: y+h is exterior)
        if side == "north" and abs((ry + rh) - (uy + uh)) < _EXTERIOR_TOL:
            touches_exterior = True

        if not touches_exterior:
            errors.append(
                f"Room {rid} ({rtype}) in unit {uid}: no exterior wall contact — "
                f"violates GDCR Reg 13.4 ventilation requirement"
            )

    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_floor_plan_validator.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_floor_plan_validator.py backend/tests/test_floor_plan_validator.py
git commit -m "feat: add room completeness, GDCR enforcement, and ventilation checks to validator"
```

---

### Task 6: Refactor the floor plan service to use AI-generated rooms

**Files:**
- Modify: `backend/services/ai_floor_plan_service.py`

- [ ] **Step 1: Write failing test for AI-driven room generation**

Create `backend/tests/test_floor_plan_service.py`:

```python
"""Tests for the refactored AI floor plan service."""

import json
import pytest
from unittest.mock import patch, MagicMock


# A valid AI response with complete room-level layout for 2 units
MOCK_AI_RESPONSE = json.dumps({
    "core": {
        "x": 10.0, "y": 0.0, "w": 4.5, "h": 12.0,
        "stairs": [{"x": 10.23, "y": 6.0, "w": 1.2, "h": 3.5}],
        "lifts": [{"x": 10.23, "y": 0.23, "w": 1.85, "h": 1.8}],
        "lobby": {"x": 10.0, "y": 4.75, "w": 4.5, "h": 2.0}
    },
    "corridor": {"x": 0.0, "y": 5.25, "w": 24.0, "h": 1.5},
    "units": [
        {
            "id": "U1", "type": "2BHK", "side": "south",
            "x": 0.0, "y": 0.0, "w": 10.0, "h": 5.25,
            "rooms": [
                {"id": "U1_R1", "type": "foyer", "x": 0.0, "y": 0.0, "w": 2.0, "h": 1.5},
                {"id": "U1_R2", "type": "living", "x": 2.0, "y": 0.0, "w": 4.0, "h": 3.2},
                {"id": "U1_R3", "type": "kitchen", "x": 6.0, "y": 0.0, "w": 3.5, "h": 3.2},
                {"id": "U1_R4", "type": "utility", "x": 6.0, "y": 3.2, "w": 2.0, "h": 2.05},
                {"id": "U1_R5", "type": "bedroom", "x": 0.0, "y": 1.5, "w": 4.5, "h": 3.75},
                {"id": "U1_R6", "type": "bathroom", "x": 4.5, "y": 3.2, "w": 1.5, "h": 2.05},
                {"id": "U1_R7", "type": "bedroom2", "x": 8.0, "y": 3.2, "w": 2.0, "h": 2.05},
                {"id": "U1_R8", "type": "toilet", "x": 9.5, "y": 0.0, "w": 1.5, "h": 1.8}
            ],
            "balcony": {"x": 0.0, "y": -1.5, "w": 10.0, "h": 1.5}
        },
        {
            "id": "U2", "type": "3BHK", "side": "north",
            "x": 0.0, "y": 6.75, "w": 10.0, "h": 5.25,
            "rooms": [
                {"id": "U2_R1", "type": "foyer", "x": 0.0, "y": 6.75, "w": 2.0, "h": 1.5},
                {"id": "U2_R2", "type": "living", "x": 2.0, "y": 6.75, "w": 3.5, "h": 3.0},
                {"id": "U2_R3", "type": "dining", "x": 5.5, "y": 6.75, "w": 2.5, "h": 3.0},
                {"id": "U2_R4", "type": "kitchen", "x": 8.0, "y": 6.75, "w": 2.0, "h": 3.0},
                {"id": "U2_R5", "type": "utility", "x": 8.0, "y": 9.75, "w": 2.0, "h": 2.25},
                {"id": "U2_R6", "type": "bedroom", "x": 0.0, "y": 8.25, "w": 4.0, "h": 3.75},
                {"id": "U2_R7", "type": "bathroom", "x": 4.0, "y": 9.75, "w": 2.0, "h": 2.25},
                {"id": "U2_R8", "type": "bedroom2", "x": 0.0, "y": 9.75, "w": 3.5, "h": 2.25},
                {"id": "U2_R9", "type": "bathroom", "x": 3.5, "y": 9.75, "w": 1.5, "h": 2.25},
                {"id": "U2_R10", "type": "bedroom2", "x": 6.0, "y": 9.75, "w": 2.0, "h": 2.25},
                {"id": "U2_R11", "type": "toilet", "x": 6.0, "y": 6.75, "w": 2.0, "h": 1.8}
            ],
            "balcony": {"x": 0.0, "y": 12.0, "w": 10.0, "h": 1.5}
        }
    ],
    "design_notes": "Test layout"
})


def test_service_uses_call_llm_not_call_openai():
    """The service should use call_llm (model-agnostic), not call_openai directly."""
    with patch("services.ai_floor_plan_service.call_llm", return_value=MOCK_AI_RESPONSE) as mock_llm:
        with patch("services.ai_floor_plan_service.call_openai", side_effect=AssertionError("Should not be called")):
            from services.ai_floor_plan_service import generate_ai_floor_plan
            result = generate_ai_floor_plan(
                footprint_geojson={"type": "Polygon", "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]},
                n_floors=12,
                building_height_m=36.0,
                units_per_core=4,
                segment="mid",
            )
            assert mock_llm.called
            assert result["status"] == "ok"


def test_service_preserves_ai_rooms():
    """The service should keep AI-generated rooms, not replace them with deterministic ones."""
    with patch("services.ai_floor_plan_service.call_llm", return_value=MOCK_AI_RESPONSE):
        from services.ai_floor_plan_service import generate_ai_floor_plan
        result = generate_ai_floor_plan(
            footprint_geojson={"type": "Polygon", "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]},
            n_floors=12,
            building_height_m=36.0,
            units_per_core=4,
            segment="mid",
        )
        # The result should have rooms in the layout
        features = result.get("layout", {}).get("features", [])
        room_features = [f for f in features if f.get("properties", {}).get("layer") == "room"]
        assert len(room_features) > 0, "AI-generated rooms should appear in output"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_floor_plan_service.py -v`
Expected: FAIL — `call_llm` not imported, service still uses `call_openai`

- [ ] **Step 3: Refactor the service**

In `backend/services/ai_floor_plan_service.py`, make these changes:

**Import changes** (replace line 16):
```python
from ai_layer.client import call_llm, call_openai, parse_json_response
```

**In `generate_ai_floor_plan`**, replace the AI call loop (lines 102-167) with:

```python
    # ---- 4. Call AI with retry (model-agnostic) ----
    config = get_ai_config()
    model_choice = config.floor_plan_ai_model  # "claude" or "gpt-4o"
    timeout = config.floor_plan_timeout_s
    max_tokens_setting = config.floor_plan_max_tokens

    ai_layout = None
    design_notes = ""
    last_errors: List[str] = []

    for attempt in range(3):
        prompt = user_prompt
        if attempt > 0 and last_errors:
            prompt += (
                "\n\nPREVIOUS ATTEMPT HAD ERRORS — please fix:\n"
                + "\n".join(f"  - {e}" for e in last_errors)
            )

        raw = call_llm(
            model_choice=model_choice,
            system_prompt=system_prompt,
            user_prompt=prompt,
            timeout_s=timeout,
            temperature=0.2,
            max_tokens=max_tokens_setting,
        )

        if not raw:
            logger.warning("AI floor plan: LLM returned empty (attempt %d, model=%s)",
                           attempt + 1, model_choice)
            continue

        logger.debug("AI floor plan raw response (attempt %d, %d chars): %s…",
                      attempt + 1, len(raw), raw[:200])

        parsed = _parse_ai_response(raw)
        if not parsed:
            logger.warning("AI floor plan: JSON parse failed (attempt %d). First 500 chars: %s",
                           attempt + 1, raw[:500])
            last_errors = ["Response was not valid JSON"]
            continue

        # Validate structure
        validation = validate_ai_floor_plan(
            parsed, floor_width_m, floor_depth_m, n_lifts, n_stairs,
        )

        if validation["valid"]:
            ai_layout = validation["repaired_layout"]
            design_notes = parsed.get("design_notes", "")
            if validation["warnings"]:
                logger.info("AI floor plan warnings: %s", validation["warnings"])
            break
        else:
            last_errors = validation["errors"]
            logger.warning(
                "AI floor plan validation failed (attempt %d): %s",
                attempt + 1, last_errors,
            )

    if ai_layout is None:
        logger.error("AI floor plan: all attempts failed, returning error")
        return _error_response(
            f"AI floor plan generation failed after 3 attempts. Last errors: {last_errors}"
        )
```

**Replace the deterministic room injection** (lines 174-192) with validation-only steps:

```python
    # ---- 4b. Recompute unit envelopes if AI provided incomplete geometry ----
    # Only recompute if units lack rooms (backward compat / fallback)
    units_have_rooms = all(
        len(u.get("rooms", [])) > 0 for u in ai_layout.get("units", [])
    )

    if not units_have_rooms:
        # Fallback: recompute envelopes and inject deterministic rooms
        logger.warning("AI returned units without rooms — falling back to deterministic layout")
        ai_layout = _recompute_unit_envelopes(
            ai_layout, floor_width_m, floor_depth_m,
            units_per_core, n_lifts, n_stairs,
        )
        ai_layout = _inject_deterministic_rooms(ai_layout, segment)
    else:
        # AI provided rooms — validate completeness
        from services.ai_floor_plan_validator import (
            check_room_completeness, enforce_gdcr_minimums, check_ventilation,
        )
        for unit in ai_layout.get("units", []):
            completeness_errors = check_room_completeness(unit)
            if completeness_errors:
                logger.warning("Room completeness issues in %s: %s",
                               unit.get("id"), completeness_errors)
            # Enforce GDCR minimums
            rooms = unit.get("rooms", [])
            adjusted_rooms, gdcr_warnings = enforce_gdcr_minimums(rooms)
            unit["rooms"] = adjusted_rooms
            if gdcr_warnings:
                logger.info("GDCR adjustments for %s: %s",
                            unit.get("id"), gdcr_warnings)
            # Check ventilation
            vent_errors = check_ventilation(unit, adjusted_rooms)
            if vent_errors:
                logger.warning("Ventilation issues in %s: %s",
                               unit.get("id"), vent_errors)

    # ---- 5. Snap coordinates ----
    ai_layout = _snap_to_structural_grid(ai_layout, floor_width_m)
    ai_layout = _align_wet_zone_stacks(ai_layout)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_floor_plan_service.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_floor_plan_service.py backend/tests/test_floor_plan_service.py
git commit -m "feat: refactor floor plan service to use AI-generated rooms with model toggle"
```

---

### Task 7: Update GeoJSON converter for new room types

**Files:**
- Modify: `backend/services/ai_to_geojson_converter.py`

- [ ] **Step 1: Add support for passage and attached_bath room types**

In `backend/services/ai_to_geojson_converter.py`, update the `_WIN_W` dict (around line 39) to include new room types:

```python
_WIN_W: Dict[str, float] = {
    "living":       1.50,
    "dining":       1.20,
    "bedroom":      1.20,
    "bedroom1":     1.20,
    "bedroom2":     1.20,
    "bedroom3":     1.20,
    "bedroom4":     1.20,
    "master_bedroom": 1.20,
    "kitchen":      0.90,
    "bathroom":     0.60,
    "attached_bath": 0.60,
    "toilet":       0.60,
    "foyer":        0.00,
    "passage":      0.00,
    "utility":      0.60,
    "balcony":      0.00,
}
```

Also update the `_OPEN_PLAN_PAIRS` frozenset to include passage connections:

```python
_OPEN_PLAN_PAIRS: frozenset = frozenset({
    frozenset(("living", "dining")),
    frozenset(("living", "foyer")),
    frozenset(("dining", "kitchen")),
    frozenset(("foyer", "passage")),
    frozenset(("passage", "living")),
    frozenset(("passage", "foyer")),
})
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/services/ai_to_geojson_converter.py
git commit -m "feat: add passage, attached_bath, bedroom variants to GeoJSON converter"
```

---

### Task 8: Rewrite SVG blueprint renderer with professional drawing conventions

**Files:**
- Modify: `backend/services/svg_blueprint_renderer.py` (major rewrite)
- Test: `backend/tests/test_svg_renderer.py`

- [ ] **Step 1: Write failing tests for new rendering features**

Create `backend/tests/test_svg_renderer.py`:

```python
"""Tests for SVG blueprint renderer — professional drawing conventions."""

import pytest


def _make_feature(layer, room_type=None, coords=None, props=None):
    """Helper to build a GeoJSON feature."""
    base_props = {"layer": layer}
    if room_type:
        base_props["room_type"] = room_type
    if props:
        base_props.update(props)
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords or [[0,0],[5,0],[5,3],[0,3],[0,0]]],
        },
        "properties": base_props,
    }


def test_svg_contains_north_arrow():
    """SVG output must include a north arrow element."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0, title="Test")
    assert "north-arrow" in svg or "N" in svg


def test_svg_contains_structural_grid():
    """SVG output must include structural column grid markers."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0, title="Test")
    assert "structural-grid" in svg or "column-grid" in svg


def test_svg_kitchen_hatching_different_from_bathroom():
    """Kitchen and bathroom must have different hatch patterns."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [
        _make_feature("footprint_bg"),
        _make_feature("room", room_type="KITCHEN", coords=[[0,0],[3,0],[3,3],[0,3],[0,0]]),
        _make_feature("room", room_type="BATHROOM", coords=[[3,0],[5,0],[5,2],[3,2],[3,0]]),
    ]}
    svg = render_blueprint_svg(layout, 20.0, 12.0)
    # Should have at least 3 different hatch patterns defined
    assert "hatch-kitchen" in svg or "hatch-wet" in svg
    assert svg.count("<pattern") >= 2


def test_svg_title_block_includes_scale():
    """Title block must include scale notation."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0, title="Test Plan")
    assert "1:100" in svg or "Scale" in svg


def test_svg_scale_bar_has_subdivisions():
    """Scale bar must have 1m subdivisions."""
    from services.svg_blueprint_renderer import render_blueprint_svg
    layout = {"features": [_make_feature("footprint_bg")]}
    svg = render_blueprint_svg(layout, 20.0, 12.0)
    # Scale bar group should exist with multiple tick marks
    assert "scale-bar" in svg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_svg_renderer.py -v`
Expected: FAIL — no north arrow, no structural grid, no distinct kitchen hatch

- [ ] **Step 3: Rewrite the SVG renderer**

Rewrite `backend/services/svg_blueprint_renderer.py`. Key changes to the existing file:

**Update `_svg_defs()`** to add distinct hatch patterns:

```python
def _svg_defs() -> str:
    """SVG defs: distinct hatch patterns per room type + markers."""
    return """\
  <defs>
    <pattern id="hatch-wet" patternUnits="userSpaceOnUse" width="6" height="6"
             patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="6" stroke="#b0c4de" stroke-width="0.6"/>
      <line x1="3" y1="0" x2="3" y2="6" stroke="#b0c4de" stroke-width="0.4"/>
    </pattern>
    <pattern id="hatch-kitchen" patternUnits="userSpaceOnUse" width="6" height="6"
             patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="6" stroke="#e8c090" stroke-width="0.6"/>
    </pattern>
    <pattern id="hatch-utility" patternUnits="userSpaceOnUse" width="4" height="4">
      <circle cx="2" cy="2" r="0.6" fill="#ccc"/>
    </pattern>
    <pattern id="hatch-stair" patternUnits="userSpaceOnUse" width="4" height="8">
      <line x1="0" y1="0" x2="4" y2="0" stroke="#666" stroke-width="0.5"/>
      <line x1="0" y1="4" x2="4" y2="4" stroke="#666" stroke-width="0.5"/>
    </pattern>
    <marker id="arrow-stair" markerWidth="6" markerHeight="6"
            refX="3" refY="3" orient="auto">
      <path d="M0,0 L0,6 L6,3 Z" fill="#444"/>
    </marker>
  </defs>"""
```

**Update `_get_style()`** for room-type-specific hatching:

```python
    elif layer == "room":
        room_type = props.get("room_type", "").upper()
        if room_type in ("BATHROOM", "TOILET"):
            return f'fill="url(#hatch-wet)" stroke="#444" stroke-width="0.5"'
        if room_type == "KITCHEN":
            return f'fill="url(#hatch-kitchen)" stroke="#444" stroke-width="0.5"'
        if room_type == "UTILITY":
            return f'fill="url(#hatch-utility)" stroke="#444" stroke-width="0.4"'
        if room_type in CIRC_ROOMS:
            return 'fill="#f0f0f0" stroke="#444" stroke-width="0.4"'
        return 'fill="#ffffff" stroke="#444" stroke-width="0.4"'
    elif layer == "wall":
        wall_type = props.get("wall_type", "external")
        if wall_type == "internal":
            return 'fill="#333" stroke="#222" stroke-width="0.3"'
        if wall_type == "entry":
            return 'fill="#222" stroke="#000" stroke-width="0.4"'
        if wall_type == "parapet":
            return 'fill="#555" stroke="#444" stroke-width="0.2"'
        return 'fill="#111" stroke="#000" stroke-width="0.6"'
```

**Add north arrow function** (add before `_render_title`):

```python
def _render_north_arrow(floor_width_m: float, floor_depth_m: float) -> str:
    """Render a north arrow at the top-right corner."""
    ax, ay = _to_svg(floor_width_m + MARGIN * 0.6, floor_depth_m - 0.5, floor_depth_m)
    arrow_h = 25  # px
    return (
        f'  <g class="north-arrow" transform="translate({ax:.0f},{ay:.0f})">\n'
        f'    <line x1="0" y1="{arrow_h}" x2="0" y2="0" stroke="#333" stroke-width="1.5"/>\n'
        f'    <polygon points="-5,8 0,0 5,8" fill="#333"/>\n'
        f'    <text x="0" y="-5" text-anchor="middle" font-size="10" '
        f'font-weight="bold" font-family="Arial,sans-serif" fill="#333">N</text>\n'
        f'  </g>'
    )
```

**Add structural column grid function:**

```python
def _render_structural_grid(floor_width_m: float, floor_depth_m: float,
                             grid_m: float = 4.5) -> str:
    """Render structural column grid as dashed lines with small circles at intersections."""
    lines = ['  <g class="structural-grid column-grid">']

    # Vertical grid lines
    x = 0.0
    while x <= floor_width_m + 0.01:
        sx0, sy0 = _to_svg(x, 0, floor_depth_m)
        sx1, sy1 = _to_svg(x, floor_depth_m, floor_depth_m)
        lines.append(
            f'    <line x1="{sx0:.1f}" y1="{sy0:.1f}" x2="{sx1:.1f}" y2="{sy1:.1f}" '
            f'stroke="#ccc" stroke-width="0.3" stroke-dasharray="4 4"/>'
        )
        x += grid_m

    # Horizontal grid lines
    y = 0.0
    while y <= floor_depth_m + 0.01:
        sx0, sy0 = _to_svg(0, y, floor_depth_m)
        sx1, sy1 = _to_svg(floor_width_m, y, floor_depth_m)
        lines.append(
            f'    <line x1="{sx0:.1f}" y1="{sy0:.1f}" x2="{sx1:.1f}" y2="{sy1:.1f}" '
            f'stroke="#ccc" stroke-width="0.3" stroke-dasharray="4 4"/>'
        )
        y += grid_m

    # Column circles at intersections
    x = 0.0
    while x <= floor_width_m + 0.01:
        y = 0.0
        while y <= floor_depth_m + 0.01:
            sx, sy = _to_svg(x, y, floor_depth_m)
            lines.append(
                f'    <circle cx="{sx:.1f}" cy="{sy:.1f}" r="3" '
                f'fill="none" stroke="#999" stroke-width="0.5" stroke-dasharray="2 2"/>'
            )
            y += grid_m
        x += grid_m

    lines.append('  </g>')
    return "\n".join(lines)
```

**Update `_render_scale_bar`** to add subdivisions:

```python
def _render_scale_bar(floor_width_m: float, floor_depth_m: float) -> str:
    """Render a scale bar at bottom-left with 1m subdivisions."""
    bar_m = 5.0 if floor_width_m > 15 else 2.0
    x0, y0 = _to_svg(0, -MARGIN * 0.8, floor_depth_m)
    bar_px = bar_m * SCALE

    parts = [f'  <g class="scale-bar">']
    # Main bar
    parts.append(
        f'    <line x1="{x0:.1f}" y1="{y0:.1f}" '
        f'x2="{x0 + bar_px:.1f}" y2="{y0:.1f}" '
        f'stroke="#000" stroke-width="1.5"/>'
    )
    # End ticks + 1m subdivision ticks
    for i in range(int(bar_m) + 1):
        tick_x = x0 + i * SCALE
        tick_h = 5 if i == 0 or i == int(bar_m) else 3
        parts.append(
            f'    <line x1="{tick_x:.1f}" y1="{y0 - tick_h:.1f}" '
            f'x2="{tick_x:.1f}" y2="{y0 + tick_h:.1f}" stroke="#000" stroke-width="1"/>'
        )
    # Label
    parts.append(
        f'    <text x="{x0 + bar_px / 2:.1f}" y="{y0 + 14:.1f}" '
        f'text-anchor="middle" font-size="{FONT_DIM}" '
        f'font-family="Arial,sans-serif">{bar_m:.0f} m</text>'
    )
    parts.append('  </g>')
    return "\n".join(parts)
```

**Update `_render_title`** to include scale:

```python
def _render_title(title: str, svg_w: float, svg_h: float) -> str:
    title_with_scale = f"{title} — Scale 1:100" if "Scale" not in title else title
    return (
        f'  <text x="{svg_w - 10:.1f}" y="{svg_h - 10:.1f}" '
        f'text-anchor="end" font-size="10" font-weight="bold" '
        f'font-family="Arial,sans-serif" fill="#333">'
        f'{xml_escape(title_with_scale)}</text>'
    )
```

**Update `render_blueprint_svg`** to call the new functions. After the dimension lines (around line 92), add:

```python
    # Structural column grid (rendered behind everything, right after footprint)
    parts.insert(3, _render_structural_grid(floor_width_m, floor_depth_m))

    # North arrow
    parts.append(_render_north_arrow(floor_width_m, floor_depth_m))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_svg_renderer.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/svg_blueprint_renderer.py backend/tests/test_svg_renderer.py
git commit -m "feat: rewrite SVG renderer with professional hatching, north arrow, structural grid"
```

---

### Task 9: Integration test — end-to-end floor plan generation

**Files:**
- Test: `backend/tests/test_floor_plan_integration.py`

- [ ] **Step 1: Write integration test**

Create `backend/tests/test_floor_plan_integration.py`:

```python
"""Integration test: full pipeline from footprint → GeoJSON + SVG."""

import json
import pytest
from unittest.mock import patch


MOCK_AI_LAYOUT = {
    "core": {
        "x": 10.0, "y": 0.0, "w": 4.5, "h": 12.0,
        "stairs": [{"x": 10.23, "y": 6.0, "w": 1.2, "h": 3.5}],
        "lifts": [{"x": 10.23, "y": 0.23, "w": 1.85, "h": 1.8}],
        "lobby": {"x": 10.0, "y": 4.75, "w": 4.5, "h": 2.0}
    },
    "corridor": {"x": 0.0, "y": 5.25, "w": 24.0, "h": 1.5},
    "units": [
        {
            "id": "U1", "type": "2BHK", "side": "south",
            "x": 0.0, "y": 0.0, "w": 10.0, "h": 5.25,
            "rooms": [
                {"id": "U1_R1", "type": "foyer", "x": 0.0, "y": 0.0, "w": 2.0, "h": 1.5},
                {"id": "U1_R2", "type": "living", "x": 2.0, "y": 0.0, "w": 4.0, "h": 3.2},
                {"id": "U1_R3", "type": "kitchen", "x": 6.0, "y": 0.0, "w": 3.5, "h": 3.2},
                {"id": "U1_R4", "type": "utility", "x": 6.0, "y": 3.2, "w": 2.0, "h": 2.05},
                {"id": "U1_R5", "type": "bedroom", "x": 0.0, "y": 1.5, "w": 4.5, "h": 3.75},
                {"id": "U1_R6", "type": "bathroom", "x": 4.5, "y": 3.2, "w": 2.0, "h": 2.05},
                {"id": "U1_R7", "type": "bedroom2", "x": 8.0, "y": 3.2, "w": 3.0, "h": 2.05},
                {"id": "U1_R8", "type": "toilet", "x": 8.0, "y": 0.0, "w": 1.5, "h": 1.8},
            ],
            "balcony": {"x": 0.0, "y": -1.5, "w": 10.0, "h": 1.5}
        },
        {
            "id": "U2", "type": "2BHK", "side": "north",
            "x": 0.0, "y": 6.75, "w": 10.0, "h": 5.25,
            "rooms": [
                {"id": "U2_R1", "type": "foyer", "x": 0.0, "y": 10.5, "w": 2.0, "h": 1.5},
                {"id": "U2_R2", "type": "living", "x": 2.0, "y": 8.8, "w": 4.0, "h": 3.2},
                {"id": "U2_R3", "type": "kitchen", "x": 6.0, "y": 8.8, "w": 3.5, "h": 3.2},
                {"id": "U2_R4", "type": "utility", "x": 6.0, "y": 6.75, "w": 2.0, "h": 2.05},
                {"id": "U2_R5", "type": "bedroom", "x": 0.0, "y": 6.75, "w": 4.5, "h": 3.75},
                {"id": "U2_R6", "type": "bathroom", "x": 4.5, "y": 6.75, "w": 2.0, "h": 2.05},
                {"id": "U2_R7", "type": "bedroom2", "x": 8.0, "y": 6.75, "w": 3.0, "h": 2.05},
                {"id": "U2_R8", "type": "toilet", "x": 8.0, "y": 10.2, "w": 1.5, "h": 1.8},
            ],
            "balcony": {"x": 0.0, "y": 12.0, "w": 10.0, "h": 1.5}
        },
    ],
    "design_notes": "Integration test layout"
}


def test_full_pipeline_produces_valid_output():
    """End-to-end: footprint → AI mock → GeoJSON + SVG with all required elements."""
    mock_response = json.dumps(MOCK_AI_LAYOUT)

    with patch("services.ai_floor_plan_service.call_llm", return_value=mock_response):
        from services.ai_floor_plan_service import generate_ai_floor_plan
        result = generate_ai_floor_plan(
            footprint_geojson={
                "type": "Polygon",
                "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]
            },
            n_floors=12,
            building_height_m=36.0,
            units_per_core=4,
            segment="mid",
            unit_mix=["2BHK", "2BHK"],
        )

    assert result["status"] == "ok"
    assert result["source"] == "ai"

    # GeoJSON has room features
    features = result["layout"]["features"]
    layers = {f["properties"]["layer"] for f in features}
    assert "room" in layers
    assert "wall" in layers
    assert "window" in layers

    # SVG has professional elements
    svg = result["svg_blueprint"]
    assert "<svg" in svg
    assert "north-arrow" in svg or ">N<" in svg
    assert "structural-grid" in svg or "column-grid" in svg
    assert "scale-bar" in svg
    assert "1:100" in svg

    # Metrics present
    metrics = result["metrics"]
    assert metrics["nUnitsPerFloor"] == 2
    assert metrics["footprintSqm"] > 0


def test_fallback_to_deterministic_when_no_rooms():
    """When AI returns units without rooms, fallback to deterministic layout."""
    no_rooms_layout = json.dumps({
        "core": MOCK_AI_LAYOUT["core"],
        "corridor": MOCK_AI_LAYOUT["corridor"],
        "units": [
            {"id": "U1", "type": "2BHK", "side": "south",
             "x": 0, "y": 0, "w": 10, "h": 5.25},
            {"id": "U2", "type": "2BHK", "side": "north",
             "x": 0, "y": 6.75, "w": 10, "h": 5.25},
        ],
        "design_notes": "No rooms provided"
    })

    with patch("services.ai_floor_plan_service.call_llm", return_value=no_rooms_layout):
        from services.ai_floor_plan_service import generate_ai_floor_plan
        result = generate_ai_floor_plan(
            footprint_geojson={
                "type": "Polygon",
                "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]
            },
            n_floors=12,
            building_height_m=36.0,
            units_per_core=2,
            segment="mid",
        )

    # Should still produce valid output via fallback
    assert result["status"] == "ok"
    features = result["layout"]["features"]
    room_features = [f for f in features if f["properties"]["layer"] == "room"]
    assert len(room_features) > 0, "Fallback should produce rooms"
```

- [ ] **Step 2: Run integration test**

Run: `cd backend && python -m pytest tests/test_floor_plan_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Run all tests together**

Run: `cd backend && python -m pytest tests/test_ai_config.py tests/test_ai_client.py tests/test_floor_plan_prompt.py tests/test_floor_plan_validator.py tests/test_floor_plan_service.py tests/test_svg_renderer.py tests/test_floor_plan_integration.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_floor_plan_integration.py
git commit -m "test: add end-to-end integration tests for upgraded floor plan pipeline"
```

---

### Task 10: Final verification and cleanup

- [ ] **Step 1: Run the full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Verify .env has CLAUDE_API_KEY**

Run: `cd backend && grep CLAUDE_API_KEY .env`
Expected: Line showing `CLAUDE_API_KEY=sk-ant-...` (or similar)

- [ ] **Step 3: Verify the API endpoint works (manual smoke test)**

Run a curl or httpie call against the running server:

```bash
curl -X POST http://localhost:8000/api/development/ai-floor-plan/ \
  -H "Content-Type: application/json" \
  -d '{
    "footprint": {"type": "Polygon", "coordinates": [[[0,0],[78.74,0],[78.74,39.37],[0,39.37],[0,0]]]},
    "n_floors": 12,
    "building_height_m": 36.0,
    "units_per_core": 4,
    "segment": "mid",
    "unit_mix": ["2BHK", "3BHK"]
  }'
```

Expected: JSON response with `status: "ok"`, `layout` with room features, `svg_blueprint` with north arrow and structural grid

- [ ] **Step 4: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: complete floor plan upgrade — GDCR-aware AI layout + professional SVG rendering"
```
