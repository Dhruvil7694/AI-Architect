# Compliance Engine Version Governance

This document defines when to bump the deterministic ComplianceEngine
`engine["version"]` and when to bump the CGDCR `ruleset_version`.

## Engine version (`engine.version`)

Increment the engine version whenever **implementation semantics change** even
if the rule YAML/config remains identical. Examples:

- Changing severity weights (`SEVERITY_WEIGHTS`).
- Modifying aggregation logic (`_aggregate_overall`, `_aggregate_groups`).
- Adding, removing, or changing a `RuleGroupEvaluator`’s rule logic.
- Changing the canonicalization of `ComplianceContext` or `ComplianceResult`
  (e.g. field order, normalization rules).
- Changing error handling semantics (evaluator exception handling).

Adding new rule groups that evaluate **additional rules for the same inputs**
also requires a version bump, because it can change `overall.score` and
`overall.status`.

## Ruleset version (`ruleset_version`)

Increment the ruleset version when the **regulatory content** changes:

- Adding, removing, or modifying a rule in GDCR.yaml or equivalent config.
- Changing thresholds, bands, or trigger heights.
- Changing which development categories (D1–D10) a rule applies to.

Pure content changes in GDCR.yaml do not require an engine version bump, only a
`ruleset_version` bump.

## Field ordering in `ComplianceContext`

The dataclass field order of `ComplianceContext` is part of the canonical
schema used to compute `context_checksum`. Reordering fields, even without
changing their names or values, **must be treated as a schema change** and:

- Requires an engine version bump, and
- May require downstream consumers to be revalidated.

Do not reorder fields in `ComplianceContext` casually; treat it as a
versioned contract.

