"""
gdcr_engine
===========

Deterministic, modular GDCR compliance calculation engine for residential
floor-plan feasibility analysis.

Architecture
------------
    rules_loader        -- Load and validate GDCR/NBC YAML configuration.
    plot_analyzer       -- Derive plot parameters (area, frontage, shape class).
    fsi_calculator      -- FSI and maximum permissible BUA calculations.
    setback_calculator  -- Setback / margin calculations (road, side, rear).
    height_calculator   -- Building height limits from road width and FSI.
    compliance_engine   -- Full GDCR compliance evaluation pipeline.
    validation_engine   -- Validation with deterministic debug tracing.

Unit contract (inherits from common.units)
------------------------------------------
    - All internal calculations in SI units (sq.m, metres).
    - Plot areas from DB are in sq.ft; convert via common.units.sqft_to_sqm()
      before entering this engine.
    - FSI is dimensionless; consistent when both BUA and plot_area are in the
      same unit (the ratio is unit-invariant).
    - GDCR_DEBUG trace output labels every value with its unit.

Design principles
-----------------
    1. Deterministic: same inputs always yield same outputs.
    2. Regulatory accuracy: formulas match GDCR.yaml exactly.
    3. Modularity: each calculator is independently importable.
    4. Extensibility: GDCR rules loaded dynamically; no hardcoded constants.
    5. Testability: pure functions; no Django ORM dependency.
"""
