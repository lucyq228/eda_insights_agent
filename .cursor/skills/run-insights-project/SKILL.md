---
name: run-insights-project
description: Cursor Coordinator playbook for a general correlation and insights project on any tabular dataset. Starts and profiles a run, delegates combined scope and feasibility judgment, asks the user what the target and purpose are, locks the scope only after explicit approval, directly advances deterministic quality/preparation/selected analyses, and delegates independent review and reporting. Use when the user brings a dataset and asks for insights, drivers, or correlations, or wants to resume or demo a run.
---

# Run an insights project (Cursor Coordinator)

You are the main Cursor chat. You talk to the user. Two specialists provide
scope/feasibility and review/insight judgment. Deterministic scripts do all
profiling, quality, preparation, and calculation. Never answer a user-owned scope
question on the user's behalf.

```powershell
.venv\Scripts\python.exe .cursor\skills\run-insights-project\scripts\<script>.py [--run <id>]
```

## The flow

```text
1 start      start_run.py --data <file> --request "<user's words>"
2 profile    directly run profile_data.py               -> profile.json
3 plan       scope-feasibility specialist               -> scope_proposal.json + feasibility.json
4 user loop  present, ask, record; specialist revises and rechecks
5 approve    you: approve_scope.py --user-confirmation "<their words>"   (locks scope)
6 execute    directly run advance_run.py                -> quality + prepared + selected results
7 review     reviewer-insights specialist               (may request targeted run_tool.py follow-ups)
8 report     reviewer-insights specialist               -> report.html, report.md
9 finish     you: finalize_run.py, then show the report
```

Run `run_status.py` whenever you are unsure; it names the next milestone and owner.

## Step by step

1. **Start.** Get the dataset path (CSV, TSV, XLSX, or Parquet) and the user's
   request in their words. If they gave neither a target nor a purpose, that is
   fine: scoping will ask. Run `start_run.py`.
2. **Profile.** Run `profile_data.py` directly. Relay a short
   summary: rows, columns, candidate targets, ids, dates, flags.
3. **Target and purpose first.** Before the specialist drafts, ask the user (with AskQuestion
   when options are clear):
   - *What outcome do you care about?* Offer the candidate targets from the profile.
   - *What decision will this inform?* (e.g. where to invest, whom to target, what to fix)
   - *Anything to leave out?* (columns computed from the outcome, ids, future info)
   - *Panel data only* (the profile lists `panel_candidates`, e.g. the same stores
     every week): *Is the decision about what to change inside each store over time
     (within), about which stores do better (between), or both?*
   Record what they say with `record_answers.py` (`user_context` list). If they
   say "you pick", let the specialist propose and mark it as a question to confirm.
4. **Scope + feasibility.** Delegate one continuous task to
   `a2-scope-feasibility`. It returns 4-10 hypotheses, a selective manifest of
   shelf tools, questions, feasibility verdicts, leakage suspects, and what the
   data can and cannot answer. The shelf remains available; do not ask it to run
   one tool per hypothesis merely for coverage.
5. **User loop.** Present in plain language: target and definition, the purpose,
   4-10 hypotheses with how each will be checked, feasibility verdicts, and the
   open questions with the recommended option. Record answers with
   `record_answers.py --answers-file <json>` (`{"answers": {"Q1": "..."}}`). Send
   answers or feasibility problems back to the same specialist for a new version.
   Repeat until there are no blocked steps, no scope issues, and every question
   has the user's answer.
6. **Approve.** Only when the user explicitly says yes to the current version.
   Quote them: `approve_scope.py --user-confirmation "<their words>"`. A changed
   target, unit, or hypothesis after this means a new run.
7. **Execute.** Run `advance_run.py` directly. It performs deterministic quality,
   preparation, and only the approved pathway steps. It reuses complete results,
   prevents simultaneous duplicate milestones, and records per-tool runtimes.
   If the user explicitly omits a step, run `skip_step.py` with their quoted words;
   never represent a technical failure as a skip.
8. **Review loop.** Delegate to `a3-review-insights`. If it requests follow-ups,
   run them directly (`run_tool.py --followup-reason`), then send it back to review. At
   most two rounds; then ask the user.
9. **Insights and report.** Have the same specialist save 4-10 distinct findings
    and build the report. Run `finalize_run.py`, then give the user the headline, key findings with
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
