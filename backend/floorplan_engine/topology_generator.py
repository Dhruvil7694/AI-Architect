"""
topology_generator.py
---------------------
Convert Claude topology JSON into an annotated NetworkX graph.

Each node carries:
  area        – target floor area (m²)
  min_area    – GDCR minimum (m²)
  min_w       – GDCR minimum clear width (m)
  min_d       – GDCR minimum clear depth (m)
  aspect_max  – max allowed width/height ratio
  room_type   – categorical: entry|living|dining|passage|kitchen|bedroom|bathroom|balcony|utility
  exterior    – True if the room needs an exterior wall (ventilation / view)
  zone        – public|semi_private|private
  fsi_exempt  – True for balconies (open-to-sky)
  fixed_w     – forced width override for passages / corridors (m), or None
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

import networkx as nx

logger = logging.getLogger(__name__)

# ─── Master room spec table ────────────────────────────────────────────────────
# Keyed by canonical room-id string.
# GDCR references: §13.1.9 (habitable min areas), §13.1.11 (ventilation)
ROOM_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "entry": {
        "area": 2.5, "min_area": 1.5, "min_w": 1.0, "min_d": 1.0,
        "aspect_max": 3.0, "room_type": "entry",
        "exterior": False, "zone": "public", "fsi_exempt": False, "fixed_w": None,
    },
    "foyer": {
        "area": 3.0, "min_area": 2.0, "min_w": 1.2, "min_d": 1.5,
        "aspect_max": 2.5, "room_type": "entry",
        "exterior": False, "zone": "public", "fsi_exempt": False, "fixed_w": None,
    },
    "living": {
        "area": 15.0, "min_area": 9.5, "min_w": 3.0, "min_d": 3.0,
        "aspect_max": 2.0, "room_type": "living",
        "exterior": True, "zone": "public", "fsi_exempt": False, "fixed_w": None,
    },
    "dining": {
        "area": 8.0, "min_area": 6.0, "min_w": 2.4, "min_d": 2.4,
        "aspect_max": 2.0, "room_type": "dining",
        "exterior": False, "zone": "public", "fsi_exempt": False, "fixed_w": None,
    },
    "passage": {
        "area": 3.5, "min_area": 2.0, "min_w": 1.1, "min_d": 1.5,
        "aspect_max": 6.0, "room_type": "passage",
        "exterior": False, "zone": "semi_private", "fsi_exempt": False, "fixed_w": 1.1,
    },
    "kitchen": {
        "area": 7.5, "min_area": 5.0, "min_w": 1.8, "min_d": 2.5,
        "aspect_max": 2.5, "room_type": "kitchen",
        "exterior": True, "zone": "public", "fsi_exempt": False, "fixed_w": None,
    },
    "bedroom_master": {
        "area": 13.5, "min_area": 9.5, "min_w": 3.0, "min_d": 3.0,
        "aspect_max": 1.8, "room_type": "bedroom",
        "exterior": True, "zone": "private", "fsi_exempt": False, "fixed_w": None,
    },
    "bedroom_2": {
        "area": 10.5, "min_area": 9.5, "min_w": 3.0, "min_d": 3.0,
        "aspect_max": 1.8, "room_type": "bedroom",
        "exterior": True, "zone": "private", "fsi_exempt": False, "fixed_w": None,
    },
    "bedroom_3": {
        "area": 9.0, "min_area": 9.5, "min_w": 3.0, "min_d": 3.0,
        "aspect_max": 1.8, "room_type": "bedroom",
        "exterior": True, "zone": "private", "fsi_exempt": False, "fixed_w": None,
    },
    "bathroom_attached": {
        "area": 4.5, "min_area": 1.8, "min_w": 1.2, "min_d": 1.5,
        "aspect_max": 3.0, "room_type": "bathroom",
        "exterior": False, "zone": "private", "fsi_exempt": False, "fixed_w": None,
    },
    "bathroom_master": {
        "area": 5.0, "min_area": 1.8, "min_w": 1.5, "min_d": 1.8,
        "aspect_max": 3.0, "room_type": "bathroom",
        "exterior": False, "zone": "private", "fsi_exempt": False, "fixed_w": None,
    },
    "bathroom_common": {
        "area": 3.8, "min_area": 1.8, "min_w": 1.2, "min_d": 1.5,
        "aspect_max": 3.0, "room_type": "bathroom",
        "exterior": False, "zone": "semi_private", "fsi_exempt": False, "fixed_w": None,
    },
    "balcony": {
        "area": 4.0, "min_area": 2.0, "min_w": 1.2, "min_d": 1.5,
        "aspect_max": 4.0, "room_type": "balcony",
        "exterior": True, "zone": "public", "fsi_exempt": True, "fixed_w": None,
    },
    "balcony_living": {
        "area": 4.5, "min_area": 2.0, "min_w": 1.2, "min_d": 1.5,
        "aspect_max": 4.0, "room_type": "balcony",
        "exterior": True, "zone": "public", "fsi_exempt": True, "fixed_w": None,
    },
    "balcony_master": {
        "area": 3.5, "min_area": 2.0, "min_w": 1.2, "min_d": 1.5,
        "aspect_max": 4.0, "room_type": "balcony",
        "exterior": True, "zone": "public", "fsi_exempt": True, "fixed_w": None,
    },
    "utility": {
        "area": 2.5, "min_area": 1.5, "min_w": 1.0, "min_d": 1.2,
        "aspect_max": 3.0, "room_type": "utility",
        "exterior": False, "zone": "public", "fsi_exempt": False, "fixed_w": None,
    },
}

# Flat-type-level area overrides so default room sizes fit the unit target
_FLAT_AREA_SCALE: Dict[str, Dict[str, float]] = {
    "1BHK": {
        "living": 13.5, "kitchen": 6.0, "bedroom_master": 11.0,
        "bathroom_attached": 4.0, "balcony": 4.0,
    },
    "2BHK": {
        "living": 16.0, "kitchen": 7.5, "bedroom_master": 12.0,
        "bedroom_2": 10.0, "bathroom_attached": 4.5,
        "bathroom_common": 3.8, "balcony": 4.0, "utility": 2.5,
    },
    "3BHK": {
        "living": 15.0, "dining": 8.0, "kitchen": 7.5,
        "bedroom_master": 13.5, "bedroom_2": 10.5, "bedroom_3": 9.0,
        "bathroom_master": 5.0, "bathroom_common": 3.8,
        "balcony_living": 4.5, "balcony_master": 3.5, "utility": 2.5,
    },
}


def _resolve_spec(room_id: str, flat_type: Optional[str],
                  overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the final spec for a room node.
    Priority: caller overrides > flat-type area scale > global ROOM_DEFAULTS.
    Unknown room ids get a sensible fallback spec.
    """
    # Base
    base = copy.deepcopy(ROOM_DEFAULTS.get(room_id, {
        "area": 6.0, "min_area": 3.0, "min_w": 1.5, "min_d": 1.5,
        "aspect_max": 2.5, "room_type": "room",
        "exterior": False, "zone": "private", "fsi_exempt": False, "fixed_w": None,
    }))
    # Flat-type scale
    if flat_type and flat_type in _FLAT_AREA_SCALE:
        scale = _FLAT_AREA_SCALE[flat_type]
        if room_id in scale:
            base["area"] = scale[room_id]
    # Room-level overrides from topology JSON (e.g. area_sqm field)
    if "area_sqm" in overrides:
        base["area"] = float(overrides.pop("area_sqm"))
    base.update(overrides)
    return base


