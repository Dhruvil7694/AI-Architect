# Phase 2.3 — TP14 Full Batch Resolution Analysis

**Run:** Full TP14 batch at 10 m, 16.5 m, 25 m (171 plots, road_width=12 m).  
**Output:** `tp14_phase2_resolution.csv`

---

## Results Summary

| Height (m) | Total zones | % STANDARD | % COMPACT | % STUDIO | % UNRESOLVED | Avg depth (unresolved) | Avg length (width fail) |
|------------|-------------|------------|-----------|----------|--------------|------------------------|--------------------------|
| 10.0       | 149         | 75.2       | 14.1      | 6.7      | 4.0          | 3.78                    | n/a                      |
| 16.5       | 119         | 64.7       | 10.1      | 16.8     | 8.4          | 3.76                    | n/a                      |
| 25.0       | 104         | 59.6       | 9.6       | 25.0     | 5.8          | 3.86                    | n/a                      |

*Total zones* = number of unit zones that got a valid skeleton at that height (envelope + placement + skeleton all succeeded). Higher height → fewer buildable zones (149 → 119 → 104) because of setbacks and envelope constraints.

---

## Validation Against Your Criteria

| Criterion | Threshold | Result |
|-----------|------------|--------|
| **UNRESOLVED on buildable plots** | &lt; 15% | **Pass.** 4.0%, 8.4%, 5.8% — no template problem indicated. |
| **STUDIO share** | &lt; 40% (depth not too aggressive) | **Pass.** Max 25.0% at 25 m. |
| **COMPACT usage** | Not rarely used | **Pass.** 9.6–14.1% — fallback is used; STANDARD is not over‑permissive. |

---

## Interpretation

1. **Market baseline (STANDARD)**  
   - 75% at 10 m, 65% at 16.5 m, 60% at 25 m.  
   - Baseline viability is strong; share drops with height as bands get tighter.

2. **Tight band / depth stress (COMPACT, STUDIO)**  
   - COMPACT 10–14%; STUDIO 7–25%.  
   - STUDIO increases with height (6.7% → 16.8% → 25%), consistent with deeper envelopes and more depth‑constrained bands.

3. **Fatal geometry (UNRESOLVED)**  
   - All below 15%.  
   - **Avg band_depth_m (unresolved)** 3.76–3.86 m, below STUDIO’s required depth (4.3 m), so failure is expected and points to zone size, not a bug.

4. **Width failures**  
   - **Avg band_length_m (width fail) = n/a** at all heights.  
   - No `width_budget_fail` among unresolved cases; failures are depth/zone_too_small. Width stress is not the bottleneck.

---

## Conclusion

- Resolution distribution is **within acceptable bounds** (UNRESOLVED &lt; 15%, STUDIO &lt; 40%, COMPACT in use).
- Unresolved zones are **explainable** by depth (&lt; STUDIO min).
- **Phase 2 is validated** for freeze from a resolution‑distribution perspective.

Next step: freeze Phase 2 and proceed to repetition (Phase 3) when ready.

---

## Sanity check (pre-freeze)

**Command:** `python manage.py phase2_sanity_check --height 16.5 --out-dir ./phase2_sanity`

**Zones rendered:** One STANDARD (FP 105 zone[0]), one COMPACT (FP 104 zone[0]), one STUDIO (FP 110 zone[0]).

**Programmatic checks (all PASS):**
- LIVING touches frontage edge (entry side)
- TOILET has edge on wet wall line (core side)
- Entry door on frontage edge

**Plots:** `phase2_sanity/phase2_sanity_standard.png`, `phase2_sanity_compact.png`, `phase2_sanity_studio.png`  
- Cyan = frontage (entry), magenta dashed = wet wall (core), red = entry door.  
- Visually confirm: living at frontage, wet wall at core, door at corridor/frontage, no inverted layouts.  
- If correct → lock Phase 2.
