---
name: scope
description: Propose a sequential investigation table, guide the user, and define the analyst handoff.
---
Use read_context.py, then save_scope.py --file <draft>. The script writes scope_proposal.json
and scope_proposal.md from the same ordered questions. Present the table in chat; a file alone
is not a scope discussion. Include feasibility limits, defaults and a request to confirm or revise.

Keep the existing schema: project_name, purpose, decision_supported, target {column,type,definition},
unit_of_analysis, hypotheses. Use mode exploratory for discovery; confirmation does not make it confirmatory.
Each hypotheses item is a sequential business question with id, statement, rationale,
support_criteria and pathway [{tool,params,purpose}]. support_criteria states what evidence would
answer the question, not a required significant result. No fixed number of questions.

pathway contains only initial calculations that can run before inspecting results. An exploratory
adaptive question instead uses pathway: [], followup_when (evidence trigger and intended decision),
and candidate_tools (registered tool IDs; optional for synthesis). These are not automatic tool calls
or promises of feasibility. Concrete follow-ups pass normal runtime checks after evidence is available.
The reviewer accounts for every question, including why a conditional branch was not pursued.

Declare population/comparison boundaries and missing coverage in assumptions/out_of_scope;
declare drivers, segments, exclusions, roles, date/entity columns, views and max_followups as applicable.
Preserve keys and accounting components. Do not force sales decomposition onto other numeric targets.
User questions require question and why_it_matters; offer a recommended default when possible.
Resolve them using actual user answers and reflect decisions in the final scope, not just answers.json.

All new scopes require confirmation of the presented version. Routine analysis within it does not.

The target overview runs automatically in the post-confirmation data-quality stage. Do not put
eda-overview, profiling, preparation, multiple-testing or reporting tools into an analysis pathway.
Initial pathways and candidate_tools must name selectable analysis tools from read_context.py.
