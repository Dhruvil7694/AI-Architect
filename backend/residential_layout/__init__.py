"""
residential_layout — Phase 2 deterministic unit composer.

One zone + frame + template → one UnitLayoutContract.
No AI, no search, no optimization. Stability first.
"""

from residential_layout.models import UnitLayoutContract, RoomInstance
from residential_layout.errors import (
    UnitZoneTooSmallError,
    LayoutCompositionError,
    UnresolvedLayoutError,
)
from residential_layout.frames import ComposerFrame, derive_unit_local_frame
from residential_layout.templates import (
    UnitTemplate,
    RoomTemplate,
    STANDARD_1BHK,
    COMPACT_1BHK,
    STUDIO,
    get_unit_template,
)
from residential_layout.composer import compose_unit
from residential_layout.orchestrator import (
    resolve_unit_layout,
    resolve_unit_layout_from_skeleton,
)
from residential_layout.repetition import (
    repeat_band,
    BandLayoutContract,
    BandRepetitionError,
    BandRepetitionValidationError,
)
from residential_layout.floor_aggregation import (
    build_floor_layout,
    FloorLayoutContract,
    FloorAggregationError,
    FloorAggregationValidationError,
)
from residential_layout.building_aggregation import (
    build_building_layout,
    BuildingLayoutContract,
    BuildingAggregationError,
    BuildingAggregationValidationError,
)

__all__ = [
    "UnitLayoutContract",
    "RoomInstance",
    "UnitZoneTooSmallError",
    "LayoutCompositionError",
    "UnresolvedLayoutError",
    "ComposerFrame",
    "derive_unit_local_frame",
    "UnitTemplate",
    "RoomTemplate",
    "STANDARD_1BHK",
    "COMPACT_1BHK",
    "STUDIO",
    "get_unit_template",
    "compose_unit",
    "resolve_unit_layout",
    "resolve_unit_layout_from_skeleton",
    "repeat_band",
    "BandLayoutContract",
    "BandRepetitionError",
    "BandRepetitionValidationError",
    "build_floor_layout",
    "FloorLayoutContract",
    "FloorAggregationError",
    "FloorAggregationValidationError",
    "build_building_layout",
    "BuildingLayoutContract",
    "BuildingAggregationError",
    "BuildingAggregationValidationError",
]
