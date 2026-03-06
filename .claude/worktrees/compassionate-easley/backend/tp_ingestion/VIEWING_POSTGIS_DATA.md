# Viewing Plot Polygons in PostGIS

Your Django app uses **PostGIS** with database `architecture_ai`. Plot geometries are in the **`tp_ingestion_plot`** table, column **`geom`** (type: geometry, SRID 0 = local/DXF units).

## 1. Connection details (from `backend/settings.py`)

| Setting  | Value          |
|----------|----------------|
| Host     | localhost      |
| Port     | 5432           |
| Database | architecture_ai |
| User     | postgres       |
| Engine   | PostGIS        |

Use the same password you have in `settings.py` (or env) when connecting with the tools below.

---

## 2. Option A — QGIS (see polygons on a map)

1. Open **QGIS**.
2. **Layer → Add Layer → Add PostGIS Layer** (or DB Manager → PostGIS).
3. **New** connection:
   - Name: e.g. `Architecture AI`
   - Host: `localhost`, Port: `5432`
   - Database: `architecture_ai`
   - Username: `postgres`, Password: (your password)
4. **Connect**, then select:
   - **Schema:** `public`
   - **Table:** `tp_ingestion_plot`
5. **Add**. The plot polygons will appear. You can style by `tp_scheme` or `fp_number`, and open attribute table to see `road_width_m`, `road_edges`, area, etc.

**Note:** Geometries are in SRID 0 (local DXF coordinates). In QGIS they may show as “Unknown CRS”; that’s expected. To overlay with real-world data you’d need to assign/transform CRS later.

---

## 3. Option B — pgAdmin or DBeaver

- **pgAdmin**
  1. Add server (host, port, db, user, password).
  2. **Databases → architecture_ai → Schemas → public → Tables → tp_ingestion_plot**.
  3. Right-click table → **View/Edit Data → All Rows** (or use Query Tool).
  4. For **geom**, you often see WKT or hex; some versions have a “View geometry” / map preview.

- **DBeaver**
  1. New connection → PostgreSQL; fill host, port, database, user, password.
  2. Open **tp_ingestion_plot**.
  3. DBeaver can show geometry in a simple map or as WKT depending on version and extensions.

**Useful SQL (run in Query Tool / SQL editor):**

```sql
-- List plots with WKT (first 5)
SELECT id, tp_scheme, fp_number, area_geometry, road_width_m,
       ST_AsText(geom) AS geom_wkt
FROM tp_ingestion_plot
LIMIT 5;

-- Count by TP
SELECT tp_scheme, COUNT(*) FROM tp_ingestion_plot GROUP BY tp_scheme;

-- Bounding box of all plots
SELECT ST_Extent(geom) FROM tp_ingestion_plot;
```

---

## 4. Option C — Export to GeoJSON (open in QGIS or geojson.io)

From the project **backend** folder run:

```bash
# All plots
python manage.py export_plots_geojson --output outputs/plots.geojson

# One TP scheme
python manage.py export_plots_geojson --tp 14 --output outputs/tp14_plots.geojson

# Single plot (TP14 FP126)
python manage.py export_plots_geojson --tp 14 --fp 126 --output outputs/fp126.geojson
```

Then:

- **QGIS:** Layer → Add Layer → Add Vector Layer → choose the `.geojson` file.
- **Web:** Open [geojson.io](https://geojson.io) and drag the file (or paste GeoJSON).

---

## 5. Table summary

| Column           | Type      | Description                    |
|------------------|-----------|--------------------------------|
| id               | bigint    | Primary key                    |
| city             | varchar   | City name                      |
| tp_scheme        | varchar   | e.g. TP14                      |
| fp_number        | varchar   | e.g. 126                       |
| area_excel       | float     | Area from Excel (sq.ft)        |
| area_geometry    | float     | Area from polygon (sq.ft)      |
| geom             | geometry  | **Polygon (SRID 0)**           |
| validation_status| boolean   | Area match OK                  |
| road_width_m     | float     | Road width (m) when set        |
| road_edges       | varchar   | Road edge indices when set     |
| created_at       | timestamp |                                |

Geometry is stored in **DXF/local units** (same as the TP DXF). No real-world CRS is set in the DB.

---

## 6. Foundation data: verify first, then set road data

If **Excel is the source of truth**, verify that stored plot data matches it before running envelope/floorplan engines. Wrong plot areas or wrong road edges will propagate through the pipeline.

### Step 1 — Verify (Excel vs geometry)

From the **backend** folder:

```bash
# Report area validation and road fields for all plots
python manage.py verify_plot_data

# One TP scheme and export full CSV for review
python manage.py verify_plot_data --tp-scheme TP14 --export outputs/tp14_verification.csv
```

Check that **Area OK** matches expectations and fix ingestion or source data if many plots show **Area FAIL**.

### Step 2 — Set road data for all plots

- **From plan/Excel (recommended when you have correct values):**  
  Prepare a CSV with columns `tp_scheme`, `fp_number`, `road_width_m`, `road_edges` (e.g. from the plan) and run:

  ```bash
  python manage.py setup_road_data --from-csv path/to/road_data.csv
  ```

- **Heuristic (baseline when no CSV yet):**  
  Fill missing `road_edges` (longest edge) and `road_width_m` (default) for plots that have none:

  ```bash
  python manage.py setup_road_data --heuristic --tp-scheme TP14 --default-road-width 15
  ```

Use `--dry-run` with either mode to see what would be updated without saving.
