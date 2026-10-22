---
name: scope
description: Define business intent, source grain, metrics, data roles, declared aggregate views and a feasible initial plan.
---
Use read_context.py, then save_scope.py --file <draft>. Required fields remain project_name,
purpose, decision_supported, target {column,type,definition}, unit_of_analysis and hypotheses.
Each hypothesis is a meaningful question with id, statement, rationale, support_criteria and
pathway [{tool,params,purpose}]. There are no fixed counts. Use mode exploratory for discovery.
Record roles {customer, transaction: [store key, transaction key], quantity, product, store},
date_column, entity_column where applicable, views and max_followups. See examples/qvi_scope.json.
Preserve IDs/components even when excluded from predictors. Declare model drivers explicitly.
Use descriptive decomposition before association screening. State data limits and assumptions.
Substantive user questions go in user_questions; do not ask permission for routine analysis.
For new scopes set report_schema_version: 2 and business_context {audience, decision,
available_levers: [], constraints: [], success_measures: [], unknowns: []}. Unknown values
are valid. Record inferred context as assumptions, never as confirmed stakeholder instructions.
