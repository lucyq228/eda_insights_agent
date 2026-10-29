---
name: run-insights-project
description: Coordinate guided scoping, bounded analysis and independent review using shared tools.
---
The main chat is the analyst; delegate scoping to a1-scope-feasibility and review to
a3-review-insights. These remain three roles, not four.

1. start_run.py --data <file> --request <user words>; profile with profile_data.py.
2. Scoping specialist proposes sequential questions, purposes and tools, with defaults,
   boundaries and gaps. Save scope and feasibility. Resolve blocked initial steps.
3. Main chat presents scope_proposal.md as a table with feasibility caveats and asks the user
   to confirm or revise. STOP before substantive analysis. Guide uncertain users with a recommendation.
4. Record actual answers with record_answers.py. If decisions change the scope, revise it and
   rerun feasibility; present the final version. approve_scope.py --user-confirmation <actual quote>
   locks that version in both exploratory and confirmatory modes. Never treat the original broad
   analysis request as approval of a proposal the user has not seen. --exploration cannot bypass this.
5. advance_run.py runs quality, preparation and the initial manifest. Analyst reads aggregate evidence.
6. Address adaptive questions through registered tools with --followup-reason and --hypothesis.
   Read run_tool.py --help for arguments. Use only scoped drivers/views/populations. Each follow-up
   identifies the question and evidence that warrants it. No routine repeat approvals; default budget 12.
   Stop at adequate answers, exhausted evidence or budget. Do not execute all candidate tools by default.
7. Reviewer accounts for each scoped question and requests only in-scope follow-ups. Record gaps and
   out-of-scope opportunities; do not silently expand the investigation.
8. Save review, insights and report, then finalize. Every recommendation needs evidence and validation.

Continuation: answer clarifications from existing evidence. Continue in-scope calculations within
budget and invalidate/rebuild review/report as usual. For a new objective, dataset, population or
excluded factors, start a new run and scope discussion. Put the prior run ID and relevant evidence
references in the new request/context; preserve the old locked run. Reuse context, not stale estimates
when definitions, controls or population change. No extra agent or run-linking subsystem is needed.
Use run_status.py to resume.
