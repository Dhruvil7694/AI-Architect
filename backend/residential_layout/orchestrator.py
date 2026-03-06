"""
residential_layout/orchestrator.py — Resolution layer.

resolve_unit_layout(zone, frame) tries STANDARD_1BHK → COMPACT_1BHK → STUDIO.
Logs every transition; raises UnresolvedLayoutError when all fail.
No silent fallback. No repetition.
"""

from __future__ import annotations

import logging
import time
from typing import List

from floor_skeleton.models import UnitZone, FloorSkeleton

from residential_layout.composer import compose_unit
from residential_layout.errors import (
    UnitZoneTooSmallError,
    LayoutCompositionError,
    UnresolvedLayoutError,
)
from residential_layout.frames import ComposerFrame, derive_unit_local_frame
from residential_layout.models import UnitLayoutContract
from residential_layout.templates import get_unit_template

logger = logging.getLogger("residential_layout.orchestrator")

TEMPLATE_ORDER = [
    "STANDARD_5BHK",
    "STANDARD_4BHK",
    "STANDARD_3BHK",
    "STANDARD_2BHK",
    "STANDARD_1BHK",
    "COMPACT_1BHK",
    "STUDIO",
]
PHASE = "unit_composer"


def _failure_type_from_exception(e: UnitZoneTooSmallError | LayoutCompositionError) -> str:
    """Map exception to plan failure_type for logging."""
    if isinstance(e, UnitZoneTooSmallError):
        return "ZoneTooSmall"
    assert isinstance(e, LayoutCompositionError)
    rc = getattr(e, "reason_code", "") or ""
    if rc == "room_min_dim_fail":
        return "RoomMinDimensionFail"
    if rc == "connectivity_fail":
        return "ConnectivityFail"
    if rc == "wet_wall_alignment_fail":
        return "WetWallAlignmentFail"
    if rc == "width_budget_fail":
        return "WidthBudgetFail"
    return "LayoutCompositionError"


def _log_transition(
    template_tried: str,
    failure_type: str,
    reason_code: str,
    next_template: str,
    band_id: int,
) -> None:
    """Structured log entry for every fallback transition. No silent fallback."""
    timestamp = time.time()
    logger.info(
        "phase=%s template_tried=%s failure_type=%s reason_code=%s next_template=%s band_id=%s timestamp=%s",
        PHASE,
        template_tried,
        failure_type,
        reason_code,
        next_template,
        band_id,
        timestamp,
    )


def resolve_unit_layout(zone: UnitZone, frame: ComposerFrame) -> UnitLayoutContract:
    """
    Resolution: try STANDARD_5BHK → STANDARD_4BHK → STANDARD_3BHK → STANDARD_2BHK
    → STANDARD_1BHK → COMPACT_1BHK → STUDIO.
    On first success return UnitLayoutContract. On all failure raise UnresolvedLayoutError
    with failure_reasons and log every transition (template_tried, failure_type, reason_code,
    next_template, band_id). No silent fallback.
    """
    failure_reasons: List[dict] = []
    band_id = frame.band_id

    for i, template_name in enumerate(TEMPLATE_ORDER):
        template = get_unit_template(template_name)
        try:
            contract = compose_unit(zone, frame, template)
            contract.resolved_template_name = template_name
            return contract
        except (UnitZoneTooSmallError, LayoutCompositionError) as e:
            reason_code = getattr(e, "reason_code", "") or ""
            failure_type = _failure_type_from_exception(e)
            next_template = TEMPLATE_ORDER[i + 1] if i + 1 < len(TEMPLATE_ORDER) else "UNRESOLVED"

            record = {
                "template_tried": template_name,
                "failure_type": failure_type,
                "reason_code": reason_code,
                "next_template": next_template,
                "band_id": band_id,
            }
            failure_reasons.append(record)
            _log_transition(
                template_tried=template_name,
                failure_type=failure_type,
                reason_code=reason_code,
                next_template=next_template,
                band_id=band_id,
            )
            if next_template == "UNRESOLVED":
                break
            continue

    raise UnresolvedLayoutError(
        f"All templates exhausted for band_id={band_id}; tried {TEMPLATE_ORDER}",
        failure_reasons=failure_reasons,
    )


def resolve_unit_layout_from_skeleton(
    skeleton: FloorSkeleton,
    zone_index: int,
) -> UnitLayoutContract:
    """
    Wrapper: derive frame, pull zone, call resolve_unit_layout.
    No placement_label or skeleton internals passed. No repetition.
    """
    zone = skeleton.unit_zones[zone_index]
    frame = derive_unit_local_frame(skeleton, zone_index)
    return resolve_unit_layout(zone, frame)
