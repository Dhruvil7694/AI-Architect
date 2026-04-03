# Phase 0.5-T2 Validation Report (Template)

Date:
Profile ID: `tp14_fidelity_v1`
Prepared by:
Gate: `G0.5-B`

## 1. Run Metadata

- Input benchmark set:
- Run command/config reference:
- Raw output CSV:
- Summary markdown:
- Timestamp:

## 2. Completeness Checks

- Expected rows: `24`
- Actual rows:
- Unique `fp_number` count:
- Missing `fp_number` list:
- Duplicate `fp_number` list:
- Result: `PASS/FAIL`

## 3. Fidelity Metadata Checks

- `fidelity_profile_id` complete (`24/24`):
- `road_width_source` complete (`24/24`):
- `road_edge_source` complete (`24/24`):
- `compliance_pass` complete (`24/24`):
- Rows with `fidelity_flag`:
- Result: `PASS/FAIL`

## 4. Schema Integrity Checks

- Core KPI columns preserved: `PASS/FAIL`
- Added fidelity columns present: `PASS/FAIL`
- Numeric fields parseable: `PASS/FAIL`

## 5. Determinism Checks

- Ordered by `fp_number`: `PASS/FAIL`
- Reproducibility note captured: `YES/NO`

## 6. KPI Snapshot

- Envelope valid rate:
- Placement valid rate:
- Compliance pass rate (`COMPLIANT` normalized):
- Road-edge source distribution:
- Road-width source distribution:

## 7. Blockers

- Blocker 1:
- Blocker 2:

## 8. Gate Decision

- `G0.5-B = PASS/FAIL`
- Decision rationale:
