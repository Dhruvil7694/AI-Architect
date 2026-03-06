"""
dxf_export/layers.py
--------------------
Fixed layer definitions for the DXF exporter.

Six layers are created unconditionally on every new document.
All names are prefixed A_ (Architecture standard).
Layer creation is idempotent — safe to call on any new ezdxf document.

Layer inventory
---------------
A_FOOTPRINT  color 7  (white)    CONTINUOUS  — outer footprint boundary
A_CORE       color 1  (red)      CONTINUOUS  — core strip polygon
A_CORRIDOR   color 3  (green)    CONTINUOUS  — corridor strip polygon
A_UNITS      color 2  (yellow)   CONTINUOUS  — unit zone polygons (all)
A_TEXT       color 6  (magenta)  CONTINUOUS  — summary annotation text
A_AUDIT      color 8  (grey)     DASHED      — reserved, intentionally empty in POC v1
"""

import ezdxf

# ── Layer definitions ──────────────────────────────────────────────────────────
# Each entry: (aci_color, linetype)

LAYER_DEFS: dict[str, tuple[int, str]] = {
    "A_FOOTPRINT": (7,  "CONTINUOUS"),
    "A_CORE":      (1,  "CONTINUOUS"),
    "A_CORRIDOR":  (3,  "CONTINUOUS"),
    "A_UNITS":     (2,  "CONTINUOUS"),
    "A_TEXT":      (6,  "CONTINUOUS"),
    "A_AUDIT":     (8,  "DASHED"),
}


def setup_layers(doc: ezdxf.document.Drawing) -> None:
    """
    Create all fixed DXF layers on *doc*.

    The DASHED linetype is registered via ezdxf.setup_linetypes() if it is
    not already present in the document.  All other layers use CONTINUOUS
    which is always available in any new DXF document.

    Parameters
    ----------
    doc : ezdxf Drawing object (R2010 or later).
    """
    # Ensure all standard linetypes (including DASHED) are available
    if "DASHED" not in doc.linetypes:
        ezdxf.setup_linetypes(doc)

    layers = doc.layers
    for name, (color, linetype) in LAYER_DEFS.items():
        if name not in layers:
            layers.new(name, dxfattribs={"color": color, "linetype": linetype})
