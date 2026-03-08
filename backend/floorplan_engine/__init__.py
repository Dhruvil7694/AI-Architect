"""
floorplan_engine
================
Graph-based residential flat layout generator.

Pipeline
--------
Claude topology JSON
  → topology_generator   : NetworkX annotated graph
  → graph_layout_solver  : 2-D force-directed embedding (metres)
  → room_geometry_solver : Rectangles with area constraints
  → layout_optimizer     : Collision resolution + simulated annealing
  → compliance_validator : GDCR §13 checks
  → renderer_svg         : Professional SVG floor plan

Entry point
-----------
  from floorplan_engine.pipeline import generate_floorplan_svg
  from floorplan_engine.pipeline import generate_floorplan
"""
