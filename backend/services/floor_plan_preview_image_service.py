"""
floor_plan_preview_image_service.py
------------------------------------
Text-to-image preview for floor plans (separate from the AI layout pipeline).

Uses Hugging Face Inference API (e.g. FLUX.1-schnell) when HUGGINGFACE_API_TOKEN is set.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DXF_TO_M = 0.3048


def footprint_dimensions_m(geojson: Dict[str, Any]) -> Tuple[float, float]:
    """Width × depth in metres from GeoJSON Polygon (DXF feet)."""
    coords = geojson.get("coordinates", [[]])[0]
    if len(coords) < 3:
        return 0.0, 0.0
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    width_dxf = max(xs) - min(xs)
    depth_dxf = max(ys) - min(ys)
    return round(width_dxf * DXF_TO_M, 2), round(depth_dxf * DXF_TO_M, 2)


def build_floor_plan_image_prompt(payload: Dict[str, Any]) -> str:
    """
    Build a detailed English prompt for architectural floor-plan style imagery.

    `payload` matches the preview-image API body: tower inputs plus optional
    `design_notes` and `ai_metrics` from the last AI floor plan response.
    """
    floor_w, floor_d = footprint_dimensions_m(payload["footprint"])
    n_floors = int(payload["n_floors"])
    building_height_m = float(payload["building_height_m"])
    units_per_core = int(payload.get("units_per_core") or 4)
    segment = str(payload.get("segment") or "mid")
    unit_mix: List[str] = payload.get("unit_mix") or []
    storey_height_m = float(payload.get("storey_height_m") or 3.0)
    plot_area_sqm = float(payload.get("plot_area_sqm") or 0.0)
    design_brief = str(payload.get("design_brief") or "").strip()
    design_notes = str(payload.get("design_notes") or "").strip()
    ai_metrics = payload.get("ai_metrics") or {}

    unit_mix_s = ", ".join(unit_mix) if unit_mix else "mixed residential units"

    lines = [
        "Professional architectural floor plan drawing, top-down orthographic view, "
        "black linework on white background, CAD drafting style, clear wall thickness, "
        "dimension lines optional, north arrow, labeled rooms, scale bar, "
        "high contrast, technical illustration, no perspective, no 3D render.",
        f"Rectangular tower footprint approximately {floor_w:.1f} m by {floor_d:.1f} m "
        f"({floor_w * floor_d:.0f} m² per floor).",
        f"Building: {n_floors} floors, total height about {building_height_m:.1f} m, "
        f"typical storey height {storey_height_m:.1f} m.",
        f"Residential segment: {segment}. Target mix: {unit_mix_s}. "
        f"About {units_per_core} units per floor sharing one core (lifts and stairs).",
    ]
    if plot_area_sqm > 0:
        lines.append(f"Site context: total plot area reference {plot_area_sqm:.0f} m².")
    if design_brief:
        lines.append(f"Design brief from client: {design_brief}")
    if design_notes:
        lines.append(f"Layout notes: {design_notes}")

    if isinstance(ai_metrics, dict) and ai_metrics:
        eff = ai_metrics.get("efficiencyPct")
        nu = ai_metrics.get("nUnitsPerFloor")
        net = ai_metrics.get("netBuaSqm")
        lifts = ai_metrics.get("nLifts")
        stairs = ai_metrics.get("nStairs")
        parts = []
        if eff is not None:
            parts.append(f"plate efficiency about {eff}%")
        if nu is not None:
            parts.append(f"{nu} units per typical floor")
        if net is not None:
            parts.append(f"net BUA per floor near {net:.0f} m²")
        if lifts is not None:
            parts.append(f"{lifts} lift(s)")
        if stairs is not None:
            parts.append(f"{stairs} stair(s)")
        if parts:
            lines.append("Derived layout summary: " + "; ".join(parts) + ".")

    lines.append(
        "Avoid photorealistic materials, furniture photography, or isometric views; "
        "keep a clean 2D plan suitable for a zoning submission appendix."
    )
    return "\n".join(lines)


def _hf_inference_url(model_id: str) -> str:
    return f"https://api-inference.huggingface.co/models/{model_id}"


def generate_image_via_huggingface(
    prompt: str,
    *,
    api_token: str,
    model_id: str,
    timeout_s: float = 120.0,
    max_retries: int = 3,
) -> bytes:
    """
    Call HF text-to-image. Returns raw image bytes (PNG/JPEG).

    Retries when the API returns 503 (model loading).
    """
    url = _hf_inference_url(model_id)
    body = json.dumps({"inputs": prompt}).encode("utf-8")
    last_err: Optional[str] = None

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "application/json" in ctype:
                    try:
                        obj = json.loads(data.decode("utf-8"))
                    except json.JSONDecodeError:
                        raise ValueError("HF returned JSON that could not be parsed")
                    if isinstance(obj, dict) and obj.get("error"):
                        raise ValueError(str(obj.get("error")))
                    raise ValueError("Unexpected JSON image response from HF")
                return data
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                err_obj = json.loads(raw)
                msg = err_obj.get("error", raw)
            except json.JSONDecodeError:
                msg = raw or str(e)
            last_err = msg
            if e.code == 503 and "loading" in msg.lower() and attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                logger.info("HF model loading; retry in %ds: %s", wait, msg[:200])
                time.sleep(wait)
                continue
            logger.warning("HF inference HTTP %s: %s", e.code, msg[:500])
            raise ValueError(msg) from e
        except urllib.error.URLError as e:
            last_err = str(e)
            raise ValueError(last_err) from e

    raise ValueError(last_err or "HF inference failed")


def image_bytes_to_base64_png(image_bytes: bytes) -> Tuple[str, str]:
    """Return (base64_str, mime_type)."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return base64.b64encode(image_bytes).decode("ascii"), "image/png"
    if image_bytes[:2] == b"\xff\xd8":
        return base64.b64encode(image_bytes).decode("ascii"), "image/jpeg"
    return base64.b64encode(image_bytes).decode("ascii"), "image/png"
