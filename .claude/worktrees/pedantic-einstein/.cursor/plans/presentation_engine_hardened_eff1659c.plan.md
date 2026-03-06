---
name: Presentation Engine Hardened
overview: Design a production-hardened `presentation_engine` module that converts `FloorSkeleton` into a professional schematic DXF with double-line walls, deterministic room subdivision, symbolic door overlays, and a structured title block — with an explicit three-tier fallback guarantee that prevents any crash in `generate_floorplan`.
todos: []
isProject: false
---

# Presentation Engine — Hardened Technical Design

## Pipeline Position

```mermaid
flowchart TD
    FS["FloorSkeleton\n(floor_skeleton/models.py)"]
    DC["drawing_composer.py\norchestrator + fallback guard"]

    subgraph pe [backend/presentation_engine/]
        WB["wall_builder.py"]
        RS["room_splitter.py"]
        DP["door_placer.py"]
        AB["annotation_builder.py"]
    end

    PM["PresentationModel\n(frozen dataclass)"]
    PX["presentation_exporter.py\nexport_presentation_to_dxf()"]
    DXF[".dxf file"]

    EX["export_floor_skeleton_to_dxf()\n(existing — untouched)"]

    FS --> DC
    DC --> WB
    DC --> RS
    DC --> DP
    DC --> AB
    WB & RS & DP & AB --> PM
    PM --> PX --> DXF
    DC -- "any stage fails" --> EX --> DXF
```



The existing `[backend/dxf_export/exporter.py](backend/dxf_export/exporter.py)` is **never modified**. A parallel `presentation_exporter.py` is added inside `backend/dxf_export/`. The `generate_floorplan` command gains `--presentation` flag; the existing codepath is the fallback.

---

## 1. Module Structure

```
backend/presentation_engine/
├── __init__.py
├── models.py              # PresentationModel + WallGeometry + RoomGeometry + DoorSymbol
├── wall_builder.py        # Double-line external/core walls;
```

