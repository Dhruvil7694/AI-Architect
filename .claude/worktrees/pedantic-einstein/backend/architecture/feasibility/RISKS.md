# Feasibility Layer — Mathematical Risks & Definitions

This document records the three main mathematical assumptions and how they align (or may diverge) with typical architect/client methodology.

---

## Risk 1 — Floor count assumption (FSI BUA estimate)

**What we do:** When there is no `BuildingProposal` (e.g. validate_feasibility_metrics, generate_floorplan), we estimate total BUA for FSI as:

- `num_floors = max(1, int(building_height_m / storey_height_m))`
- `total_bua_sqft = footprint_area_sqft * num_floors`

**Storey height:** We do **not** assume a fixed value. The default is **3.0 m** (see `constants.DEFAULT_STOREY_HEIGHT_M`). Callers can pass `storey_height_m=3.1`, `3.3`, or any client value to `build_feasibility_from_pipeline(..., storey_height_m=...)`.

**Client methodology may differ:**

- 3.0 m, 3.1 m, 3.3 m — different norms by region/project.
- **Podium logic** — commercial podium floors may be counted differently.
- **Stilt exclusion** — stilt height may be excluded from FSI floor count.

If the engine’s storey height is not aligned with the client’s, **FSI and FSI utilization %** in the feasibility report will not match the architect’s figures. For authority submission, use actual BUA (e.g. from `BuildingProposal.total_bua`) or set `storey_height_m` to the client’s convention.

---

## Risk 2 — Plot depth for irregular shapes

**What we do:** Plot depth is defined **only** as the extent of the plot **along the normal to the primary ROAD edge** (first ROAD edge in `edge_margin_audit`). We project all exterior vertices onto that unit normal and take the span. We do **not** use minimum bounding rectangle (MBR) axes or any fallback.

**Implications:**

- **L-shaped, T-shaped, trapezoidal, corner-skewed plots:** Depth is “thickness” perpendicular to the road, not necessarily the same as a manual “front-to-back” measure if the architect uses a different convention (e.g. MBR or longest axis).
- If depth from the engine differs from the architect’s manual calculation, it is likely due to this definition. Validation on L-shaped, trapezoidal, and corner plots is recommended.

**Code:** `plot_metrics._compute_plot_depth_m` — see docstring; no MBR fallback.

---

## Risk 3 — Ground coverage (GC) interpretation

**What we do:**

- **Achieved GC** = `100 * (built_footprint_area_sqft / plot_area_sqft)` when the pipeline has a placed footprint (`footprint_area_sqft > 0` and `plot_area_sqft > 0`).
- Otherwise we fall back to **envelope-based** GC: `envelope_area / plot_area` (from `envelope_result.ground_coverage_pct`).

**Architect interpretation:** GC is often “actual built footprint / plot area”. Our **footprint-based** achieved GC matches that. If we reported only envelope-based GC, the envelope can be larger than the placed slab, so GC would be **overstated**. We therefore prefer built footprint when available and document the fallback.

**Code:** `service.build_feasibility_from_pipeline` sets `achieved_gc_pct` from footprint when placement exists; `regulatory_metrics.build_regulatory_metrics` accepts whatever the caller passes (footprint- or envelope-based).

---

## Summary

| Risk | Definition / behaviour | Mitigation |
|------|------------------------|------------|
| 1 — Floor count | BUA estimate uses configurable `storey_height_m` (default 3.0 m) | Set `storey_height_m` to client value or use `BuildingProposal.total_bua` |
| 2 — Plot depth | Depth = extent along primary ROAD edge normal only; no MBR | Document; validate on L/T/trapezoidal/corner plots |
| 3 — GC | Achieved GC = built footprint / plot when available; else envelope | Footprint-based when placement exists; documented in service and here |
