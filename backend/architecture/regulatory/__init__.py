from __future__ import annotations

"""
architecture.regulatory
-----------------------

Regulatory helper modules for GDCR/NBC-driven calculations that sit
on top of the core geometry engines (envelope, placement, skeleton,
layout) without modifying them.

This package is intentionally thin and deterministic; it reuses existing
pipeline artefacts and central YAML accessors rather than duplicating
regulatory logic.
"""

