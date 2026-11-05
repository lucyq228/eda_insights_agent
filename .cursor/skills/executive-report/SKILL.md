---
name: executive-report
description: Turn a reviewed analysis checkpoint into a layered executive report with traceable charts, complete comparison tables and a closing recap. Use after the original analytical report is saved; deliver both reports.
---
Keep the existing three agents. The analyst drafts the storyline; the reviewer checks its
claims against saved evidence and runs scripts/build_executive_report.py. Do not rerun analysis,
change the approved scope, rewrite insights.json, or replace report.html/report.md here.

## Story before layout
1. Read approved_scope.json, review.json, insights.json, report.html and complete aggregate
   result tables through insight-shelf/scripts/read_evidence.py. Never use only preview rows.
2. Lead with a clear answer to the business question. Order sections by explanatory logic,
   not tool execution order. Move from overall pattern to meaningful segments and selected
   intersections. State the question that motivates each deeper layer.
3. Use a conclusion-led headline, plain-language explanation, complete comparison table and
   supporting chart per major finding. Retain benchmark groups and offsets; highlight relevant
   rows instead of filtering everyone else away. For very large tables, keep complete evidence
   in the calculation appendix; do not silently top-N or invent an Other bucket.
4. Distinguish group change from portfolio contribution, counts from shares, percentages from
   percentage points, and pooled from adjusted/within comparisons. Name the group definition
   when a deeper partition refines the explanation. Do not add overlapping decompositions.
5. Close with the key conclusions, a visual recap, full calculation table and actionable next
   steps. For rate/count attributions, use a reconciled waterfall. For associations, use an
   evidence summary; never make correlations or predictive importance into additive effects.
6. Keep material uncertainties beside their findings. Preserve source limitations and reviewed
   recommendations. Do not turn a small, descriptive pattern into a confident causal claim.
   Refer new questions or insufficient evidence back to the analyst/reviewer workflow.

## Save the storyline
Write drafts/executive_story.json using the schema/example in docs/executive-reporting.md.
Copy the current report.json SHA-256 into checkpoint_sha256. Sections refer to result IDs,
table names and columns, not copied chart/table values. For change tools, the renderer creates
volume, rate and share changes from the saved aggregates and verifies the attribution formulas.
Chart titles and table labels should use business language with units. Numeric narrative claims
must be checked manually against those same tables; automatic checks cannot validate prose.

Send the draft and its referenced results to the existing reviewer. The reviewer verifies:
- Every conclusion and recommendation is supported, with no stronger claim than the checkpoint.
- Each layer answers the preceding question; alternatives and uncertainty are not suppressed.
- Charts, comparison tables and closing recap tell the same story at the same grain/periods.
- Any numbers in prose match the source, including rounding, signs, units and denominators.
- Highlighting preserves the full comparison and meaningful offsets.

Then run build_executive_report.py --file <draft>. It validates the numerical evidence, renders
executive_report.html and saves its input hashes. Inspect the output visually in the local browser
at desktop and narrow width; fix chart labels, overlap and confusing tables before finalization.
The existing finalize_run.py now requires both current reports. Deliver executive_report.html,
report.html AND report.md. The executive report links to the original analytical reference.

If new analysis changes the evidence, use the existing review/checkpoint rebuild flow first;
then redraft/recheck the executive story. A stale executive report cannot finalize the run.
