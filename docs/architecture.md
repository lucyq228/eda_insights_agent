# Architecture

## Three layers

1. **Three logical roles.** The Coordinator is the main Cursor chat following
   `run-insights-project/SKILL.md`. Two Markdown specialists in `.cursor/agents/`
   own scope/feasibility and review/insights. They decide and explain; they never
   compute statistics.
2. **Skills (scripts).** Each agent task is a skill with small CLI scripts that
   validate inputs, call the shelf, and save artifacts. Every script prints JSON
   with `ok` and exits non-zero on refusal.
3. **Shelf (`insight_core/` + `tool_registry.yaml`).** Deterministic, typed tools.
   The registry remains broad. The scope is a selective manifest, so only tools
   needed for approved hypotheses run. Feasibility checks the same manifest.

This boundary removes agent hand-offs from profiling, quality checks, preparation,
and planned execution without reducing analytical flexibility. Judgment stays in
the three roles; repeatable computation stays in the pipeline.

## A run is a folder of artifacts

```text
runs/<id>/
  run.json              dataset path, SHA-256, the user's request
  profile.json          deterministic, before scoping
  answers.json          what the user said (coordinator)
  scope_proposal.json   scope/feasibility specialist, versioned
  feasibility_auto.json saved deterministic check for the current proposal
  feasibility.json      specialist judgment, carries the scope's SHA-256
  approved_scope.json   locked; scope.lock.json holds its SHA-256 and the data's
  data_quality.json     deterministic; reuses feasibility leakage screen
  prepared_data.json    deterministic (+ datasets/prepared.parquet)
  step_waivers.json     explicit user-approved skipped steps, if any
  results/*.json        deterministic, one per selected step or follow-up (+ CSV tables)
  analyses_index.json   plan coverage, follow-ups, multiple testing
  cache/associations.json repeated association results for this prepared dataset
  review.json           reviewer verdicts (open while follow-ups are pending)
  insights.json         reviewer
  report.md / .html     reviewer
  live_run.log          human-readable timeline (scripts + hooks)
```

## Staleness

Each downstream artifact stores the SHA-256 of the artifact it was built from.
If the upstream changes, `run_status.py` reports the downstream one as **stale**,
and the next step is to redo it:

```text
scope_proposal -> feasibility        approved_scope -> data_quality, prepared_data
prepared_data -> analyses_index -> review -> insights -> report
```

Examples: a scope revision invalidates the saved feasibility check, so approval is
refused until the specialist rechecks; a follow-up changes the index, so review is redone.

## Gates

| Gate | Enforced by |
|---|---|
| Scope is valid (target exists, binary has a positive class, tools exist) | `save_scope.py` |
| Feasibility auto-check runs once per scope version; judgment can only be stricter | `check_feasibility.py`, `save_feasibility.py` |
| No approval with stale feasibility, blocked steps, leakage drivers, or unanswered questions | `approve_scope.py` |
| Panel data needs a decision: `entity_column` plus a panel tool, or a `panel_reason` | `feasibility.panel_issues` (scope issue) |
| No analysis without a locked, untampered scope and unchanged data file | every downstream script |
| Every tool call re-checked against the scope; follow-ups need a reason | `runner.execute` |
| Concurrent duplicate milestones are refused; completed milestones are reused | `.locks/`, milestone checks |
| A skipped planned step needs the user's quoted confirmation and remains visible | `skip_step.py`, `step_waivers.json` |
| Verdicts and insights cite existing findings; causal wording refused | `save_review.py`, `save_insights.py` |

## Performance policy

- Broad leakage/ranking screens use point estimates only.
- Vectorized eta replaces repeated Python scans over category levels.
- Report-grade intervals are computed only for selected results and cached.
- High-cardinality deep dives show the 10 most frequent levels plus `Other`;
  frequency selection occurs without looking at the target.
- `advance_run.py` runs quality, preparation, and the approved analysis manifest
  directly, so no agent rereads a playbook merely to launch a deterministic script.
