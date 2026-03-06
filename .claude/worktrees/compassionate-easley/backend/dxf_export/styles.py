"""
dxf_export/styles.py
--------------------
Minimal text style setup for the DXF exporter.

A single style ARCH_STANDARD is created when it does not already exist.
Font: Arial.ttf (standard AutoCAD fallback — always available).
Height: 0.25 m (character height in metres; overridable per entity).
"""

import ezdxf

STYLE_NAME = "ARCH_STANDARD"
STYLE_FONT  = "Arial.ttf"
STYLE_HEIGHT = 0.25  # metres


def ensure_text_style(doc: ezdxf.document.Drawing) -> None:
    """
    Register ARCH_STANDARD text style on *doc* if not already present.

    Safe to call multiple times — idempotent.

    Parameters
    ----------
    doc : ezdxf Drawing object (R2010 or later).
    """
    if STYLE_NAME not in doc.styles:
        doc.styles.new(
            STYLE_NAME,
            dxfattribs={"font": STYLE_FONT, "height": STYLE_HEIGHT},
        )
