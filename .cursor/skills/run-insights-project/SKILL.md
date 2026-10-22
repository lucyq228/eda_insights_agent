---
name: run-insights-project
description: Coordinate scoping, analyst investigation and independent review using shared deterministic tools.
---
# Run a business investigation
The main chat is the analyst agent; delegate scoping to a1-scope-feasibility and
independent review to a3-review-insights. These are three roles, not four.

1. start_run.py --data <file> --request <user words>; profile with profile_data.py.
2. Scoping specialist defines metrics, roles, grain, views and initial questions.
   Ask only material questions. Defaults and assumptions are explicit, not user answers.
3. Save scope and feasibility using existing scripts. Resolve blocked steps.
4. Exploratory scope: approve_scope.py --exploration activates under the original request.
   Confirmatory scope: approve_scope.py --user-confirmation <actual quote>.
5. advance_run.py runs quality, preservation and the initial manifest.
6. Analyst reads aggregate evidence. Use run_tool.py --followup-reason with registered
   tools for meaningful unresolved questions within scope. Default max_followups is 12.
   No repeated approval for routine exploration. No arbitrary agent calculations.
7. Independent reviewer checks evidence AND coverage; analyst executes requested follow-ups.
8. Save review, insights and report, then finalize_run.py. Report unresolved areas and
   data limits. There are no fixed counts. Each recommendation needs evidence and validation.

New objective/dataset or use of excluded predictors requires a new scope. Preserve all
run provenance. Use run_status.py to resume. The legacy approved_scope filename now means
an activated immutable scope; its authorization field distinguishes exploration from consent.

New scopes use report_schema_version: 2. Analyst and reviewer both use business-reporting/SKILL.md.
Finish only after the reviewer resolves business_review revisions and validates the v2 insight
contract. Report generation preserves full evidence in detail while putting decisions first.
