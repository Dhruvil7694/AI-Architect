---
name: cgdcr-compliance-engine-design
overview: High-level design for a deterministic, geometry-agnostic CGDCR residential compliance engine on top of existing layout contracts.
todos:
  - id: define-compliance-context-schema
    content: Define flattened numeric/boolean ComplianceContext metrics grouped by plot, building, structure, safety, and environment, with type/source/scope annotations.
    status: completed
  - id: design-metric-extractor-layer
    content: Design read-only ComplianceMetricExtractor layer that derives and normalizes metrics from BuildingLayoutContract, FloorLayoutContract, and plot data into ComplianceContext.
    status: completed
  - id: design-compliance-engine-core
    content: Specify ComplianceEngine entry point, RuleRegistry, rule grouping into evaluator classes, and deterministic evaluation flow from ComplianceContext + RuleSet to ComplianceResult.
    status: completed
  - id: design-rule-config-model
    content: Describe YAML rule configuration schema and its mapping to in-memory rule models, including severity, triggers, and development categories/overlays.
    status: completed
  - id: define-compliance-result-schema
    content: Define JSON-serializable ComplianceResult structure, including per-rule results, overall status, and deterministic compliance score rules.
    status: completed
  - id: document-separation-and-extensibility
    content: Document separation from geometry/detailing layers, non-goals, and mechanisms for future regulation overlays and municipalities.
    status: completed
isProject: false
---

### Objectives

- Define a flattened, numeric/boolean-only `ComplianceContext` schema capturing all metrics needed for CGDCR residential (D1–D10) evaluation.
- Design a read-only `ComplianceMetricExtractor` layer that derives and normalizes metrics from existing contracts/plot data without recomputing geometry or FSI logic.
- Specify a deterministic `ComplianceEngine` with rule registry, group evaluators, and JSON-serializable `ComplianceResult` suitable for municipal audit and future overlays.

### High-level Approach

- Model `ComplianceContext` as a single DTO with clearly named fields grouped conceptually by domain (plot, building, structure, safety, environment) and annotated with type, source, and scope.
- Introduce dedicated metric extractors per domain (plot, building, floor/structure, safety/environment) that aggregate into `ComplianceContext` and normalize units to meters/sqm.
- Parse CGDCR YAML once into a typed `RuleSet` and drive evaluation via a `RuleRegistry` and per-group evaluators, avoiding dynamic eval or geometry access.
- Produce a deterministic `ComplianceResult` with per-rule details, severity classification, and optional compliance score, plus versioning information and input checksums for audit.

### Key Components / Todos

- `define-compliance-context-schema`: Enumerate all required/optional metrics, their types, scopes, and high-level derivations.
- `design-metric-extractor-layer`: Specify extractor classes, inputs/outputs, caching behavior, and metric-derivation mapping.
- `design-compliance-engine-core`: Define engine entry point, `RuleRegistry`, rule grouping, and evaluation lifecycle.
- `design-rule-config-model`: Describe YAML structure → in-memory rule models, including severity, triggers, and development categories.
- `define-compliance-result-schema`: Specify JSON-safe result structure and aggregation rules for statuses/scores.
- `document-separation-and-extensibility`: Capture boundaries with existing phases, overlay mechanism, and explicit non-goals.

## ComplianceResult JSON Contract (Deterministic Core)

### 1. Purpose and Scope

`ComplianceResult` is the **single, canonical, deterministic output** of the `ComplianceEngine`. It is:

- Fully JSON-serializable.
- Stable across platforms for the same inputs and `RuleSet`.
- The only authoritative source for numeric checks, PASS/FAIL outcomes, severities, and compliance scores.

All downstream consumers (APIs, UI, PDFs, LLM reporting) must depend exclusively on this contract, not on internal engine types.

### 2. Top-Level Structure

The top-level `ComplianceResult` object has the following shape:

```json
{
  "schema_version": "1.0.0",
  "engine": {
    "name": "CGDCRComplianceEngine",
    "version": "1.0.0"
  },
  "input_refs": {
    "context_checksum": "sha256-...",
    "ruleset_id": "CGDCR-D-RESIDENTIAL",
    "ruleset_version": "2026.03.01",
    "layout_contract_id": "plot-123-building-A",
    "layout_contract_version": "2026.02.15"
  },
  "overall": { },
  "groups": [ ],
  "rules": [ ],
  "errors": [ ],
  "result_hash": "sha256-...",
  "generated_at": "2026-03-03T12:34:56Z"
}
```