def _parse_room_list(rooms_raw: Any) -> List[Dict[str, Any]]:
    """
    Accept rooms as:
      - list of strings:  ["entry", "living", ...]
      - list of dicts:    [{"id": "entry", "area_sqm": 2.5}, ...]
    Returns list of dicts always.
    """
    result = []
    for r in rooms_raw:
        if isinstance(r, str):
            result.append({"id": r})
        elif isinstance(r, dict):
            if "id" not in r and "label" in r:
                r = {**r, "id": r["label"].lower().replace(" ", "_")}
            result.append(r)
    return result


def build_graph(
    topology: Dict[str, Any],
    flat_type: Optional[str] = None,
    unit_w: float = 0.0,
    unit_d: float = 0.0,
    room_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> nx.Graph:
    """
    Build an annotated NetworkX graph from a Claude topology dict.

    Parameters
    ----------
    topology      : Claude JSON with rooms + adjacency_graph (or "adjacency")
    flat_type     : "1BHK" | "2BHK" | "3BHK" — selects default area table
    unit_w, unit_d: outer unit dimensions in metres (0 → auto from room areas)
    room_overrides: per-room spec overrides, e.g. {"living": {"area": 18.0}}

    Returns
    -------
    G : nx.Graph
        Nodes carry full spec dicts; edges have weight=1 (will be used by
        graph_layout_solver for force strength).
    """
    room_overrides = room_overrides or {}
    rooms_raw = topology.get("rooms", topology.get("nodes", []))
    rooms = _parse_room_list(rooms_raw)

    adj_raw = topology.get("adjacency_graph", topology.get("adjacency", []))

    G: nx.Graph = nx.Graph()
    G.graph["flat_type"]  = flat_type or topology.get("flat_type", "unknown")
    G.graph["unit_w"]     = unit_w
    G.graph["unit_d"]     = unit_d

    for room in rooms:
        rid  = room["id"]
        extra = {k: v for k, v in room.items() if k != "id"}
        spec  = _resolve_spec(rid, flat_type, {**extra, **room_overrides.get(rid, {})})
        G.add_node(rid, **spec)

    for edge in adj_raw:
        u, v = edge[0], edge[1]
        # Add nodes that appear in adjacency but not in rooms list
        if u not in G:
            G.add_node(u, **_resolve_spec(u, flat_type, room_overrides.get(u, {})))
        if v not in G:
            G.add_node(v, **_resolve_spec(v, flat_type, room_overrides.get(v, {})))
        G.add_edge(u, v, weight=1)

    logger.info(
        "build_graph: flat=%s nodes=%d edges=%d",
        G.graph["flat_type"], G.number_of_nodes(), G.number_of_edges(),
    )
    return G


def graph_summary(G: nx.Graph) -> Dict[str, Any]:
    """Return a concise summary dict for logging / API response."""
    return {
        "flat_type":  G.graph.get("flat_type"),
        "nodes":      list(G.nodes),
        "edges":      list(G.edges),
        "room_types": {n: G.nodes[n].get("room_type") for n in G.nodes},
        "areas":      {n: G.nodes[n].get("area") for n in G.nodes},
    }
