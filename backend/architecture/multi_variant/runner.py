"""
architecture/multi_variant/runner.py — Run pipeline per preset, collect results, rank (Phase 6.2).

Steps 1–5 are run by the caller once; this module runs 5b and 5c per preset with merged config.
Skeleton is read-only; no mutation.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ai_layer.merge import merge_config
from ai_layer.schemas import ENGINE_CONFIG_ALLOWED_KEYS
from residential_layout import (
    build_building_layout,
    build_floor_layout,
    BuildingAggregationError,
    FloorAggregationError,
    FloorAggregationValidationError,
)
from residential_layout.repetition import DEFAULT_MODULE_WIDTH_M

from architecture.multi_variant.contracts import MultiVariantResult, VariantResult
from architecture.multi_variant.presets import (
    ENGINE_DEFAULTS,
    PRESET_ORDER,
    preset_to_advisor_like,
)

# Default storey height when not overridden by preset (plan Section 5).
DEFAULT_STOREY_HEIGHT_M = 3.0


def run_multi_variant(
    skeleton: Any,
    height_limit_m: float,
    plot_id: str,
    storey_height_default: float = DEFAULT_STOREY_HEIGHT_M,
    module_width_default: float = DEFAULT_MODULE_WIDTH_M,
    building_id: str = "B0",
    ai_compare: bool = False,
    selected_presets: Optional[List[str]] = None,
) -> MultiVariantResult:
    """
    Run 5b and 5c for each preset; collect VariantResults; compute deterministic ranking.
    Caller must have run Steps 1–5 once; skeleton is reused and must not be mutated by 5b/5c.
    If selected_presets is given, only those presets are run; order is always PRESET_ORDER.
    """
    if selected_presets is None:
        presets_to_run = list(PRESET_ORDER)
    else:
        # Preserve canonical order for determinism; ignore user order.
        presets_to_run = [p for p in PRESET_ORDER if p in selected_presets]

    variants: list[VariantResult] = []

    for preset_name in presets_to_run:
        advisor_like = preset_to_advisor_like(preset_name)
        merged = merge_config(
            hard_constraints=None,
            user_overrides=None,
            advisor_suggestion=advisor_like,
            defaults=ENGINE_DEFAULTS,
        )
        merged = {k: v for k, v in merged.items() if k in ENGINE_CONFIG_ALLOWED_KEYS}

        module_width_m = merged.get("preferred_module_width")
        if module_width_m is None:
            module_width_m = module_width_default
        else:
            module_width_m = float(module_width_m)

        storey_height_m = merged.get("storey_height_override")
        if storey_height_m is None:
            storey_height_m = storey_height_default
        else:
            storey_height_m = float(storey_height_m)

        try:
            floor_contract = build_floor_layout(
                skeleton, floor_id="L0", module_width_m=module_width_m
            )
        except (FloorAggregationError, FloorAggregationValidationError) as exc:
            variants.append(
                VariantResult(
                    preset_name=preset_name,
                    final_config_used=dict(merged),  # merged config passed to engine (audit)
                    building_contract_summary=None,
                    success_flag=False,
                    failure_reason=str(exc),
                )
            )
            continue

        try:
            building_contract = build_building_layout(
                skeleton,
                height_limit_m=height_limit_m,
                storey_height_m=storey_height_m,
                building_id=building_id,
                module_width_m=module_width_m,
                first_floor_contract=floor_contract,
            )
        except BuildingAggregationError as exc:
            variants.append(
                VariantResult(
                    preset_name=preset_name,
                    final_config_used=dict(merged),  # merged config passed to engine (audit)
                    building_contract_summary=None,
                    success_flag=False,
                    failure_reason=str(exc),
                )
            )
            continue

        from ai_layer.evaluator import build_contract_summary

        floors_data = [
            (
                f.floor_id,
                f.total_units,
                f.unit_area_sum,
                f.efficiency_ratio_floor,
            )
            for f in building_contract.floors
        ]
        summary = build_contract_summary(
            building_id=building_contract.building_id,
            total_floors=building_contract.total_floors,
            total_units=building_contract.total_units,
            total_unit_area=building_contract.total_unit_area,
            total_residual_area=building_contract.total_residual_area,
            building_efficiency=building_contract.building_efficiency,
            building_height_m=building_contract.building_height_m,
            floors=floors_data,
        )
        variants.append(
            VariantResult(
                preset_name=preset_name,
                final_config_used=dict(merged),  # merged config passed to engine (audit)
                building_contract_summary=summary,
                success_flag=True,
                failure_reason=None,
                building_contract=building_contract,
            )
        )

    ranking = _compute_ranking(variants)
    comparison_note: Optional[str] = None
    if ai_compare:
        comparison_note = _optional_ai_compare(variants)

    # Phase A: first successful preset in ranking (best-ranked); None if all failed.
    best_preset_name: Optional[str] = None
    best_variant_index: Optional[int] = None
    if ranking:
        first_name = ranking[0]
        for i, v in enumerate(variants):
            if v.preset_name == first_name and v.success_flag and v.building_contract is not None:
                best_preset_name = first_name
                best_variant_index = i
                break

    return MultiVariantResult(
        plot_id=plot_id,
        building_id=building_id,
        variants=variants,
        ranking=ranking,
        comparison_note=comparison_note,
        best_preset_name=best_preset_name,
        best_variant_index=best_variant_index,
    )


def _compute_ranking(variants: list[VariantResult]) -> list[str]:
    """
    Deterministic ranking: relative normalization over successful variants only.
    Maxima (max_total_units, max_avg, max_residual) are computed from successful
    variants only; failed variants never influence normalization. Failed variants
    are always placed after all successful ones (same order as in variants).
    Tie-break among successful: PRESET_ORDER (lower index wins).
    """
    successful = [v for v in variants if v.success_flag and v.building_contract_summary]
    if not successful:
        return [v.preset_name for v in variants]

    def avg_unit_area(s: Any) -> float:
        if s.total_units and s.total_units > 0:
            return s.total_unit_area / s.total_units
        return 0.0

    max_total_units = max(s.building_contract_summary.total_units for s in successful)
    if max_total_units == 0:
        max_total_units = 1
    max_avg = max(avg_unit_area(s.building_contract_summary) for s in successful)
    if max_avg == 0:
        max_avg = 1.0
    max_residual = max(
        s.building_contract_summary.total_residual_area for s in successful
    )
    if max_residual == 0:
        max_residual = 1.0

    order_idx = {name: i for i, name in enumerate(PRESET_ORDER)}

    def score(v: VariantResult) -> tuple[float, int]:
        s = v.building_contract_summary
        if not s:
            return (-1.0, order_idx.get(v.preset_name, 999))
        n_units = s.total_units
        av = avg_unit_area(s)
        eff = s.building_efficiency
        res = s.total_residual_area
        norm_units = n_units / max_total_units
        norm_avg = av / max_avg
        norm_res = res / max_residual

        if v.preset_name == "SPACIOUS":
            sc = norm_avg
        elif v.preset_name == "DENSE":
            sc = norm_units
        elif v.preset_name == "BALANCED":
            sc = eff
        elif v.preset_name == "BUDGET":
            sc = 0.5 * (1.0 - norm_res) + 0.5 * eff
        else:
            sc = eff
        return (sc, order_idx.get(v.preset_name, 999))

    sorted_successful = sorted(successful, key=score, reverse=True)
    ranking = [v.preset_name for v in sorted_successful]
    failed = [v.preset_name for v in variants if not v.success_flag]
    for name in failed:
        ranking.append(name)
    return ranking


def _optional_ai_compare(variants: list[VariantResult]) -> Optional[str]:
    """
    Build compact payload (building-level metrics only), call AI Evaluator for
    comparative explanation. AI does not select winner. Returns comparison_note or None.
    """
    successful = [v for v in variants if v.success_flag and v.building_contract_summary]
    if not successful:
        return None
    try:
        from ai_layer import get_ai_config, evaluate_building
    except ImportError:
        return None
    config = get_ai_config()
    if not config.evaluator_enabled or not config.has_api_key():
        return None

    # Compact payload: scalar building-level only (plan Section 7).
    lines = []
    for v in successful:
        s = v.building_contract_summary
        if not s:
            continue
        lines.append(
            f"{v.preset_name}: total_units={s.total_units} total_unit_area={s.total_unit_area:.1f} "
            f"total_residual_area={s.total_residual_area:.1f} building_efficiency={s.building_efficiency:.2f} "
            f"building_height_m={s.building_height_m:.1f} total_floors={s.total_floors}"
        )
    if not lines:
        return None
    user_msg = "Compare these layout variants (building-level only). Provide a short comparative explanation. Do not pick a winner.\n\n" + "\n".join(lines)

    from ai_layer.client import call_openai, parse_json_response

    raw = call_openai(
        model=config.evaluator_model,
        system_prompt=(
            "You are an advisory assistant. Compare the given layout variants. "
            "Output a JSON object with a single key 'explanation' (string). "
            "Respond with a single JSON object and nothing else. No markdown, no code blocks."
        ),
        user_prompt=user_msg,
        timeout_s=config.evaluator_timeout_s,
        temperature=config.temperature,
        rate_limit_kind="advisor",
    )
    if not raw:
        return None
    obj = parse_json_response(raw)
    if not obj or "explanation" not in obj:
        return None
    expl = obj.get("explanation")
    return str(expl).strip() if expl else None
