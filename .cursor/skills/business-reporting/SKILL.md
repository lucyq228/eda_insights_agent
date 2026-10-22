---
name: business-reporting
description: Turn reviewed analytical evidence into decision-ready HTML and Markdown business reports. Use when drafting recommendations, selecting supporting evidence, or reviewing a report for business usefulness.
---
# Business reporting
Use clarity, credibility, selective evidence and visual hierarchy. These principles are adapted
for a standalone report; do not create slides or impose slide counts or slide layouts.

Read the scope's business_context and the saved aggregate evidence. Use report_schema_version: 2
in new scopes and schema_version: 2 in new insight drafts. Follow docs/business-report-schema.md.

## Reason before writing
- Identify the decision, audience, available levers and constraints. Mark unknowns and proposed
  owners explicitly; never invent budgets, capabilities, customer reach, margins or user approval.
- Translate a finding into candidate actions. Compare alternatives, including no change. Higher
  historical spend does not establish the best audience to target; low spend is not recoverable lift.
- Explain the proposed intervention, population, hypothesized mechanism, priority and dependencies.
  Use investigation, pilot, implement or monitor. Recommend implementation only with appropriate
  evidence and operational context. An investigation must name the decision it will unlock.
- Request targeted, within-scope follow-ups when their answer could change the action or audience.
  Stop when evidence or the budget is exhausted and name the unresolved decision.
- Do not default every recommendation to an audit because causal lift, budgets or owners are
  unknown. When evidence supports a useful business question, propose a concrete conditional pilot
  and state its prerequisites. Reserve investigations for uncertainties that would change the
  intervention or make even a pilot inappropriate. Do not invent an operational problem merely
  because a segment or brand has a large sales share.
- State expected benefit as unquantified unless measured or supported by a transparent scenario.
  A scenario must state assumptions and calculations; accounting gaps are not intervention lift.
- Use success_metric and decision_rule together: what is measured, and what result leads to
  expand/change/stop? Unknown business thresholds must be set before a pilot, not invented.

## Write for the reader
Lead with the executive takeaway and decision requested. Rank actions by business relevance,
feasibility and uncertainty, explaining the ranking. Do not force a number of findings or actions.
Keep action titles short and verb-led. Write rationale, intervention, expected benefit and
success measure as concise sentences, not analytical paragraphs. Put qualifications in the
appropriate detail fields and avoid repeating them across every field. The first screen should
make the decision and first action apparent. Additional actions remain easy to scan.
For each finding use Point -> Proof -> Meaning -> Action where applicable. Write a concise title,
brief_summary and business_implication. Select key_evidence references that prove the takeaway;
retain every supporting reference in evidence for the audit trail. Use clear denominators and units.
Do not turn a trivial identity (larger bags cost more) into a commercial insight. For bulk value,
request comparable price per weight, with product/brand mix accounted for, through shared tools.

Select charts explicitly using {result, index, caption}; the chart must already exist in that
result. Explain what it proves in the caption. Omit a chart if it does not aid the decision.
Never choose the first chart just because it exists. No invented values or decorative charts.
Keep decisive limitations visible in decision_uncertainties and each finding's decision_caveat.
Put statistical details, full evidence, repeated caveats and hypothesis verdicts in the appendix.

## Review before saving
Ask: Can a reader quickly identify the decision, action, audience and reason? Does evidence
support the claim? Is the action concrete rather than a generic test instruction? Are alternatives,
tradeoffs and stop/expand criteria clear? Distinguish observed facts from proposed mechanisms.
Record the review in business_review {decision_clarity, actionability, evidence_alignment,
uncertainty, communication}, each {status: pass|revise|not_applicable, reason: ...}.
Resolve revise items before finalizing. If no action is defensible, give no_recommendations_reason.
A schema pass is not proof of business usefulness: the independent reviewer must exercise judgment.
