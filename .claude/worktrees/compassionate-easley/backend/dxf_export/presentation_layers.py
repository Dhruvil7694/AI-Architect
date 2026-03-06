"""
dxf_export/presentation_layers.py
-----------------------------------
Layer definitions for the Presentation Engine DXF exporter.

Separate from layers.py (which defines the original skeleton exporter layers)
so neither file is modified.  Both files can coexist in the same ezdxf document
without conflict.

Layer inventory
---------------
A-WALL-EXT  color  7 (white)       lw 35  CONTINUOUS  external double-line walls
A-WALL-INT  color 253 (light grey) lw 18  CONTINUOUS  internal partitions
A-CORE      color  1 (red)         lw 50  CONTINUOUS  core thick walls
A-DOOR      color  4 (cyan)        lw 18  CONTINUOUS  door leaf + arc
A-CORR      color  3 (green)       lw 13  DASHED      corridor zone indicator
A-TEXT      color  6 (magenta)     lw 18  CONTINUOUS  room labels + title block
A-DIM       color  2 (yellow)      lw 13  CONTINUOUS  (Phase 3 only — reserved)
"""

import ezdxf

# ── Layer table ────────────────────────────────────────────────────────────────
# Each entry: {"color": int, "lineweight": int (hundredths of mm), "linetype": str}

PRESENTATION_LAYER_DEFS: dict[str, dict] = {
    "A-WALL-EXT": {"color":  7,  "lineweight": 35, "linetype": "CONTINUOUS"},
    "A-WALL-INT": {"color": 253, "lineweight": 18, "linetype": "CONTINUOUS"},
    "A-CORE":     {"color":  1,  "lineweight": 50, "linetype": "CONTINUOUS"},
    "A-DOOR":     {"color":  4,  "lineweight": 18, "linetype": "CONTINUOUS"},
    "A-CORR":     {"color":  3,  "lineweight": 13, "linetype": "DASHED"},
    "A-TEXT":     {"color":  6,  "lineweight": 18, "linetype": "CONTINUOUS"},
    "A-DIM":      {"color":  2,  "lineweight": 13, "linetype": "CONTINUOUS"},
}


def setup_presentation_layers(doc: ezdxf.document.Drawing) -> None:
    """
    Create all presentation DXF layers on *doc*.

    Safe to call on a document that already has these layers — layers are only
    created when they do not already exist.

    The DASHED linetype is registered via ezdxf.setup_linetypes() if missing.

    Parameters
    ----------
    doc : ezdxf Drawing object (R2010 or later).
    """
    if "DASHED" not in doc.linetypes:
        ezdxf.setup_linetypes(doc)

    layers = doc.layers
    for name, attrs in PRESENTATION_LAYER_DEFS.items():
        if name not in layers:
            layers.new(
                name,
                dxfattribs={
                    "color":      attrs["color"],
                    "lineweight": attrs["lineweight"],
                    "linetype":   attrs["linetype"],
                },
            )
