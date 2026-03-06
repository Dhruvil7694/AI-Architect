"""
architecture/multi_variant/presets.py — Hardcoded preset config deltas for Phase 6.2.

Presets are deterministic; no AI, no randomness. Keys allowlisted only (ENGINE_CONFIG_ALLOWED_KEYS).
"""

from __future__ import annotations

from typing import Any

from ai_layer.schemas import (
    AdvisorOutput,
    ENGINE_CONFIG_ALLOWED_KEYS,
    ALLOWED_TEMPLATE_NAMES,
)

# Fixed order for tie-break and iteration (plan Section 6).
PRESET_ORDER = ["SPACIOUS", "DENSE", "BALANCED", "BUDGET"]

# Engine default baseline (plan Section 4). Must include every key in ENGINE_CONFIG_ALLOWED_KEYS
# so that merge_config() output always has all allowlisted keys (no silent missing-key assumptions).
ENGINE_DEFAULTS: dict[str, Any] = {
    "template_priority_order": ["STANDARD_1BHK", "COMPACT_1BHK", "STUDIO"],
    "preferred_module_width": None,
    "storey_height_override": None,
    "density_bias": None,
    "constraint_flags": {},
    "prefer_compact": None,
    "max_units_per_floor": None,
}

# Preset deltas; only allowlisted keys. Unknown keys stripped at use.
PRESETS: dict[str, dict[str, Any]] = {
    "SPACIOUS": {
        "template_priority_order": ["STANDARD_1BHK", "COMPACT_1BHK"],
        "preferred_module_width": 4.2,
        "storey_height_override": None,
        "density_bias": "luxury",
        "constraint_flags": {},
    },
    "DENSE": {
        "template_priority_order": ["COMPACT_1BHK", "STANDARD_1BHK", "STUDIO"],
        "preferred_module_width": 3.2,
        "storey_height_override": None,
        "density_bias": "density",
        "constraint_flags": {},
    },
    "BALANCED": {},
    "BUDGET": {
        "template_priority_order": ["COMPACT_1BHK", "STUDIO", "STANDARD_1BHK"],
        "preferred_module_width": 3.2,
        "storey_height_override": 2.85,
        "density_bias": None,
        "constraint_flags": {"prefer_compact": True},
    },
}


def _strip_preset(raw: dict[str, Any]) -> dict[str, Any]:
    """Retain only allowlisted keys."""
    return {k: v for k, v in raw.items() if k in ENGINE_CONFIG_ALLOWED_KEYS}


def preset_to_advisor_like(preset_name: str) -> AdvisorOutput:
    """
    Convert preset dict to AdvisorOutput for merge_config (advisor tier).
    Only allowlisted keys; template_priority_order filtered to ALLOWED_TEMPLATE_NAMES.
    """
    raw = PRESETS.get(preset_name, {})
    delta = _strip_preset(raw)

    tpo = delta.get("template_priority_order")
    if isinstance(tpo, list):
        tpo = [x for x in tpo if isinstance(x, str) and x in ALLOWED_TEMPLATE_NAMES]
    else:
        tpo = []

    pmw = delta.get("preferred_module_width")
    if pmw is not None and not isinstance(pmw, (int, float)):
        pmw = None

    sho = delta.get("storey_height_override")
    if sho is not None and not isinstance(sho, (int, float)):
        sho = None

    db = delta.get("density_bias")
    if db not in ("luxury", "density", "balanced"):
        db = None

    cf = delta.get("constraint_flags")
    if not isinstance(cf, dict):
        cf = {}
    cf = {k: v for k, v in cf.items() if k in {"prefer_compact", "max_units_per_floor"}}

    return AdvisorOutput(
        template_priority_order=tpo,
        preferred_module_width=float(pmw) if pmw is not None else None,
        storey_height_override=float(sho) if sho is not None else None,
        density_bias=db,
        constraint_flags=cf,
    )
