Place the following files in this directory:

  tp14_plan.dxf       — TP14 scheme DXF drawing (from AUDA / local body)
  tp14_scheme.xlsx    — TP14 FP number and area metadata (Excel)

PAL bundle may use other names, for example:
  TP14  PLAN NO.3.dxf
  EDIT  T.P. 14  (FINAL) SCHEME.xls   (Gujarati F-form; decoded by ingest_tp)

The Excel file must contain at minimum:
  - A column for FP number  (e.g. "FP No" or "Plot No")
  - A column for plot area  (e.g. "Area" or "Area (sq.m)")

TP14 PAL (this DXF): include both plot layers — some FPs are drawn only on "new f.p.":
  --polygon-layers F.P. "new f.p." --label-layers FINAL F.P.
  That typically cuts "Excel but no polygon" gaps compared to F.P. alone.
  If FP 104 / 149 / 164 still fail area checks, try --area-tolerance 0.20 (ingest_tp / report).

  Label snap distance: many PAL labels sit farther than default 1.0 DXF units from the
  plot centroid. Use --snap-tolerance 35 on ingest_tp and report_ingestion_gaps so more
  FPs match (e.g. FP 157) without editing the DXF.

  If a few FPs still show "Excel but no polygon match" after that, move those FP TEXT
  entities in CAD so the insertion point lies inside the correct plot outline (or use a
  larger snap only if you accept risk of wrong neighbour matches). Do not rely on blind
  automated DXF reassignment — it can steal polygons from other FPs.

--------------------------------------------------------------------
Beginner: what to edit and why (step by step)
--------------------------------------------------------------------

Goal: each final-plot number (TEXT) must sit *inside* the closed outline of that plot
(the polygon on F.P. or new f.p.). Our importer matches "label point" to "plot polygon";
if the text is in the road gap or wrong parcel, that FP fails.

Before you start: copy TP14  PLAN NO.3.dxf to a new name (e.g. TP14_PLAN_NO3_edit.dxf)
so you keep the original safe.

Typical FPs that may still need a manual move after --snap-tolerance 35 (run report to
see your exact list): 100, 102, 103, 127, 138, 161 (and 157 if you use snap 1 only).

OPTION A — CAD (BricsCAD, AutoCAD, ZWCAD, etc.) — recommended for DXF text
  1. Open the .dxf in the CAD program.
  2. Use the **Layer** palette or -LAYER command: turn **On** layers **F.P.**, **new f.p.**
     and **FINAL F.P.**; turn **Off** heavy hatch/background layers if the screen is
     too busy.
  3. **Zoom** to the area where the PDF map shows that FP (use TP14 PAL.pdf on screen
     or printout to compare).
  4. **Find text**: command **QSELECT** (or Find / Filter): object type = Text, MText,
     layer = FINAL F.P., text string = e.g. 100 102 103 … one at a time.
  5. **Move**: command **MOVE** (or drag). Click the text, base point anywhere, then
     move so the **insertion point** (the small square grip on the text) lies **inside**
     the correct plot outline — not inside the road or neighbour plot.
  6. If you see **duplicate** numbers (e.g. three "102"), delete the extras so only one
     TEXT stays per FP.
  7. **Save** the DXF (same filename you are editing).

OPTION B — QGIS (if you do not have CAD)
  1. Layer -> Add Layer -> Add Vector Layer -> file type "AutoCAD DXF" -> pick the .dxf.
  2. In the dialog, select sublayers: at minimum polygon layers for plots and any
     **point** or **text** layer that corresponds to FINAL F.P. (names may differ).
  3. Open the **attribute table** on the text/point layer; use **Select by expression**
     or column filter to find rows whose text equals 100, 102, …
  4. **Toggle editing** on that layer; activate **Move feature(s)**; drag each
     selected label inside the correct plot polygon (use F.P. / new f.p. outlines).
  5. **Save layer edits**. If export back to DXF looks wrong, repeat the moves in CAD
     instead.

After editing
  1. From backend/: run report_ingestion_gaps with --snap-tolerance 35 (see below).
  2. If "Excel but no polygon match" is empty or shorter, run ingest_tp with the same
     layers and --snap-tolerance 35.

--------------------------------------------------------------------
QGIS short checklist (same as Option B, condensed)
--------------------------------------------------------------------
  1. Vector -> add the .dxf; enable polygon layers F.P. and new f.p. plus FINAL F.P. text.
  2. Style plot polygons; use TP14 PAL.pdf on a second screen to match parcels.
  3. Attribute table -> find each target FP; toggle editing; Move feature inside plot.
  4. Save; re-run report_ingestion_gaps; then ingest_tp with --snap-tolerance 35.

Pre-ingest QA (lists Excel FPs with no polygon, area failures, unmatched labels):
  python manage.py report_ingestion_gaps <dxf> <excel> --polygon-layers F.P. "new f.p." --label-layers "FINAL F.P." --snap-tolerance 35 [--csv gaps.csv]
  (run from backend/)
