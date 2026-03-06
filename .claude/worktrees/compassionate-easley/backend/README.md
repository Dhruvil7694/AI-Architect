# Architecture AI — TP Ingestion Backend

## Milestone 1 — TP/FP Spatial Ingestion Pipeline

This Django backend reads Town Planning (TP) scheme DXF drawings and their
corresponding Excel metadata files, matches Final Plot (FP) numbers to
polygon geometries spatially, validates area consistency, and stores clean
plot records in a PostGIS database.

---

## Scope (this milestone only)

| In scope | Out of scope |
|---|---|
| DXF file reading | REST APIs |
| Excel metadata reading | Frontend |
| Plot polygon extraction | GDCR / NBC logic |
| FP number ↔ polygon spatial matching | Layout generation |
| Area validation | AI / optimisation |
| Django ORM storage (PostGIS) | |

---

## Project Structure

```
backend/
├── manage.py
├── requirements.txt
├── backend/                      ← Django project package
│   ├── settings.py
│   ├── urls.py
│   └── __init__.py
└── tp_ingestion/                 ← Django app
    ├── models.py                 ← Plot model
    ├── services/
    │   ├── dxf_reader.py         ← ezdxf → Shapely Polygons + labels
    │   ├── excel_reader.py       ← pandas → {fp_number: area}
    │   ├── geometry_matcher.py   ← STRtree spatial matching
    │   ├── area_validator.py     ← relative-error validation
    │   └── ingestion_service.py  ← pipeline orchestrator
    └── management/commands/
        ├── inspect_dxf.py        ← diagnostic DXF inspector
        └── ingest_tp.py          ← full ingestion command
```

---

## Prerequisites

- Python 3.10+
- PostgreSQL 14+ with PostGIS extension
- GDAL / GEOS system libraries (required by GeoDjango)

### PostGIS setup (one-time)

```sql
CREATE DATABASE tp_ingestion_db;
\c tp_ingestion_db
CREATE EXTENSION postgis;
```

---

## Installation

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
```

---

## Database configuration

Edit `backend/settings.py` and set your PostGIS credentials:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": "tp_ingestion_db",
        "USER": "postgres",
        "PASSWORD": "your_password",
        "HOST": "localhost",
        "PORT": "5432",
    }
}
```

---

## Running migrations

```bash
python manage.py makemigrations tp_ingestion
python manage.py migrate
```

---

## Usage

### 1. Inspect a DXF file (no DB writes)

```bash
python manage.py inspect_dxf ../../tp_data/pal/tp14/tp14_plan.dxf
```

Output includes:
- Layer names
- Entity type counts (LWPOLYLINE, TEXT, MTEXT, …)
- Total closed polylines (candidate plot polygons)
- Sample text labels

### 2. Run full ingestion

```bash
python manage.py ingest_tp \
    ../../tp_data/pal/tp14/tp14_plan.dxf \
    ../../tp_data/pal/tp14/tp14_scheme.xlsx \
    --city Ahmedabad \
    --tp-scheme TP14
```

Optional flags:

| Flag | Default | Description |
|---|---|---|
| `--area-tolerance` | `0.05` | Max relative area error (5%) |
| `--snap-tolerance` | `1.0` | Label–polygon snap distance in DXF units |
| `--save-invalid` | off | Save area-invalid records (flagged) |
| `--dry-run` | off | Parse + validate without DB writes |

### 3. Dry run (safe for testing)

```bash
python manage.py ingest_tp \
    ../../tp_data/pal/tp14/tp14_plan.dxf \
    ../../tp_data/pal/tp14/tp14_scheme.xlsx \
    --city Ahmedabad \
    --tp-scheme TP14 \
    --dry-run
```

---

## Data files

Place TP scheme files under `tp_data/` following this convention:

```
tp_data/
└── <city_code>/
    └── <tp_scheme>/
        ├── <tp_scheme>_plan.dxf
        └── <tp_scheme>_scheme.xlsx
```

Example: `tp_data/pal/tp14/tp14_plan.dxf`

---

## Excel column names

The Excel file must contain columns matching (case-insensitive):

| Column | Accepted names |
|---|---|
| FP number | `FP No`, `FP Number`, `Plot No` |
| Area | `Area`, `Plot Area`, `Area (sq.m)` |

---

## Plot model fields

| Field | Type | Description |
|---|---|---|
| `city` | CharField | City name |
| `tp_scheme` | CharField | TP scheme ID |
| `fp_number` | CharField | Final Plot number |
| `area_excel` | FloatField | Area from Excel (sq m) |
| `area_geometry` | FloatField | Area computed from polygon |
| `geom` | PolygonField | Plot boundary (SRID=0) |
| `validation_status` | BooleanField | True = area within tolerance |
