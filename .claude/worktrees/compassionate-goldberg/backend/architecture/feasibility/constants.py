"""
architecture.feasibility.constants
----------------------------------

Constants and assumptions used in feasibility aggregation.

MATHEMATICAL RISK — Floor count (FSI BUA estimate)
---------------------------------------------------
When no BuildingProposal exists (e.g. generate_floorplan or validate_feasibility_metrics),
we estimate total BUA for FSI as:

    total_bua_sqft = footprint_area_sqft * num_floors
    num_floors     = max(1, int(building_height_m / storey_height_m))

We do NOT assume a fixed storey height. This module exposes a default that can be
overridden by the caller or by client configuration. Architect methodologies vary:

  - 3.0 m  — common default
  - 3.1 m, 3.3 m — alternate norms
  - Podium / stilt exclusion — number of floors may not be height / storey_height
  - Client-specific formula

If this assumption is not aligned with client methodology, FSI and FSI utilization %
in the feasibility report may not match the architect's calculation. The engine
value is strictly for pipeline-only reporting; for authority submission the client
must supply actual BUA (e.g. via BuildingProposal.total_bua) or align storey height.
"""

# Default storey height (m) used only when estimating BUA from height in the
# pipeline (no proposal). Override via build_feasibility_from_pipeline(storey_height_m=...).
DEFAULT_STOREY_HEIGHT_M: float = 3.0
