"""
excel_reader.py
---------------
Reads the TP scheme Excel metadata file and returns a mapping of:
    fp_number (str) → area (float, same unit as DXF polygon area)

Supports two formats:

1. SUDA / AUDA old Gujarati font-encoded format (pre-Unicode)
   ── Detected automatically when column headers are not readable ASCII.
   ── Structure (TP14 PAL confirmed):
       - Rows 0-8: Gujarati title / header rows (skipped)
       - Column 9:  Final Plot (FP) number in Gujarati encoding
       - Column 10: FP area in Gujarati encoding (sq.ft, same unit as DXF)
   ── Numbers decoded via guja_decoder.py

2. Standard English Excel (future TP files with clean headers)
   ── Column matching via known name variants (case-insensitive).
   ── FP column : "FP No", "FP Number", "Plot No", etc.
   ── Area column: "Area", "Plot Area", "Area (sq.m)", etc.

Area units: TP14 PAL stores areas in sq. ft. The DXF coordinate system also
produces polygon areas in sq. ft. → No conversion is applied here; both
sides of the area comparison use the same unit.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

from tp_ingestion.services.guja_decoder import decode_area, decode_fp_number

logger = logging.getLogger(__name__)

# ── Column name variants for the standard English format ────────────────────
_FP_COLUMN_VARIANTS = [
    "fp no", "fp number", "fp_no", "fp_number",
    "plot no", "plot_no", "fpno", "final plot no",
]
_AREA_COLUMN_VARIANTS = [
    "area", "plot area", "area (sq.m)", "area(sq.m)",
    "area_sqm", "plot_area", "area (sq.ft)", "fp area",
]

# Column indices for the SUDA/AUDA Gujarati-encoded format
_GUJA_SKIP_ROWS = 9   # rows 0-8 are title/header in Gujarati
_GUJA_FP_COL = 9      # Final Plot Number (0-indexed)
_GUJA_AREA_COL = 10   # FP Area in sq.ft (0-indexed)


def read_excel(excel_path: str | Path) -> Dict[str, float]:
    """
    Parse the TP scheme Excel file and return {fp_number: area}.

    Auto-detects Gujarati-encoded vs standard English format.

    Parameters
    ----------
    excel_path : path to the .xlsx / .xls file

    Returns
    -------
    dict mapping FP number strings to their stated area (float)
    """
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    logger.info("Reading Excel: %s", excel_path)

    # Peek at the raw header row to detect encoding
    raw_header = pd.read_excel(excel_path, dtype=str, nrows=1)
    first_col = str(raw_header.columns[0])

    if _is_gujarati_encoded(first_col):
        logger.info("Detected Gujarati font-encoded format (SUDA/AUDA).")
        all_areas = _read_gujarati_format_all_areas(excel_path)
        result = {fp: areas[0] for fp, areas in all_areas.items()}
    else:
        logger.info("Detected standard English column format.")
        result = _read_standard_format(excel_path)

    logger.info("Excel read complete: %d FP records found.", len(result))
    return result


def read_excel_all_areas(excel_path: str | Path) -> Dict[str, List[float]]:
    """
    Parse the TP scheme Excel or CSV and return {fp_number: [area1, area2, ...]}.
    Use when the same FP appears multiple rows (e.g. different OP contributors);
    ingestion can pick the area closest to the polygon geometry.
    """
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    if excel_path.suffix.lower() == ".csv":
        logger.info("Reading CSV: %s", excel_path)
        return _read_csv_all_areas(excel_path)

    raw_header = pd.read_excel(excel_path, dtype=str, nrows=1)
    first_col = str(raw_header.columns[0])

    if _is_gujarati_encoded(first_col):
        return _read_gujarati_format_all_areas(excel_path)
    # Standard format: single area per FP
    single = read_excel(excel_path)
    return {fp: [a] for fp, a in single.items()}


# ── Gujarati format reader ───────────────────────────────────────────────────

def _is_gujarati_encoded(header_text: str) -> bool:
    """
    Heuristic: if the header contains common Gujarati font encoding artifacts
    (non-printable or unexpected ASCII sequences), treat it as Gujarati-encoded.
    ASCII-only headers that look like plain English are considered standard.
    """
    ascii_readable = all(32 <= ord(c) <= 126 for c in header_text if c != '\n')
    has_latin_words = any(w in header_text.lower() for w in ["fp", "plot", "area", "no"])
    return ascii_readable and not has_latin_words


def _read_gujarati_format_all_areas(excel_path: Path) -> Dict[str, List[float]]:
    """
    Read Gujarati TP scheme Excel; return {fp_number: [area1, area2, ...]}.
    Preserves all rows so ingestion can choose area closest to geometry when duplicates exist.
    """
    df = pd.read_excel(
        excel_path,
        header=None,
        dtype=str,
        skiprows=_GUJA_SKIP_ROWS,
    )

    if df.shape[1] <= _GUJA_AREA_COL:
        raise ValueError(
            f"Excel file has only {df.shape[1]} columns; "
            f"expected at least {_GUJA_AREA_COL + 1} for Gujarati format."
        )

    fp_series = df.iloc[:, _GUJA_FP_COL]
    area_series = df.iloc[:, _GUJA_AREA_COL]

    result: Dict[str, List[float]] = {}
    for fp_raw, area_raw in zip(fp_series, area_series):
        fp_num = decode_fp_number(str(fp_raw) if pd.notna(fp_raw) else "")
        area = decode_area(str(area_raw) if pd.notna(area_raw) else "")

        if fp_num is None or area is None or area <= 0:
            continue

        if fp_num not in result:
            result[fp_num] = []
        result[fp_num].append(area)

    return result


# ── CSV (standard English columns) ──────────────────────────────────────────

def _read_csv_all_areas(csv_path: Path) -> Dict[str, List[float]]:
    """
    Read a CSV with FP and Area columns; return {fp_number: [area1, area2, ...]}.
    """
    df = pd.read_csv(csv_path, dtype=str)
    col_map = {str(col).strip().lower(): col for col in df.columns}
    fp_col = _find_column(col_map, _FP_COLUMN_VARIANTS, csv_path)
    area_col = _find_column(col_map, _AREA_COLUMN_VARIANTS, csv_path)
    df = df[[fp_col, area_col]].copy()
    df.columns = ["fp_number", "area"]
    df.dropna(subset=["fp_number", "area"], inplace=True)
    df["fp_number"] = df["fp_number"].astype(str).str.strip()
    df["area"] = pd.to_numeric(df["area"], errors="coerce")
    df.dropna(subset=["area"], inplace=True)
    result: Dict[str, List[float]] = {}
    for fp_num, area in zip(df["fp_number"], df["area"]):
        if fp_num not in result:
            result[fp_num] = []
        result[fp_num].append(float(area))
    return result


# ── Standard English format reader ──────────────────────────────────────────

def _read_standard_format(excel_path: Path) -> Dict[str, float]:
    """
    Read an Excel file with recognisable English column headers.
    """
    df = pd.read_excel(excel_path, dtype=str)
    col_map = {col.strip().lower(): col for col in df.columns}

    fp_col = _find_column(col_map, _FP_COLUMN_VARIANTS, excel_path)
    area_col = _find_column(col_map, _AREA_COLUMN_VARIANTS, excel_path)

    df = df[[fp_col, area_col]].copy()
    df.columns = ["fp_number", "area"]
    df.dropna(subset=["fp_number", "area"], inplace=True)
    df["fp_number"] = df["fp_number"].str.strip()
    df["area"] = pd.to_numeric(df["area"], errors="coerce")
    df.dropna(subset=["area"], inplace=True)

    return dict(zip(df["fp_number"], df["area"]))


def _find_column(col_map: dict, variants: list[str], path: Path) -> str:
    for variant in variants:
        if variant in col_map:
            return col_map[variant]
    raise ValueError(
        f"Could not find a recognised column in '{path.name}'.\n"
        f"  Looked for: {variants}\n"
        f"  Found columns: {list(col_map.keys())}\n"
        "Please rename the column to match one of the expected names."
    )
