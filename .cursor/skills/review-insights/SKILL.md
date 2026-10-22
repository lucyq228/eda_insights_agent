---
name: review-insights
description: Independently review business coverage, statistical evidence and proposed actions, then build a report.
---
Use review_checks.py, save_review.py --file <draft>, save_insights.py --file <draft>, build_report.py.
Read result JSON and aggregate tables via insight-shelf/scripts/read_evidence.py.
Review every planned question. Verdicts: supported, partially_supported, not_supported,
inconclusive; not_evaluated is reserved for user-waived steps. Follow-ups have a tool,
params and reason; they keep review open until the analyst executes them.

insights.json contains headline_summary, insights, limitations, next_steps and optional
recommendations. Each insight has id, title, statement, strength, confidence, evidence
[{result, finding}], caveats and suggested_next_step. No required count. If empty, supply
no_findings_reason. Descriptive evidence may omit intervals; never manufacture significance.
Recommendations have action, rationale, evidence [{result, finding}], evidence_type,
assumptions, risks, success_metric, validation_plan. Proposals must acknowledge observational
limits and be framed as experiments when causal support is absent.
Challenge missing mechanisms, wrong grain, exposure differences, unstable segments,
repeated entities, rank deficiency, and overbroad null conclusions. Report unanswered questions.
