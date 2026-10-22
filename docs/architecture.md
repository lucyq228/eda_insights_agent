# Architecture

## Three roles

1. Scoping agent: business objective, source grain, keys, metrics, assumptions, views and initial plan.
2. Analyst agent (main chat): deterministic execution, aggregate evidence inspection, bounded follow-ups.
3. Reviewer agent: independent correctness/coverage checks and evidence-backed recommendations.

The shared calculation library is insight_core/, exposed through tool_registry.yaml and CLI skills.
No extra coordinator agent is needed. The main chat handles coordination as part of the analyst role.

## Activation and adaptation

Scopes use mode exploratory or confirmatory (legacy default). A feasible exploratory scope can
activate with approve_scope.py --exploration under the recorded original request. Its authorization
is user_requested_exploration and user_confirmation is empty. Confirmatory scopes still require a
real approval quote. Substantive unanswered questions block either path. Never infer approval of
external actions or a genuinely different objective from exploratory authorization.

The active scope stays hashed and immutable. It declares roles, views, initial questions, exclusions
and max_followups (default 12). Additional registered calculations use --followup-reason; their
parameters, view, grain and mode are saved. New results invalidate review/report as before.
A new objective or dataset requires a new run. Do not redefine the scope to chase significance.

## Data and metrics

Preparation preserves all columns and categories after exact deduplication, target validity and date
parsing. Predictive exclusions do not delete accounting components. Roles may name customer,
transaction (a composite key list), quantity, product and store. Distinct customer/transaction counts
are nonadditive across product groups. Metrics use complete required keys/components and report
excluded rows. Customer spending/frequency covers the observed window, not individual exposure time.

Named views contain group_by, metrics {output: {column, agg}}, optional ratios
{output: {numerator, denominator}}, target, drivers, unit, and optional date_column/freq/entity_column.
Allowed aggregations: sum, mean, median, min, max, nunique, count, size. Ratios use existing metrics;
zero denominators produce missing values. No eval or arbitrary code. Views are derived from the base
at execution time and feasibility/sample size are checked at the resulting grain. Include composite
transaction keys when counting visits; nunique of a locally scoped transaction ID alone is insufficient.
Check segment stability before calling customer-by-segment rows unique customers.

## Evidence

Result JSON stores statistical/descriptive findings and a 30-row aggregate table preview. Full tables
are paginated by insight-shelf/scripts/read_evidence.py (up to 200 rows). Agents may inspect aggregates,
not raw personal records. Reports distinguish descriptive accounting from statistical evidence.
Recommendations carry action, rationale, evidence links, evidence_type, assumptions, risks,
success_metric and validation_plan. No minimum count; empty insight reports need no_findings_reason.

## Statistical safeguards

P-values retain precision until display. Category display caps do not change association estimates.
Rank-deficient adjusted coefficients are suppressed. With an explicit entity, adjusted OLS uses
clustered covariance and predictive holdout uses entities. Ordinary correlation tools still require
independence; warnings make that limitation visible. Panel tools remain available. High association
alone is a review warning, not proof of leakage; derived/name-based suspects remain blocked unless
excluded or given a documented leakage_justifications entry addressing timing and provenance.

Exploration does not become confirmatory simply because BH adjustment was applied. Repeated tests,
data-selected follow-ups and dependent observations require careful interpretation.

## Validation

Run python -m pytest tests -q. Tests include legacy end-to-end flows and business regressions:
frequency differences with identical purchase amounts, temporal volume changes with flat average
amounts, accounting reconciliation, preserved identifiers, view grain, aggregate evidence access,
category display invariance, p-value precision, and suppression of unidentified coefficients.
The QVI example plan is a manual integration benchmark; keep source data and artifacts out of git.

## Business decision and reporting contract
The three roles share report schema v2; no fourth writer agent is introduced. Scoping captures
business_context; the analyst proposes and compares actions; the reviewer independently assesses
business usefulness and writes business_review. New scopes opt into report_schema_version 2 and
cannot save a v1 insight draft. Legacy scopes/artifacts remain supported.

The business-reporting skill adapts communication principles for reports. The Python validator
checks structure, evidence references, selected charts and completed review, while semantic action
quality remains an explicit reviewer responsibility. Factual rationale is screened for causal
claims; mechanism hypotheses and test questions are separate fields. The renderer makes no LLM
calls, invents no business reasoning and performs no new calculations. It renders selected
registered charts only and preserves all cited evidence in detail. See business-report-schema.md.
