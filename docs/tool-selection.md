# Choosing analysis tools

Choose the question first, then the smallest calculation that answers it. Use the
canonical names below in new scopes, CLI calls and review follow-ups.

| Tool | Use when | Reuse rule |
|---|---|---|
| `feature-target-associations` | Screen individual feature-target associations. | Deep dives reuse the same unadjusted test; they are not independent confirmation. |
| `correlation-matrix` | Inspect overlap among numeric drivers. | Descriptive matrix; does not add hypothesis tests. |
| `target-by-numeric-bins` | Inspect a numeric feature with a binned target profile. | Reuse the screen association; use nonlinearity-check only for an additional curvature question. |
| `target-by-group` | Compare target levels or class proportions across categories. | Canonical categorical deep dive; do not also run legacy pair-deep-dive for this group. |
| `correlation-by-group` | Compare a numeric feature-target correlation across groups and pooled versus within. | Reuse its combined within result instead of adjusted-correlation with only the same group on the same rows. |
| `adjusted-correlation` | Adjust one numeric feature-target relationship for chosen numeric or categorical controls. | Run when adjustment is the main question or additional controls change the comparison. |
| `predictive-feature-importance` | Measure joint predictive usefulness with random-forest permutation importance. | Linear coefficients are a separate model; they do not give the direction of random-forest importance. |
| `within-between-correlation` | Separate one association within and between repeated entities. | Use for entity-period dependence; ordinary grouping is not a replacement for clustered inference. |
| `within-between-regression` | Estimate within and between associations for numeric drivers jointly. | Coefficients are adjusted slopes, not predictive importance or causal effects. |

`nonlinearity-check` adds a quadratic curvature check and mutual information;
it does not prove every threshold or nonlinear shape. `time-trend` summarizes
periods, not within-entity effects. `multiple-testing-adjustment` runs automatically.
Sales accounting tools retain their distinct descriptive responsibilities.

## Evidence and interpretation

Screening, a deep dive and the pooled part of a group analysis may reference the
same statistical test. Identical tests share `test_id` and enter BH once; all result
references retain the adjusted q-value for report lookup. IDs distinguish the exact
sample, variable names, types, method, controls, prepared dataset and analysis view.
Legacy findings without IDs remain separate rather than guessing equivalence.
Data-selected follow-ups remain exploratory; deduplication does not solve adaptive
testing or invalid original p-values.

Adjusted correlations, standardized slopes and predictive importance are different
quantities. Do not compare their magnitudes as one ranking. Predictive importance
includes a separately labeled linear-coefficient output; it is not the random
forest's direction. Panel methods address repeated entities and must follow the
agreed within/between question rather than always preferring within effects.

## Compatibility

Old tool IDs resolve through `registry.ALIASES` but are hidden from the catalogue.
Old categorical `pair-deep-dive` calls route to `target-by-group`; old numeric calls
route to `target-by-numeric-bins`. Direct legacy Python function names remain usable.
Approved scope snapshots are never rewritten. New saved results use canonical tool
IDs and record `requested_tool`; readers accept the old multiple-testing artifact.
Historical exported reports are snapshots and are not rewritten.

## Report provenance

Each key insight displays unique supporting tool tags beside strength and confidence.
Tags come from valid cited result records, use canonical names, and exclude uncited
analyses. Agents only need to cite evidence normally; no separate tool list is required.
The Markdown report lists the same tools. Rebuild reports to show tags in existing runs.

## Changes in event rates

First compare events and eligible units in each cohort. For one observed binary outcome per
eligible row, use `rate-change-decomposition` when group composition could explain the change.
For example, use `{"cohort":"launch_wave","baseline":"A","comparison":"B","by":"entry_channel"}`.
Declare cohort and grouping as drivers or segments with timing verified before the outcome.
Confirm unique units and comparable observation windows separately. Aggregate inputs containing
rates or exposure counts require a different denominator treatment.

The benchmark applies baseline group rates to comparison counts. Benchmark minus baseline is
mix; comparison minus benchmark is within-group change. Both contributions use percentage points.
Missing group labels are retained. A comparison-only group leaves full attribution undefined.
Use another grouping or shelf tool for a distinct, reasoned question; summing explanations
from overlapping groupings double counts the same change.

## Screening dimensions for changes in counts and rates

For a broad change investigation include `dimension_omissions` in the scope (an empty object
when every eligible dimension is screened). Plan one initial step per distinct eligible dimension,
with a common metric, baseline and comparison. Use the full profile to identify meaningful grouping
fields. The scope validator checks categorical and binary columns except identifiers, target and
period roles. Record omitted fields as column-to-reason pairs, including timing, inadequate coverage
or duplicate labels (name the representative and verify the one-to-one mapping). For specific
single-group questions the usual focused scope is sufficient.

Use `count-change-contribution` for a numeric additive count or a prepared binary indicator whose
sum counts events. For individual units use a unique ID per period; for pre-aggregated counts confirm
disjoint groups, source keys, complete observation, and that preparation preserved the input totals.
A group missing in an observed period is unknown unless the source guarantees zero; only then set
`absent_is_zero` to true. Periods must cover comparable exposure and use the same units.

Example params: `{"cohort":"period","baseline":"3","comparison":"4","by":"channel"}`.
The default compares to the specified prior period. Add `"history":["1","2","3"]` only when there
are at least three consecutive, equally spaced pre-periods, the comparison immediately follows,
and extrapolation is justified. Supply labels exactly as stored. The tool fits a straight line
to each group's history and projects one period ahead. Inspect pre-period stability, seasonality
and missing counts before interpreting the gap. Never estimate a baseline from comparison outcomes.

For rates, reuse the existing tool and inspect both group shares and within-group rate changes.
Look for countervailing shifts even when totals reconcile to zero. Prioritize up to three deep
dives after the screen, including plausible interactions. No limit applies to the initial screen.
For each planned screen the review supplies a `dimension_coverage` entry keyed by step ID, e.g.
`{"H1.S1":{"status":"movement","reason":"Group losses of 12 offset gains of 12."}}`.
Use movement, little movement, or unresolved against the agreed business threshold. Cite group
magnitudes, uncertainty and data gaps. The report combines these entries with scoped omissions.
