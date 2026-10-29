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
