# Creating geometry for plots

Plot **geometry** (the polygon boundaries shown in the Plots browser and planner) comes from the **TP ingestion pipeline**. The pipeline reads:

1. **DXF file** – Contains the spatial drawing: polygon boundaries and FP number labels.
2. **Excel or CSV file** – Contains FP numbers and plot areas (e.g. "FP No", "Area (sq.ft)").

It matches labels to polygons, validates area, and writes (or updates) `Plot` records **with** `geom` in the database.

## When plots show "No geometry"

- Plots were created **without** running this pipeline (e.g. Excel-only or manual data), so `geom` is null.
- Fix: run the ingestion with the **DXF** and Excel/CSV for that scheme so geometry is created or updated.

## Run ingestion (create or update geometry)

From the **backend** directory, with your virtualenv activated:

```bash
cd backend
python manage.py ingest_tp <dxf_path> <excel_or_csv_path> --city <CityName> --tp-scheme <TPnn>
```

**Examples:**

- **Create new plots with geometry** (TP14, using repo `tp_data`):
  ```bash
  python manage.py ingest_tp ../tp_data/pal/tp14/TP14\  PLAN\ NO.3.dxf ../tp_data/pal/tp14/TP14_Scheme_English.csv --city Ahmedabad --tp-scheme TP14
  ```

- **Update geometry for existing plots** (e.g. plots already in DB without geometry):
  ```bash
  python manage.py ingest_tp ../tp_data/pal/tp14/TP14\  PLAN\  NO.3.dxf ../tp_data/pal/tp14/TP14_Scheme_English.csv --city Ahmedabad --tp-scheme TP14 --update-existing
  ```

**Options:**

- `--update-existing` – Update `geom` (and area fields) for existing plots with the same city/tp_scheme/fp_number instead of skipping them.
- `--save-invalid` – Save plots that fail area validation (e.g. DXF vs Excel area mismatch).
- `--area-tolerance 0.15` – Allow 15% area difference (default 10%).
- `--dry-run` – Don’t write to the database.

Supported metadata files: **.xlsx**, **.xls**, **.csv** (with columns like "FP No" and "Area" / "Area (sq.ft)").

After a successful run, refresh the **Plots** page in the UI; mini geometry previews should appear where ingestion matched and saved geometry.