- `**schema_version**`: Semantic version of this JSON contract; changes only when fields or semantics change.
- `**engine**`: Identity and version of the deterministic engine implementation.
- `**input_refs**`: Logical identifiers and checksums that bind the result to specific inputs (context, ruleset, layout contracts).
- `**overall**`: Aggregated, deterministic status and scoring summary.
- `**groups**`: Optional group-level aggregations (e.g., setbacks, FSI, height, fire).
- `**rules**`: One entry per evaluated rule in the `RuleSet`.
- `**errors**`: Any engine-level or evaluation-level errors that prevent or affect evaluation.
- `**result_hash**`: Cryptographic hash of the canonical JSON serialization of the result (excluding `result_hash` itself).
- `**generated_at**`: UTC timestamp of evaluation completion in ISO-8601 format.

`ruleset_id` and `ruleset_version` are part of the canonical JSON and therefore part of the `result_hash`. Re-evaluating the same inputs under a different `ruleset_version` always produces a distinct `ComplianceResult` and a different `result_hash`, even if individual rule outcomes are numerically identical.

### 3. Overall Section

```json
"overall": {
  "status": "FAIL",
  "score": 80.0,
  "severity_aggregates": {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 3,
    "LOW": 5,
    "INFO": 8
  },
  "rule_counts": {
    "total": 120,
    "evaluated": 118,
    "passed": 110,
    "failed": 4,
    "not_applicable": 6,
    "errors": 0
  }
}
```

