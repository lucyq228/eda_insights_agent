# Business insights agents

Three agents — **scoping, analyst, reviewer** — investigate business questions with a shared,
reproducible calculation library. The main chat is the analyst, which delegates scope design
and independent review. The workflow supports exploratory discovery and prespecified analysis.

## What changed

- Preserve IDs, quantity and original categories in the clean base; exclusions affect modeling only.
- Business summaries decompose sales into customer count, frequency, units and average price.
- Segment intersections and temporal diagnostics expose patterns hidden by marginal correlations.
- Named aggregate views support customer or store-period analysis with explicit metric definitions.
- Agents can read bounded aggregate evidence; no raw personal rows are printed.
- Present a sequential question / purpose / tools table and confirm the scope once before analysis.
- Initial calculations run first; evidence-driven follow-ups stay inside the agreed boundaries.
  Routine follow-ups need reasons, not repeated approval.
- No required number of hypotheses or insights. Recommendations need evidence, assumptions,
  risks, a success metric and a validation plan.

## Setup

```sh
python -m venv .venv
# Activate the environment using the command appropriate for your shell.
python -m pip install -r requirements.txt
python -m pytest tests -q
```

In Cursor ask `/run-insights-project` to investigate a dataset and business question.
See [the architecture](docs/architecture.md) and [QVI example scope](examples/qvi_scope.json).
The example is a schema/plan only; customer data and run outputs are never committed.

## Tools

The existing association, nonlinearity, prediction and panel tools remain available.
New tools are `business-summary`, `temporal-diagnostics`, and `period-comparison`.
Statistical tools accept `view` to run on a declared aggregation rather than source lines.
`read_evidence.py` reads result tables in bounded pages. Descriptive metrics are evidence
without fabricated confidence intervals. Category caps affect display only.

## Limits

EDA identifies patterns and opportunity hypotheses, not guaranteed sales lift. Average unit
price includes mix; customer frequency reflects the observation window. Missing dates do not
prove closure. Temporal anomaly flags use a simple robust baseline, not a seasonal forecast.
Ordinary correlation methods retain independence assumptions; panel tools and clustered model
coefficients are available for appropriate questions. Data-selected follow-ups remain exploratory.

Run artifacts are hashed and stored under runs/ (gitignored). No external service is required
for calculation; Cursor hosts the agent reasoning. Legacy confirmatory scopes remain supported.

## Guided scoping

The Scope Agent recommends defaults when the goal is broad, presents `scope_proposal.md`,
and waits for confirmation. The table is rendered from the same `hypotheses` used by execution
and review. Empty pathways with `followup_when` describe conditional exploration; their candidate
tools do not run automatically. See [scoping examples](docs/scoping-examples.md).

New scopes require `approve_scope.py --user-confirmation "<actual user reply>"`, including
exploratory scopes. The legacy `--exploration` flag no longer bypasses confirmation. Existing
locked runs remain readable. No additional package or agent is required.

Tool selection and compatibility: see `docs/tool-selection.md`; the registry exposes canonical names and reuse guidance.
