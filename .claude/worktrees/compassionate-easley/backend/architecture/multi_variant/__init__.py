"""
architecture/multi_variant — Phase 6.2 Multi-Variant Deterministic Runner.

Orchestration layer above the deterministic engine: run pipeline with multiple
preset configs, compare BuildingLayoutContract summaries, deterministic ranking.
No modification to envelope, placement, skeleton, composer, or aggregation.
"""

from architecture.multi_variant.contracts import (
    MultiVariantResult,
    VariantResult,
)
from architecture.multi_variant.presets import (
    ENGINE_DEFAULTS,
    PRESET_ORDER,
    PRESETS,
    preset_to_advisor_like,
)
from architecture.multi_variant.runner import run_multi_variant

__all__ = [
    "ENGINE_DEFAULTS",
    "MultiVariantResult",
    "PRESET_ORDER",
    "PRESETS",
    "preset_to_advisor_like",
    "run_multi_variant",
    "VariantResult",
]