- `**status**`: One of `PASS`, `FAIL`, `PARTIAL`, `NOT_APPLICABLE`, `ERROR`, derived deterministically from rule results (see scoring rules below).
- `**score**`: Deterministic scalar score in the range 0.0, 100.0.
- `**severity_aggregates**`: Counts of rules per severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`) considering only failed rules.
- `**rule_counts**`: Counts of rules by evaluation outcome.

### 4. Group Section

```json
"groups": [
  {
    "group_id": "setbacks",
    "title": "Setbacks and Margins",
    "status": "FAIL",
    "score": 80.0,
    "severity_aggregates": {
      "CRITICAL": 0,
      "HIGH": 1,
      "MEDIUM": 2,
      "LOW": 1,
      "INFO": 0
    },
    "rule_ids": ["D3-SETBACK-FRONT-01", "D3-SETBACK-SIDE-01"]
  }
]
```

- `**group_id**`: Stable identifier for a logical rule group (e.g., `setbacks`, `fsi`, `height`, `parking`, `fire_safety`).
- `**title**`: Human-readable label for the group.
- `**status**` and `**score**`: Deterministic aggregate for this group using the same rules as `overall`, but applied only to the group’s rules.
- `**severity_aggregates**` and `**rule_ids**`: As above, scoped to the group.

Group-level aggregation applies the same status precedence and scoring policy described for `overall`, but restricted to the rules listed in `rule_ids`. In particular:

- If any rule in the group has `status = ERROR`, then the group `status` is `ERROR` and the group `score` is `null` (JSON `null`).
- If there are failed rules in the group but no `ERROR` rules, the group `status` is derived from those failures using the same precedence rules as `overall`.
- If there are no failed or error rules in the group, but at least one passed rule, the group `status` is `PASS`.
- If all rules in the group are `NOT_APPLICABLE`, the group `status` is `NOT_APPLICABLE`, and the group `score` is typically omitted or set to `null`.

### 5. Rule Section

```json
"rules": [
  {
    "rule_id": "D3-SETBACK-FRONT-01",
    "clause_reference": "CGDCR 3.1.2(a)",
    "title": "Minimum front setback for plotted residential building",
    "category": "SETBACKS",
    "status": "FAIL",
    "severity": "HIGH",
    "scope": {
      "plot_id": "P-123",
      "building_id": "B-A",
      "structure_id": null,
      "floor_id": null
    },
    "required": {
      "kind": "NUMERIC_THRESHOLD",
      "metric": "front_setback_min_m",
      "operator": ">=",
      "value": 4.5,
      "unit": "m"
    },
    "provided": {
      "metric": "front_setback_actual_m",
      "value": 3.8,
      "unit": "m",
      "source": "ComplianceContext.plot.front_setback_actual_m"
    },
    "overlays_applied": [
      {
        "overlay_id": "ROAD_WIDTH_GT_12M",
        "description": "Fronting road width above 12m increases minimum setback"
      }
    ],
    "messages": {
      "machine": "front_setback_actual_m(3.8m) < min_required(4.5m) for road_width>=12m",
      "template_key": "SETBACK_FRONT_MIN_FAIL"
    },
    "tags": ["D3", "SETBACK", "FRONT", "RESIDENTIAL"],
    "error": null
  }
]
```

- `**rule_id**`: Unique identifier for the rule within the `RuleSet`.
- `**clause_reference**`: Reference to the underlying regulatory clause (chapter/section/sub-clause).
- `**title**` and `**category**`: Descriptive metadata.
- `**status**`: `PASS`, `FAIL`, `NOT_APPLICABLE`, or `ERROR`.
- `**severity**`: `INFO`, `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`, assigned deterministically by configuration and rule definition.
- `**scope**`: Identifiers that localize the rule (plot/building/structure/floor).
- `**required` / `provided**`: Required condition and provided value, including metric names and units, sufficient for audit without geometry access.
- `**overlays_applied**`: Any contextual overlays (e.g., special road width conditions) that influenced this rule.
- `**messages**`: Machine-oriented message and template key for consistent UI text.
- `**tags**`: Optional categorization labels.
- `**error**`: Optional error object when evaluation of this rule did not complete normally.

### 6. Errors Section

```json
"errors": [
  {
    "code": "ENGINE_INPUT_INVALID",
    "message": "Missing mandatory plot frontage metric",
    "scope": {
      "plot_id": "P-123"
    }
  }
]
```

Engine-level or evaluation errors that are not tied to a single rule are reported here and may influence `overall.status` (e.g., forcing `ERROR`).

### 7. Canonical Serialization and Result Hash

To ensure that logically identical `ComplianceResult` objects yield identical hashes across platforms, a canonical JSON serialization and hashing strategy is defined:

- **Float normalization**: All numeric fields in `ComplianceResult` must be normalized according to the numeric precision and rounding policy defined below (fixed decimal precision, round half-even) before serialization. This normalization is part of the deterministic engine logic, not delegated to the LLM layer.
- **Canonical JSON**: The canonical JSON representation is defined as the UTF-8 encoding of:

```python
canonical_json = json.dumps(
    compliance_result_without_result_hash_and_generated_at,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
)
```

- **Hash computation**:  
  - Let `canonical_bytes = canonical_json.encode("utf-8")`.  
  - Let `result_hash = SHA256(canonical_bytes)` encoded as a hex string.  
  - This `result_hash` value is then stored in the `result_hash` field and referenced by downstream systems and reports.
- **Hash scope**:
  - The field `generated_at` is excluded from the canonical JSON used for hashing to ensure that re-evaluations at different times with identical inputs produce the same `result_hash`.
  - The `engine.name` and `engine.version` fields are included in the canonical JSON; any change to the engine implementation version therefore produces a new `result_hash`, even if per-rule outcomes are numerically identical. This is intentional for implementation-level traceability.

All report integrity mechanisms (including the LLM-based layer) must use this canonicalization definition when binding narratives to a specific `ComplianceResult`.

### 8. Deterministic Scoring, Status Precedence, and NOT_APPLICABLE Logic

Scoring and status derivation are fully deterministic functions of the per-rule results:

- **Severity weights**: A configuration (versioned with the engine) defines fixed penalty weights, for example:
  - `CRITICAL`: 40
  - `HIGH`: 25
  - `MEDIUM`: 10
  - `LOW`: 5
  - `INFO`: 0
- **Score calculation**:
  - Start from `base_score = 100.0`.
  - For each rule with `status = FAIL`, subtract the severity weight for that rule’s `severity`.
  - Clamp the final score to the range 0.0, 100.0.
- **Status precedence**: Overall status uses the strict precedence `ERROR > FAIL > PARTIAL > PASS > NOT_APPLICABLE`.
- **Overall status aggregation** (illustrative but deterministic policy):
  - If any rule has `status = ERROR`, then `overall.status = ERROR`.
  - Else if any rule has `status = FAIL` with severity `CRITICAL` or `HIGH`, then `overall.status = FAIL`.
  - Else if any rule has `status = FAIL` with severity `MEDIUM` or `LOW`, then `overall.status = PARTIAL`.
  - Else if at least one rule has `status = PASS` and there are no `FAIL` or `ERROR` rules, then `overall.status = PASS`.
  - Else (no `PASS`, and all evaluated or represented rules are `NOT_APPLICABLE`) then `overall.status = NOT_APPLICABLE`.
- **NOT_APPLICABLE handling**:
  - Rules with `status = NOT_APPLICABLE` never contribute to `severity_aggregates` or penalties in the score calculation.
  - The `NOT_APPLICABLE` overall status explicitly represents cases where the rulebook does not apply to the input (for example, 100% of rules are not applicable).
- **Scoring under ERROR**:
  - If `overall.status = ERROR` (because at least one rule has `status = ERROR`), the `overall.score` must be set to `null` (JSON `null`), indicating that no meaningful aggregate score is available under incomplete or failed evaluation.
  - Group scores for any group whose aggregated status is `ERROR` must similarly be `null`.

Any changes to these deterministic aggregation rules must be versioned and documented, as they directly affect compliance scores and statuses and thus regulatory interpretation.

### 9. ComplianceContext Checksum and Numeric Normalization Policy

To ensure that both inputs and outputs are auditable and stable across platforms, `ComplianceContext` must follow a canonicalization and numeric normalization policy that mirrors `ComplianceResult`:

- **Numeric precision**:
  - All numeric metrics in `ComplianceContext` and `ComplianceResult` are normalized to a fixed precision of 4 decimal places.
  - Normalization uses round half-even (banker’s rounding) and is applied as part of the deterministic engine logic.
- **Point of normalization**:
  - Inputs to `ComplianceContext` are normalized to this precision and rounding before any rule comparisons, arithmetic, or aggregations.
  - The same normalized values are then serialized into `ComplianceContext` and `ComplianceResult`, ensuring that what is serialized is exactly what was evaluated.
- **Comparison discipline**:
  - Raw floating-point values must never be compared directly in rule evaluation.
  - All comparisons, thresholds, and aggregations must operate exclusively on the normalized numeric values stored in `ComplianceContext`.
  - Metric extractor components are responsible for performing normalization before exposing metrics to the rule evaluation layer.
- **Unit normalization**:
  - All numeric metrics in `ComplianceContext`, and all `required`/`provided` numeric values in rule definitions, must be expressed in canonical SI units (for example, meters for lengths, square meters for areas).
  - Any conversion from alternative units (such as feet or square feet) must occur before values enter `ComplianceContext`, so that all internal comparisons are made in a single, consistent unit system.
- **ComplianceContext canonical JSON**:

```python
canonical_context_json = json.dumps(
    compliance_context,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
)
canonical_context_bytes = canonical_context_json.encode("utf-8")
context_checksum = SHA256(canonical_context_bytes)
```

- **Context checksum**:
  - The `context_checksum` recorded in `ComplianceResult.input_refs` is the hex encoding of `SHA256(canonical_context_bytes)`.
  - Any change to `ComplianceContext` (including field changes, ordering, or numeric differences after normalization) results in a different `context_checksum`.

This policy guarantees that both context and result are reproducible and that any drift in inputs or evaluation can be detected and audited.

### 10. Deterministic Ordering Requirements

To avoid runtime-dependent variation due to container iteration order or concurrency, all iteration that contributes to `ComplianceResult` must be deterministic:

- **Rule evaluation order**:
  - The `RuleSet` defines an ordered list of rules; the engine must evaluate rules in a deterministic order derived from this list (for example, by rule index or by lexicographic `rule_id`).
  - The `rules` array in `ComplianceResult` must be ordered deterministically (for example, sorted by `rule_id` in ascending order) regardless of any internal registry or collection types used.
- **Group ordering**:
  - The `groups` array in `ComplianceResult` must be ordered deterministically (for example, sorted by `group_id` in ascending order).
- **Map-like structures**:
  - For structures such as `severity_aggregates` and `rule_counts`, the combination of stable field names and `sort_keys=True` in canonical JSON ensures deterministic ordering, but internal construction should also avoid dependence on unordered containers.

Engine implementations must not rely on language-specific hash map or set iteration order for any behavior that affects `ComplianceResult`. All such iteration must be explicitly ordered to guarantee determinism across runtimes and deployments.

## LLM-Based Reporting & Authoring Layer (Non-Deterministic Auxiliary Layer)

### 1. Purpose

The LLM-based layer is an auxiliary, non-deterministic reporting and authoring component that operates strictly on top of the deterministic `ComplianceEngine`.

- **Human-readable explanation only**: Its sole purpose is to generate human-readable narratives, explanations, and draft artifacts derived from existing `ComplianceResult` data and CGDCR source documents.
- **No role in compliance decisions**: It does not participate in compliance decision-making and is never consulted for PASS/FAIL computation, numeric comparisons, or rule triggering.
- **Operates exclusively on structured `ComplianceResult` JSON**: All online usage of the LLM layer consumes a precomputed, JSON-serializable `ComplianceResult` instance as input.
- **No mutation of core engine state**: It cannot alter `ComplianceContext`, cannot re-run or short-circuit rule evaluation, and cannot modify any deterministic engine artifacts.

The deterministic `ComplianceEngine` and its `ComplianceResult` remain the single source of truth for all compliance outcomes.

### 2. Permitted Use Cases

The LLM-based layer may be used only for the following auxiliary, non-deterministic purposes:

A. **Natural language executive summary generation**

- Generate a concise, human-readable executive overview of the overall compliance posture (e.g., high-level pass/fail status, key issues, and affected domains) based solely on the existing `ComplianceResult` JSON.

B. **Clause-by-clause explanation generation**

- Produce natural language explanations for individual rules/clauses, describing:
  - What the clause requires.
  - How the deterministic engine evaluated it.
  - Which metrics or inputs from `ComplianceResult` were relevant.

C. **Risk highlighting and advisory commentary**

- Highlight potential risk areas, patterns of non-compliance, or advisory commentary that helps humans interpret the deterministic results.
- All such commentary is interpretive only and cannot alter rule outcomes or severities.

D. **Conversion of `ComplianceResult` JSON into formatted PDF reports**

- Transform structured `ComplianceResult` data into formatted, human-readable PDF (or similar) reports, including summaries, tables, and narrative sections.
- Any formatting or phrasing differences do not and cannot change the underlying structured `ComplianceResult` content.

E. **Parsing CGDCR regulatory documents into draft YAML rule templates (offline authoring use only)**

- Assist in parsing CGDCR PDF or other regulatory source documents into **draft** YAML rule templates.
- This is strictly an **offline authoring aid**; all generated content is treated as untrusted until manually reviewed and validated by domain experts.

### 3. Strict Prohibitions

The LLM-based layer is explicitly prohibited from performing or influencing any deterministic compliance logic. In particular, it must **NOT**:

- **Perform numeric comparisons**: No numeric threshold checks, range comparisons, or quantitative validations may be delegated to the LLM.
- **Decide PASS/FAIL**: It may not compute, override, or vote on compliance decisions at rule, group, or overall levels.
- **Modify required or provided values**: It cannot change any inputs, derived metrics, or values stored in `ComplianceContext` or `ComplianceResult`.
- **Override severity**: It cannot upgrade, downgrade, or otherwise adjust severity levels determined by the deterministic engine.
- **Trigger rules**: It cannot trigger additional rules, suppress rules, or dynamically inject rule execution.
- **Access geometry engines**: It must not call geometry or layout engines, nor derive geometry-dependent metrics.
- **Access `ComplianceContext` directly**: Its online interaction is restricted to the exported `ComplianceResult` JSON; it has no handle to `ComplianceContext` or internal evaluator state.
- **Inject dynamic rule logic**: It cannot introduce new rule logic, conditional branching, or dynamic interpretations that affect compliance outcomes.

The deterministic `ComplianceEngine` (using `ComplianceContext` + `RuleSet`) is the sole authority for all numeric checks, PASS/FAIL decisions, and severity assignments.

### 4. LLM Report Input Contract

The LLM layer consumes a strictly defined, read-only input structure derived from `ComplianceResult`:

```json
{
  "metadata": { ... },
  "summary": { ... },
  "rules": [
    { ... }
  ]
}
```

- **Structured JSON only**: The LLM receives a pre-serialized JSON document adhering to this contract; free-form or partial internal objects are not passed.
- **No geometry objects**: No raw geometry, layout meshes, or CAD entities are included.
- **No layout contracts**: `BuildingLayoutContract`, `FloorLayoutContract`, or other internal contract objects are not exposed.
- **No database access**: The LLM layer cannot query the database or any external stateful systems.
- **No access to engine internals**: Internal evaluator classes, rule registries, and computation paths are not directly visible.
- **Immutable input**: The LLM must treat the input JSON as immutable; any changes it suggests are treated as commentary only and do not mutate stored `ComplianceResult`.

A separate serializer/adapter is responsible for mapping the full `ComplianceResult` into this reduced reporting contract.

### 5. Output Scope

The LLM layer may emit only **non-authoritative, narrative outputs**. Acceptable outputs include:

- **Executive summary paragraph**: A concise high-level narrative describing overall compliance status and notable issues.
- **Section-level narrative**: Narratives organized by domain (e.g., plot, building, safety) or regulation chapter, summarizing the deterministic findings.
- **Clause explanation paragraphs**: Per-rule or per-clause explanatory paragraphs grounded in the corresponding deterministic rule result.
- **Highlighted compliance concerns**: Callouts or bullet lists of areas that may warrant closer human review.

These outputs are **advisory** and must not replace or modify the structured `ComplianceResult`. The structured JSON output of the deterministic `ComplianceEngine` remains the canonical representation for all compliance decisions and for any downstream machine processing.

### 6. Clause Parsing Workflow (Offline Authoring Mode)

The LLM may be used in a separate, offline authoring workflow to assist with rule definition, isolated from live compliance evaluation:

- **Workflow**: `CGDCR PDF → LLM → Draft Rule YAML → Human Review → RuleSet`.
- **Draft status**: All LLM-generated YAML is treated as a **draft** and is considered untrusted until explicitly reviewed.
- **Mandatory human review**: Domain experts must review, correct, and approve each LLM-generated rule before it is added to the authoritative `RuleSet`.
- **No auto-approval**: LLM-generated rules are **never** auto-approved or auto-deployed into the production `RuleSet`.
- **Deterministic pipeline unchanged**: Once rules are approved and included in the `RuleSet`, they are evaluated by the deterministic `ComplianceEngine` in exactly the same way as manually-authored rules.

This separation ensures that model behavior cannot silently alter the semantics of regulations without explicit human oversight.

To maintain governance over rule evolution, the offline authoring workflow must also enforce:

- **RuleSet versioning**: Any change derived from LLM-assisted drafting (addition, modification, or removal of rules) requires a `ruleset_version` increment according to a defined versioning policy (for example, semantic versioning).
- **Change log entries**: Each accepted change must be captured in a human-written change log entry, including previous rule reference, new rule definition, rationale, and approver identity.
- **Rule diff auditability**: Before/after representations of affected rules (in normalized YAML or JSON model form) must be stored so that the evolution of the `RuleSet` can be reconstructed and audited.

### 7. Version Isolation

To maintain regulatory defensibility and auditability:

- **LLM model changes must not affect compliance outcomes**: Changes in LLM provider, model version, or prompt configuration may change the narrative wording of reports, but must not alter any numeric checks, PASS/FAIL outcomes, or severity levels.
- **Deterministic engine remains stable**: The `ComplianceEngine`, `ComplianceContext`, and `RuleSet` define the full compliance logic; their behavior is independent of the LLM configuration.
- **Audit perspective**: For any given set of inputs and `RuleSet` version, the structured `ComplianceResult` must remain identical regardless of whether the LLM layer is enabled, disabled, or changed.

### 8. Optional Modes

The system supports two clearly separated operating modes:

1. **Deterministic Mode (Compliance Only)**
  - Only the deterministic `ComplianceEngine` is executed.
  - Inputs: `ComplianceContext` + `RuleSet`.
  - Output: Structured `ComplianceResult` JSON.
  - No LLM invocation occurs, and no narrative reports are generated.
2. **Deterministic + LLM Report Mode**
  - The deterministic `ComplianceEngine` executes first and produces a canonical `ComplianceResult`.
  - A reporting adapter derives the restricted reporting JSON contract (`{ metadata, summary, rules }`) from `ComplianceResult`.
  - The LLM-based layer consumes this contract to generate non-authoritative narrative outputs (summaries, explanations, reports).

In both modes, the **compliance decision logic and outputs (`ComplianceResult`) are identical** for the same inputs and `RuleSet`. Enabling or disabling the LLM-based layer affects only the presence of auxiliary natural-language artifacts, not the underlying compliance evaluation or its regulatory consequences.

### 9. Security & Data Scope Statement

To reduce systemic and legal risk, the LLM layer operates under a deliberately narrow security and data-scope model:

- **No external internet access**: The LLM reporting and authoring layer must not have outbound network access to public internet endpoints during report generation or offline clause parsing.
- **No runtime retrieval-augmented generation (RAG)**: The LLM may not perform runtime document retrieval beyond the pre-supplied `ComplianceResult` JSON (for reports) or explicitly provided CGDCR documents (for offline authoring).
- **No dynamic clause fetching**: The LLM cannot dynamically fetch or discover additional regulations or clauses at generation time; all authoritative clauses reside in curated rule sources and `RuleSet` versions.
- **Strictly bounded inputs**: Online reporting runs exclusively on the reporting JSON derived from `ComplianceResult`. Offline clause authoring runs only on explicitly provided CGDCR source documents and does not touch live compliance data.
- **Segregated execution**: The LLM layer is logically separated from the deterministic engine and geometry services; it cannot invoke geometry pipelines, modify layout contracts, or access live databases.

This constrained scope ensures that report generation cannot silently introduce unreviewed external content or dynamically modify the regulatory basis for evaluation.

### 10. Report Integrity Guarantees

The reporting layer must guarantee that human-facing reports remain consistent with the deterministic `ComplianceResult` and cannot misrepresent its contents:

- **Verbatim structured summary section**: Each report must include a **Structured Compliance Summary** that is rendered directly from `ComplianceResult` (or its reporting contract) without LLM involvement. This includes overall status, key counts (e.g., number of failed rules by severity), and high-level metrics as appropriate.
- **Embedded structured result excerpt**: The full or summarized `ComplianceResult` (or a stable subset, such as the `{ metadata, summary, rules }` contract) must be embedded or attached verbatim in machine-readable form within the report package.
- **Authoritative-source statement**: All reports must contain a clear disclaimer such as: **“The structured ComplianceResult is authoritative. All narrative text is explanatory and non-binding.”**
- **Narrative non-overriding rule**: Narrative sections must never override, restate as authoritative, or silently modify any field of `ComplianceResult` (e.g., status, severity, required/provided values).
- **Report/result binding via hash**: Reports must reference the `result_hash` computed from the canonical JSON serialization defined in the `ComplianceResult` contract. This hash is printed in the report and logged so that any narrative can be unambiguously tied back to the exact deterministic result it describes.

These guarantees ensure that a regulator or auditor can always reconstruct and verify the precise deterministic result that the narrative purports to explain.

### 11. Narrative Validation Rules (Hallucination Containment)

To contain hallucinations and prevent the introduction of unverified content, a post-processing validation layer must check all LLM outputs before they are included in a report:

- **No new numeric claims**: The narrative must not introduce numeric values (thresholds, measurements, counts) that are not present in the structured input. Any numeric reference in narrative must be a direct restatement of a value already present in the reporting JSON.
- **No new rules or clauses**: The narrative must not invent new `rule_id`s, clause references, or regulatory sections not present in the `rules` array or associated metadata.
- **No claims about absent clauses**: The narrative may only discuss clauses and rules that exist in the structured input; references to clauses not represented in the reporting contract must cause validation failure.
- **No contradiction of PASS/FAIL or severity**: The narrative may not contradict any deterministic status (e.g., must not state “compliant” when `overall_status = FAIL`, or describe a violation as “minor” when severity is marked as “critical”). Any such contradiction detected by validation causes the narrative to be rejected.
- **No modification of severity language**: While narrative may explain the implications of severity, it must not reclassify or soften the underlying deterministic severity labels (e.g., may not downgrade “critical” to “advisory”).
- **Deterministic validation outcome**: The validation layer operates deterministically over the structured input and raw LLM output.
- **Operational policy on failure**:
  - A bounded number of retries (for example, `max_retries = 2`) is permitted, each with a stricter, more conservative prompt that reduces narrative freedom (for example, removing numeric details).
  - If all retries fail validation, narrative sections must be omitted from the final report. In this case, the report includes only deterministic structured sections and a short system-generated notice that narrative has been suppressed due to validation constraints.
  - Every validation failure and narrative suppression event must be logged with the associated `result_hash`, model identity, and validation error details for later analysis.

Only narrative that passes these checks may be included in reports.

### 12. Traceability and Per-Clause Binding

To support regulator-grade traceability and reduce narrative drift, each clause-level explanation must be explicitly bound to the corresponding structured rule entry:

- **Explicit identifiers**: For each rule explanation, the report must surface at least:
  - `rule_id`
  - `clause_reference` (e.g., CGDCR chapter/section/sub-clause)
  - Deterministic `status` (e.g., PASS/FAIL/NOT_APPLICABLE)
  - `provided_value` (if applicable)
  - `required_value` or constraint description (if applicable)
- **One-to-one mapping**: Clause-level narrative is always associated with a single rule entry from the `rules` array. Explanations spanning multiple rules must list all relevant rule identifiers explicitly.
- **Display pairing**: In the final report, each narrative explanation appears adjacent to, and clearly labeled with, its corresponding structured rule row so that readers can directly correlate text with deterministic data.
- **No unbound narrative**: Narrative text that cannot be associated with a specific rule, clause, or well-defined group of rules must be placed only in clearly marked high-level sections (e.g., overall advisory observations) and must not imply specific rule-level outcomes.

This binding ensures that any narrative statement can be traced back to concrete structured data for verification.

### 13. Audit Trail Requirements

To maintain reproducibility and support regulatory audits, every LLM-assisted report generation must produce an auditable record:

- **ComplianceResult snapshot or hash**: Persist either the full reporting-contract JSON (`{ metadata, summary, rules }`) or a durable reference plus its cryptographic hash.
- **Model identity**: Record the LLM provider, model family, and precise version or deployment identifier used (e.g., `provider/model@version`).
- **Prompt and configuration versioning**: Record the prompt template identifier, configuration parameters (e.g., temperature, max tokens), and any system messages used.
- **Timestamp and caller**: Log the generation timestamp and the initiating user/system context to support reconstruction of the reporting event.
- **Generated output snapshot**: Store the final, post-validation narrative output associated with the above metadata and `ComplianceResult` hash.

These audit records must be retained for at least as long as the underlying compliance decisions may be subject to review, so that any report provided to a regulator can be reproduced or scrutinized ex post.

### 14. Report Structure and Confidence Classification

To clearly distinguish deterministic content from interpretive narrative and advisory commentary, the final report format must follow a structured contract:

- **1. Executive Summary (Narrative, non-authoritative)**  
  - LLM-generated high-level overview, explicitly labeled as explanatory only.
- **2. Deterministic Compliance Summary (Authoritative, structured)**  
  - Table or structured section derived directly from `ComplianceResult` (overall status, key counts by severity, critical failures). No LLM involvement.
- **3. Clause-by-Clause Deterministic Table (Authoritative, structured)**  
  - Per-rule entries including `rule_id`, `clause_reference`, `status`, `provided_value`, `required_value`, and severity, rendered directly from structured data.
- **4. Clause-by-Clause Explanation (Narrative, interpretive)**  
  - LLM-generated text explanations, each bound to entries in the deterministic table as described in Section 12.
- **5. Advisory Observations (Narrative, non-binding, optional)**  
  - Clearly labeled advisory commentary (e.g., design improvement suggestions, risk patterns) that does not affect compliance outcomes.

The report must visually and textually distinguish between:

- **Deterministic results (authoritative)**: Sections 2 and 3.
- **Narrative explanations (interpretive)**: Sections 1 and 4.
- **Advisory commentary (non-binding)**: Section 5.

Deterministic sections must precede narrative sections, and all narrative must explicitly reference that the underlying `ComplianceResult` is the authoritative basis for any regulatory decision.

For downstream consumers, the report envelope must also include an explicit, machine-readable confidence class for each section, for example:

```json
{
  "section_id": "overall_compliance_summary",
  "title": "Deterministic Compliance Summary",
  "confidence_class": "AUTHORITATIVE"
}
```

with allowed values:

- `"AUTHORITATIVE"` for sections rendered directly from `ComplianceResult` without LLM involvement.
- `"INTERPRETIVE"` for deterministic-grounded narrative explanations of existing results.
- `"ADVISORY"` for optional commentary that does not affect or restate compliance outcomes.

This classification prevents downstream systems from misinterpreting interpretive or advisory narrative as having the same standing as deterministic compliance results.