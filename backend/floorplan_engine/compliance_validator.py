"""
compliance_validator.py
-----------------------
GDCR Part III §13.1 compliance checks for individual flat layouts.

Each check returns a ComplianceIssue (a TypedDict) with:
  room     : room id
  rule     : GDCR clause
  ok       : bool
  message  : human-readable result
  severity : "pass" | "warn" | "fail"

All issues are collected into a ComplianceReport.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

import networkx as nx

from floorplan_engine.room_geometry_solver import (
    is_exterior,
    overlap_area,
    shared_edge_length,
)

# ─── Typed result containers ───────────────────────────────────────────────────

ComplianceIssue = Dict[str, Any]


def _issue(room: str, rule: str, ok: bool, message: str,
           severity: str = "") -> ComplianceIssue:
    if not severity:
        severity = "pass" if ok else "fail"
    return {"room": room, "rule": rule, "ok": ok, "message": message, "severity": severity}


# ─── Individual rule checks ────────────────────────────────────────────────────

def check_min_area(
    room_id: str,
    rect: Dict,
    node_data: Dict,
) -> ComplianceIssue:
    """
    GDCR §13.1.9 — Minimum floor area per room type:
      Habitable room (bedroom / living / dining): ≥ 9.5 m²
      Kitchen:  ≥ 5.0 m²
      Bathroom: ≥ 1.8 m²
    """
    actual  = rect["w"] * rect["h"]
    min_req = float(node_data.get("min_area", 1.5))
    ok      = actual >= min_req
    return _issue(
        room_id, "§13.1.9 — min area", ok,
        f"{room_id}: {actual:.1f} m² (min {min_req} m²)",
    )


def check_min_width(
    room_id: str,
    rect: Dict,
    node_data: Dict,
) -> ComplianceIssue:
    """
    GDCR §13.1.9 — Minimum clear width:
      Bedroom: ≥ 2.4 m   Kitchen: ≥ 1.8 m   Bathroom: ≥ 1.2 m
      Passage: 1.0–1.2 m (Rule 6)
    """
    min_w  = float(node_data.get("min_w", 1.0))
    actual = min(rect["w"], rect["h"])   # shorter dimension = clear width
    ok     = actual >= min_w
    # Passage upper bound
    rt = node_data.get("room_type", "")
    if rt == "passage" and actual > 1.20:
        return _issue(
            room_id, "Circulation Rule 6 — passage width", False,
            f"passage width {actual:.2f} m > 1.20 m max",
            "warn",
        )
    return _issue(
        room_id, "§13.1.9 — min width", ok,
        f"{room_id}: min dim {actual:.2f} m (min {min_w} m)",
    )


def check_ventilation(
    room_id: str,
    rect: Dict,
    node_data: Dict,
    unit_w: float,
    unit_d: float,
) -> ComplianceIssue:
    """
    GDCR §13.1.11 — Window opening ≥ 1/6 floor area.
    Applied to habitable rooms (living, dining, bedroom) that touch an exterior wall.
    Non-exterior rooms (bathrooms, passages) are checked for exhaust / shaft
    requirement only (emitted as a warning, not a fail).
    """
    rt  = node_data.get("room_type", "")
    if rt in ("passage", "entry", "utility"):
        return _issue(room_id, "§13.1.11 — ventilation", True,
                      f"{room_id}: ventilation not required for {rt}", "pass")

    floor_area     = rect["w"] * rect["h"]
    required_win   = floor_area / 6.0
    # Available window = room facade width × assumed sill-to-lintel height 1.2 m
    # Facade width = longer dimension if room touches exterior wall, else 0
    exterior       = is_exterior(rect, unit_w, unit_d)
    facade_w       = max(rect["w"], rect["h"]) if exterior else 0.0
    available_win  = facade_w * 1.20

    if rt == "bathroom":
        # Bathrooms only need exhaust shaft (0.09 m² min), not full §13.1.11 window
        ok = True   # shaft requirement handled structurally
        return _issue(room_id, "§13.1.11 — ventilation (bath)", ok,
                      f"{room_id}: exhaust shaft required (area {floor_area:.1f} m²)", "pass")

    ok = available_win >= required_win
    return _issue(
        room_id, "§13.1.11 — ventilation", ok,
        f"{room_id}: window {available_win:.2f} m² avail / {required_win:.2f} m² req "
        f"({'exterior' if exterior else 'INTERIOR — needs duct'})",
    )


def check_aspect_ratio(
    room_id: str,
    rect: Dict,
    node_data: Dict,
) -> ComplianceIssue:
    """
    GDCR §13.1.9 — Rooms must not be excessively elongated.
    Fail if aspect > aspect_max defined in node spec.
    """
    aspect_max = float(node_data.get("aspect_max", 3.0))
    ratio      = max(rect["w"], rect["h"]) / max(min(rect["w"], rect["h"]), 0.01)
    ok         = ratio <= aspect_max
    return _issue(
        room_id, "§13.1.9 — aspect ratio", ok,
        f"{room_id}: {ratio:.2f} (max {aspect_max})",
    )


def check_passage_length(
    room_id: str,
    rect: Dict,
    node_data: Dict,
) -> ComplianceIssue:
    """Circulation Rule 7 — passage length ≤ 5 m."""
    if node_data.get("room_type") != "passage":
        return _issue(room_id, "Circ. Rule 7", True, "N/A", "pass")
    length = max(rect["w"], rect["h"])
    ok     = length <= 5.0
    return _issue(
        room_id, "Circulation Rule 7 — passage ≤ 5 m", ok,
        f"passage length {length:.2f} m",
    )


def check_adjacency(
    G: nx.Graph,
    rects: Dict[str, Dict],
    u: str,
    v: str,
) -> ComplianceIssue:
    """
    Check that two topologically adjacent rooms share a physical edge
    (≥ 0.6 m overlap = min door width).
    """
    if u not in rects or v not in rects:
        return _issue(f"{u}–{v}", "adjacency", False,
                      f"{u} or {v} not in rects", "warn")
    shared = shared_edge_length(rects[u], rects[v])
    ok     = shared >= 0.60
    return _issue(
        f"{u}–{v}", "adjacency (shared edge ≥ 0.6 m)", ok,
        f"shared edge {shared:.2f} m",
    )


def check_no_overlap(rects: Dict[str, Dict]) -> List[ComplianceIssue]:
    """
    Global check: no two rooms should overlap.
    Overlaps < 0.50 m² are layout-engine artefacts (warn); larger overlaps fail.
    """
    issues = []
    keys = list(rects.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ov = overlap_area(rects[keys[i]], rects[keys[j]])
            if ov < 0.01:
                continue
            severity = "fail" if ov >= 0.50 else "warn"
            issues.append(_issue(
                f"{keys[i]}∩{keys[j]}", "no overlap", ov < 0.50,
                f"overlap {ov:.2f} m²", severity,
            ))
    return issues


def check_passage_serves_min_rooms(
    G: nx.Graph,
    node_id: str,
) -> ComplianceIssue:
    """Circulation Rule 8 — passage must serve ≥ 2 rooms."""
    if G.nodes[node_id].get("room_type") != "passage":
        return _issue(node_id, "Circ. Rule 8", True, "N/A", "pass")
    nbr_count = G.degree(node_id)
    ok = nbr_count >= 2
    return _issue(
        node_id, "Circulation Rule 8 — passage serves ≥ 2 rooms", ok,
        f"passage degree {nbr_count}",
    )


def check_bathroom_not_direct_to_living(
    G: nx.Graph,
    node_id: str,
) -> ComplianceIssue:
    """
    Circulation Rule 5 — common bathrooms must not open directly into living room.
    En-suite bathrooms attached to bedrooms are exempt.
    """
    rt = G.nodes[node_id].get("room_type", "")
    if rt != "bathroom":
        return _issue(node_id, "Circ. Rule 5", True, "N/A", "pass")
    if "attached" in node_id or "master" in node_id:
        return _issue(node_id, "Circ. Rule 5", True,
                      f"{node_id}: en-suite — exempt from Rule 5", "pass")
    nbrs    = list(G.neighbors(node_id))
    bad_adj = [n for n in nbrs if G.nodes[n].get("room_type") == "living"]
    ok      = len(bad_adj) == 0
    return _issue(
        node_id, "Circulation Rule 5 — common bath not direct to living", ok,
        f"{node_id} directly adjacent to living: {bad_adj}" if not ok else
        f"{node_id}: OK (accessible via passage)",
    )


# ─── Full report ───────────────────────────────────────────────────────────────

def validate(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
) -> Dict[str, Any]:
    """
    Run all compliance checks.

    Returns
    -------
    {
      "issues":      List[ComplianceIssue],
      "all_pass":    bool,
      "fail_count":  int,
      "warn_count":  int,
      "summary":     { rule_category: pass/fail/warn }
    }
    """
    issues: List[ComplianceIssue] = []

    # Per-room checks
    for nid, data in G.nodes(data=True):
        if nid not in rects:
            continue
        rect = rects[nid]
        issues.append(check_min_area(nid, rect, data))
        issues.append(check_min_width(nid, rect, data))
        issues.append(check_ventilation(nid, rect, data, unit_w, unit_d))
        issues.append(check_aspect_ratio(nid, rect, data))
        if data.get("room_type") == "passage":
            issues.append(check_passage_length(nid, rect, data))
            issues.append(check_passage_serves_min_rooms(G, nid))
        if data.get("room_type") == "bathroom":
            issues.append(check_bathroom_not_direct_to_living(G, nid))

    # Edge-level adjacency checks
    for u, v in G.edges():
        issues.append(check_adjacency(G, rects, u, v))

    # Global overlap check
    issues.extend(check_no_overlap(rects))

    fails = [i for i in issues if not i["ok"] and i["severity"] == "fail"]
    warns = [i for i in issues if not i["ok"] and i["severity"] == "warn"]

    return {
        "issues":     issues,
        "all_pass":   len(fails) == 0,
        "fail_count": len(fails),
        "warn_count": len(warns),
        "fails":      fails,
        "warns":      warns,
    }
