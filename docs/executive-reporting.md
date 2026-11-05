# Two reports, one reviewed body of evidence

The original report.html and report.md remain required outputs with hypotheses, findings,
tools, review verdicts and limitations. executive_report.html is a separate presentation.
No fourth agent or new analysis pipeline: analyst authors the story, reviewer checks it and
runs the renderer, coordinator finalizes and delivers both. Presentation does not alter the
checkpoint bytes. If analysis changes, rebuild the reviewed checkpoint and presentation.

The original report is still built by review-insights/scripts/build_report.py. Then use
executive-report/scripts/build_executive_report.py --file <draft>. Run run_status.py to resume.
Existing runs with only the original report remain readable; finalizing under the new workflow
requires the additional executive report. No migration or automatic replacement is performed.

## Small storyline schema

```json
{
  "checkpoint_sha256": "copy SHA-256 of the current report.json",
  "title": "A concrete answer to the business question",
  "summary": "Short answer with the most important qualification.",
  "sections": [{
    "headline": "A conclusion that advances the explanation",
    "message": "Explain what changed and why this comparison matters.",
    "insight_ids": ["I1"],
    "result": "H1.S1",
    "highlight": [{"group": "Example segment"}],
    "charts": [{
      "kind": "bar",
      "title": "Group shares changed between cohorts",
      "x": "segment",
      "y": ["baseline_share_pct", "comparison_share_pct"],
      "labels": {"baseline_share_pct": "Baseline", "comparison_share_pct": "Comparison"},
      "unit": "Share of all eligible units (%)"
    }],
    "next_question": "Which subgroups explain this movement?"
  }],
  "conclusion": "Recall the main findings and their limits.",
  "recap": {"result": "H1.S1"}
}
```

Example labels/IDs are illustrative; use actual reviewed evidence. Add as many logical layers
as the question needs, without a fixed number of sections. Omit highlight if unnecessary.
Sections require a chart, or chart_omission_reason explaining why the full table suffices.
Recommendations and limitations are taken from the reviewed insights, not invented in the story.

For rate/count results, groups and (for rates) cohorts are loaded automatically. Rate tables
add volume_change, rate_change_pp, share_change_pp, total_pp. Display/plot fields ending in
_share_pct or _rate_pct are percentages; source _share and _rate fields remain fractions.
A segment label combines all grouping fields. Single-group tables use group; joint tables
use group_1, group_2, etc. grouping_columns in the result maps these to original fields.
Default comparison tables preserve every row and show baseline/comparison values and changes.
Optional columns maps display field names to human-readable column labels; keep all grouping
fields. The closing calculation table always contains all groups and the full attribution.

For other tools, supply table (an actual saved aggregate table name), x and y columns in charts.
Chart kind can be bar (horizontal, all categories) or line (ordered rows; ensure chronology).
Provide a shared unit and only comparable measures on the same chart. Existing confidence
interval/sample columns remain in the table. Without recap, the close summarizes section
headlines and evidence IDs instead of inventing additive contributions. A no-findings run
can use an evidence section explaining its limits; do not fabricate positive conclusions.

## Select a detailed waterfall

recap defaults to net mix + within for a rate, or all-group net contribution for a count.
To explain particular groups, add components. Each component uses metric, label and either
where (grouping field/value matches) or remaining: true. Remaining selects only rows not yet
used for that metric. Every contribution must be covered exactly once; overlaps and omissions
are rejected. All components come from the SAME result, population and comparison.

```json
{
  "result": "F1",
  "components": [
    {"label": "Selected group mix", "metric": "mix_pp", "where": {"group_1": "Example tier", "group_2": "Example channel"}},
    {"label": "Other groups mix", "metric": "mix_pp", "remaining": true},
    {"label": "Within-group changes", "metric": "within_pp", "remaining": true}
  ]
}
```

Rate metrics: mix_pp, within_pp. Count metric: contribution. A count history baseline is labeled
Expected rather than the observed starting period. Unsupported baseline rates stay undefined;
show the complete table with a chart omission reason and explain the unresolved attribution.
Do not request a complete waterfall when reference rates are missing.

## Evidence and checks

The report reads complete saved CSV tables, not JSON previews or raw personal rows. A declared
view's result is already at its approved grain. No new statistical estimates are calculated.
Presentation arithmetic derives only changes, percentages and sums from saved results.
Rates reconcile events, denominators, shares, reference rates and contributions; count totals
reconcile to saved findings. Charts and tables share the same data. The full calculation table
and formulas let readers reproduce each contribution; the waterfall table identifies which
rows are summed for each bar. Numeric prose still needs reviewer verification.

Hashes bind the output to report.html, report.md, review, insights and saved result tables.
Changed, missing or stale inputs/output prevent finalization. Failed rendering leaves the
original analytical report intact. Tests cover preservation, reconciliation, stale inputs,
missing references, undefined rates, unsupported waterfalls and all-row benchmark coverage.
