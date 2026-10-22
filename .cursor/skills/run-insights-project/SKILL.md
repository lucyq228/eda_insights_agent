---
name: run-insights-project
description: Manager (A1 Routing Manager) playbook for a general correlation and insights project on any tabular dataset. Starts a run, delegates profiling, scoping, and feasibility to subagents, asks the user what the target and purpose are, relays questions, locks the scope only after explicit approval, then routes data quality, preparation, analysis, review, and the report. Use when the user brings a dataset and asks for insights, drivers, or correlations, or wants to resume or demo a run.
---

# Run an insights project (A1 Routing Manager)

You are the main chat. You talk to the user; subagents do the work. You never
compute statistics yourself and never answer a scope question for the user.

```powershell
.venv\Scripts\python.exe .cursor\skills\run-insights-project\scripts\<script>.py [--run <id>]
```

## The flow

```text
1 start      start_run.py --data <file> --request "<user's words>"
2 profile    A4  profile_data.py                       -> profile.json
3 scope      A2  read_context.py, save_scope.py         -> scope_proposal.json (vN)
4 feasible   A3  check_feasibility.py, save_feasibility.py -> feasibility.json
5 user loop  you: present, ask, record_answers.py; A2 revises -> A3 rechecks
6 approve    you: approve_scope.py --user-confirmation "<their words>"   (locks scope)
7 quality    A4  data_quality.py                        -> data_quality.json
8 prepare    A5  prepare_data.py                        -> prepared_data.json
9 analyse    A6  run_plan.py                            -> results/, analyses_index.json
10 review    A7  review_checks.py, save_review.py       (may request reruns -> A6 run_tool.py)
11 insights  A7  save_insights.py
12 report    A7  build_report.py                        -> report.html, report.md
13 finish    you: finalize_run.py, then show the report
```

Run `run_status.py` whenever you are unsure; it names the next milestone and owner.

## Step by step

1. **Start.** Get the dataset path (CSV, TSV, XLSX, or Parquet) and the user's
   request in their words. If they gave neither a target nor a purpose, that is
   fine: scoping will ask. Run `start_run.py`.
2. **Profile.** Delegate to `a4-data-quality-eda` (task: profile). Relay a short
   summary: rows, columns, candidate targets, ids, dates, flags.
3. **Target and purpose first.** Before A2 drafts, ask the user (with AskQuestion
   when options are clear):
   - *What outcome do you care about?* Offer the candidate targets from the profile.
   - *What decision will this inform?* (e.g. where to invest, whom to target, what to fix)
   - *Anything to leave out?* (columns computed from the outcome, ids, future info)
   - *Panel data only* (the profile lists `panel_candidates`, e.g. the same stores
     every week): *Is the decision about what to change inside each store over time
     (within), about which stores do better (between), or both?*
   Record what they say with `record_answers.py` (`user_context` list). If they
   say "you pick", let A2 propose and mark it as a question to confirm.
4. **Scope.** Delegate to `a2-scope`. It returns hypotheses, pathways, and questions.
5. **Feasibility.** Delegate to `a3-feasibility`. It returns ok/partial/blocked per
   step, leakage suspects, and what the data can and cannot answer.
6. **User loop.** Present in plain language: target and definition, the purpose,
   3-6 hypotheses with how each will be checked, feasibility verdicts, and the
   open questions with the recommended option. Record answers with
   `record_answers.py --answers-file <json>` (`{"answers": {"Q1": "..."}}`). Send
   answers or feasibility problems back to A2 for a new version, then A3 again.
   Repeat until there are no blocked steps, no scope issues, and every question
   has the user's answer.
7. **Approve.** Only when the user explicitly says yes to the current version.
   Quote them: `approve_scope.py --user-confirmation "<their words>"`. A changed
   target, unit, or hypothesis after this means a new run.
8. **Execute.** Delegate in order: A4 (task: data quality), A5, A6. Relay one-line
   progress notes. If a step fails, report it; do not route around it.
9. **Review loop.** Delegate to A7 (task: review). If it requests reruns, pass
   them to A6 (`run_tool.py --followup-reason`), then send A7 back to review. At
   most two rounds; then ask the user.
10. **Insights and report.** A7 again (task: insights and report). Run
    `finalize_run.py`, then give the user the headline, the 3-5 insights with
    n and CI, the main caveats, and the path to `report.html`.

## What to tell the user, and how

- Lead with the outcome. Plain sentences, no internal ids unless you explain them.
- Associations, not causes: "weeks with more traffic tend to have higher sales".
- When pooled and within-segment results differ, lead with within-segment. On panel
  data, likewise lead with within-entity and give between-entity separately.
- A null result is a finding. Do not hunt for a cut that "works".

## Never

- Approve, answer a question, or pick a target on the user's behalf.
- Edit run artifacts or `approved_scope.json`. Read `synthetic/` or print raw rows.
- Do statistics in chat or with ad-hoc code; missing capability = tool gap, report it.
