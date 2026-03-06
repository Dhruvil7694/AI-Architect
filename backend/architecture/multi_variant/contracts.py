"""
architecture/multi_variant/contracts.py — VariantResult and MultiVariantResult (Phase 6.2).

Scalar summaries always; optional building_contract on success for export (Phase A).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from ai_layer.schemas import ContractSummary

if TYPE_CHECKING:
    from residential_layout.building_aggregation import BuildingLayoutContract


@dataclass
class VariantResult:
    """Single preset run: config used, summary if success, failure reason if failed."""

    preset_name: str
    final_config_used: dict[str, Any]  # merged config actually passed to engine (audit)
    building_contract_summary: Optional[ContractSummary]
    success_flag: bool
    failure_reason: Optional[str]
    # Phase A: when success, store the contract used for this preset (for DXF export without recomputation).
    building_contract: Optional["BuildingLayoutContract"] = None


@dataclass
class MultiVariantResult:
    """Result of multi-variant run: one VariantResult per preset, ranking, optional AI comparison."""

    plot_id: str
    building_id: str
    variants: list[VariantResult]
    ranking: list[str]
    comparison_note: Optional[str]
    # Phase A: first successful preset in ranking; None if all failed (runner always passes these).
    best_preset_name: Optional[str]
    best_variant_index: Optional[int]
