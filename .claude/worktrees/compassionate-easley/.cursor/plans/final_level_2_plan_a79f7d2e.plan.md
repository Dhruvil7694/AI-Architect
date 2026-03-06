---
name: Final Level 2 Plan
overview: Consolidate the two Level 2 residential layout documents into a single final plan file so there is one source of truth and no confusion between the roadmap and the revalidation report.
todos: []
isProject: false
---

# Final Phase 2 (Level 2) Plan — Consolidate Two Files Into One

## Problem

Two files currently cover Level 2 residential layout:

- [level2-residential-layout-engine_866bbf85.plan.md](.cursor/plans/level2-residential-layout-engine_866bbf85.plan.md) — main roadmap (architecture, Canonical Geometry Contract, Phases 1–6 hardened, UnitLayoutContract, edge cases, forbidden list, implementation order).
- [level2-residential-layout-engine_REVALIDATION.md](.cursor/plans/level2-residential-layout-engine_REVALIDATION.md) — revalidation report (design gaps, corrections, refactored phase summaries, risk matrix, readiness score).

The main plan already says “see REVALIDATION” and REVALIDATION says “use main plan as source of truth.” That split will confuse you later when you need a single reference.

## Approach

Create **one** final plan document that is the single source of truth. Keep the two existing files only as redirects so nothing is lost.

---

## Step 1 — Create the final plan file

**New file:** [.cursor/plans/level2-residential-layout-engine_FINAL.plan.md](.cursor/plans/level2-residential-layout-engine_FINAL.plan.md)

**Contents (in order):**

1. **Front matter**
  Same YAML as the main plan (name, overview, todos, isProject). Optionally set `name` to `level2-residential-layout-engine-FINAL` for clarity.
2. **Single-source-of-truth notice**
  One short paragraph: this document is the only implementation reference for Level 2; it merges the roadmap and revalidation into one plan.
3. **Full roadmap content**
  Copy the entire body of [level2-residential-layout-engine_866bbf85.plan.md](.cursor/plans/level2-residential-layout-engine_866bbf85.plan.md) from “# Level 2 Residential Layout Engine Roadmap” through “Implementation Order” and the “Hardened architecture (summary)” table. Omit the line that says “See … REVALIDATION … for full architectural revalidation” (no more cross-reference to the other file).
4. **Design rationale (short)**
  One new section **“Design rationale (gaps addressed)”** with a compact bullet list of what was wrong and how it was fixed (from REVALIDATION Sections A and B), for example:
  - Geometry: formal UnitLocalFrame and single `derive_unit_local_frame`; no placement_label in composer.
  - Module width: canonical from config only; no circular dependency with composition.
  - Wet wall: WetWallStrategy per pattern/band; wet_wall_line and mirroring rules.
  - Connectivity: mandatory post-slice check; explicit exceptions and fallback state machine.
  - Contract: UnitLayoutContract only for presentation; repetition invariants and edge-case rules.
   Keep this to about one page so the rest stays implementation-focused.
5. **Risk matrix (optional)**
  Add the risk matrix table from REVALIDATION Section D (risk | likelihood | impact | mitigation) so it lives in one place.
6. **No other REVALIDATION content**
  Do not copy the long Sections A/B/C verbatim; the main plan already contains the corrected phase text. The final file should not duplicate that.

---

## Step 2 — Supersede the two original files

Add a single notice at the **very top** of each file (after any YAML front matter in the main plan):

**In [level2-residential-layout-engine_866bbf85.plan.md](.cursor/plans/level2-residential-layout-engine_866bbf85.plan.md):**  
After the closing `---` of the YAML block, insert:

```markdown
**Superseded by [level2-residential-layout-engine_FINAL.plan.md](level2-residential-layout-engine_FINAL.plan.md). Use that file as the single source of truth for implementation.**
```

**In [level2-residential-layout-engine_REVALIDATION.md](.cursor/plans/level2-residential-layout-engine_REVALIDATION.md):**  
At the very top (before “# Level 2 Residential…”), insert:

```markdown
**Superseded by [level2-residential-layout-engine_FINAL.plan.md](level2-residential-layout-engine_FINAL.plan.md). Use that file as the single source of truth. This file is kept for historical rationale only.**
```

Do **not** delete or move the two original files; they remain as redirects and history.

---

## Result

- **One file to use:** `level2-residential-layout-engine_FINAL.plan.md` — full implementation-ready plan (geometry contract, Phases 1–6, UnitLayoutContract, state machine, repetition, invariants, edge cases, forbidden list, implementation order, short rationale, risk matrix).
- **No ambiguity:** Opening either old file immediately directs you to the final plan.
- **No information loss:** Original roadmap and revalidation stay in the repo; their content is merged or summarized into the final plan.

---

## File summary


| Action | File                                                                                                                  |
| ------ | --------------------------------------------------------------------------------------------------------------------- |
| Create | `.cursor/plans/level2-residential-layout-engine_FINAL.plan.md` (consolidated content + short rationale + risk matrix) |
| Edit   | `.cursor/plans/level2-residential-layout-engine_866bbf85.plan.md` (add supersede notice at top)                       |
| Edit   | `.cursor/plans/level2-residential-layout-engine_REVALIDATION.md` (add supersede notice at top)                        |


