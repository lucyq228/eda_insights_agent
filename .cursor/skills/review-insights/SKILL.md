---
name: review-insights
description: Challenge every analysis result, give each hypothesis a verdict, request targeted follow-ups, pick 4-10 distinct evidence-backed findings that matter for the decision, and build the Markdown and HTML report. Use for the review, insights, and report milestones.
---

# Review, insights, report (Reviewer & Insights specialist)

```powershell
.venv\Scripts\python.exe .cursor\skills\review-insights\scripts\review_checks.py
.venv\Scripts\python.exe .cursor\skills\review-insights\scripts\save_review.py   --file runs\<run>\drafts\review.json
.venv\Scripts\python.exe .cursor\skills\review-insights\scripts\save_insights.py --file runs\<run>\drafts\insights.json
.venv\Scripts\python.exe .cursor\skills\review-insights\scripts\build_report.py
```

## 1. Review (`drafts/review.json`)

`review_checks.py` lists every result with its flags (SIMPSON, HETEROGENEITY,
NONLINEAR, ATTENUATED, WEAK MODEL, collinear pairs; on panel data also PANEL SPLIT,
PANEL POOLED, CLUSTERING, LITTLE WITHIN VARIATION, TIME-INVARIANT) and per-finding
issues (small n, CI includes 0, fails FDR, negligible size). Read each result file
it names in `results/<label>.json` if you need detail.

**Panel data** (the scope has `entity_column`): pooled tools mix two questions.
Lead with the within-entity estimate ("in weeks when a store spends more on promo,
its sales tend to be higher"), report the between-entity one separately ("stores
that spend more tend to sell more", n = entities), and do not headline a pooled
result the panel tools contradict. A driver that is only between (fixed per entity)
says which entities differ, not what moves inside one.

```json
{
  "hypothesis_verdicts": [{"id": "H2", "verdict": "supported | partially_supported | not_supported | inconclusive | not_evaluated",
                           "reasoning": "...", "evidence": [{"result": "H2.S1", "finding": "<finding label>"}]}],
  "challenges": [{"issue": "pooled promo r is negative", "resolution": "within-region r is positive; lead with it"}],
  "rerun_requests": [{"tool": "segment-correlation", "params": {"x": "staff_hours", "by": "store_format"},
                      "reason": "importance is high but the screen is weak; check by format"}]
}
```

Judge against each hypothesis's `support_criteria`. Reruns are for questions the
results raise, not for searching until something is significant. If you request
follow-ups, the review stays open; after the coordinator runs them, review again.

## 2. Insights (`drafts/insights.json`)

```json
{
  "headline_summary": "two sentences a manager would remember",
  "insights": [{"id": "I1", "title": "short, an association", "statement": "plain language with the number",
                "evidence": [{"result": "H2.S1", "finding": "promo_spend_k ~ weekly_sales_k | within region"}],
                "hypothesis": "H2", "strength": "strong | moderate | weak | null",
                "confidence": "high | medium | low", "caveats": ["..."], "suggested_next_step": "..."}],
  "limitations": ["observational data", "..."],
  "next_steps": ["..."]
}
```

4-10 distinct insights, ranked by what matters for the decision. Do not split or
pad findings to meet the range. Include a null or surprising
result when it changes what the user would do. Causal wording ("drives", "impact",
"leads to", "because of", "effect of") is refused by the save script.

Use `not_evaluated` only when every pathway step for that hypothesis has an
explicit user-approved waiver. A skipped step is visible in the report lineage;
it is not a failed result and it is not evidence.

## 3. Report

`build_report.py` writes `report.md` and a self-contained `report.html` that quote
n, CI, and q for every evidence item (plus the number of entities for panel
findings), add a panel note when the scope has `entity_column`, and embed the charts.
