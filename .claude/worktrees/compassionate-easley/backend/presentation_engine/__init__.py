"""
presentation_engine
-------------------
Converts a FloorSkeleton into a professional schematic DXF floor plan.

Pipeline (all stages wrapped in per-stage try/except in drawing_composer):

    FloorSkeleton
        → wall_builder      (double-line walls with three-tier fallback)
        → room_splitter     (max-1 toilet+room split per unit zone)
        → door_placer       (LINE + ARC symbolic overlays)
        → annotation_builder(title block + room labels)
        → PresentationModel (frozen dataclass)

Public API
----------
    from presentation_engine.drawing_composer import compose

    pm = compose(skeleton, tp_num=14, fp_num=101, height_m=16.5)
"""
