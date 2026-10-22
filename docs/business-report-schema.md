# Decision-ready reports (v2)

New scopes set `report_schema_version: 2` and `business_context` with text `audience`,
`decision`, and string lists `available_levers`, `constraints`, `success_measures`, `unknowns`.
Use explicit unknowns; do not manufacture business context. Legacy scopes default to v1.

New insights drafts set `schema_version: 2`. All existing insight fields remain, plus:

- `decision_requested`: the concrete decision requested, labeled as a proposal where applicable.
- `decision_uncertainties`: string list of material unknowns that can change that decision.
- `recommendations`: ordered by priority; if empty, provide `no_recommendations_reason`.
- `business_review`: `decision_clarity`, `actionability`, `evidence_alignment`, `uncertainty`,
  `communication`; each is `{status: pass|revise|not_applicable, reason: "..."}`. Revise blocks saving.

Each insight retains `statement` as its full explanation, and adds:

- `brief_summary`: concise observed finding, with audience-readable units and denominators.
- `business_implication`: why this matters; distinguish inference from observation.
- `decision_caveat`: visible qualification that matters to the decision (or explicitly none).
- `key_evidence`: selected `{result, finding}` objects, a subset of `evidence`.
- `charts`: optional `[{result, index: 0, caption: "What this chart proves"}]`, zero-based index
  in that result's charts list. Only registered PNG files inside run/charts are accepted.

Each recommendation retains `action`, `rationale`, `evidence`, `evidence_type`, `assumptions`,
`risks`, `success_metric`, `validation_plan`, and adds:

| Field | Meaning |
|---|---|
| id | Unique action identifier |
| action_type | investigate, pilot, implement, monitor |
| audience | Specific proposed customers, products, stores or decision makers |
| intervention | What would actually be done; an audit names its deliverable and decision |
| mechanism_hypothesis | Proposed explanation to validate, not an established causal effect |
| priority_reason | Why this action comes before alternatives |
| alternatives_considered | Nonempty string list, including no change where relevant |
| dependencies | String list of operational/context requirements; may be empty |
| expected_benefit | Honest benefit statement; no assumed recovery of an observed gap |
| benefit_basis | unquantified, scenario, measured |
| benefit_calculation | Required for scenario/measured: assumptions, formula or measured estimate and evidence |
| decision_rule | How evidence leads to expand/change/stop; identify unset thresholds |
| implementation_basis | Required for implement: why evidence and context justify rollout |
| proposed_owner | Optional role, explicitly proposed if unconfirmed |

Factual titles, summaries and rationale retain causal-language screening. Proposed actions,
mechanism hypotheses and validation plans can describe causal questions. The reviewer checks
whether claims are supported; schema validation cannot evaluate commercial wisdom or prove causality.
A pass requires an explanation, not simply checked boxes. No fixed insight or recommendation counts.

The renderer supports legacy artifacts without fabricating new business reasoning. Legacy charts
are no longer selected automatically. HTML puts decisions/actions first, selected evidence next,
with expandable full detail; Markdown uses the same order and a complete technical appendix.
Critical uncertainty stays visible. Reports are self-contained and all text is HTML-escaped.
