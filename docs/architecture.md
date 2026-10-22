# Architecture

## Three layers

1. **Agents (Markdown).** The manager is the main chat following
   `run-insights-project/SKILL.md`; A2-A7 are subagents in `.cursor/agents/`. They
   decide and explain. They never compute.
2. **Skills (scripts).** Each agent task is a skill with small CLI scripts that
   validate inputs, call the shelf, and save artifacts. Every script prints JSON
   with `ok` and exits non-zero on refusal.
3. **Shelf (`insight_core/` + `tool_registry.yaml`).** Deterministic, typed tools.
   The registry is what agents read to choose tools and what feasibility checks.

## A run is a folder of artifacts

```text
runs/<id>/
  run.json              dataset path, SHA-256, the user's request
  profile.json          A4, before scoping
  answers.json          what the user said (manager)
  scope_proposal.json   A2, versioned
  feasibility.json      A3, carries the scope's SHA-256
  approved_scope.json   locked; scope.lock.json holds its SHA-256 and the data's
  data_quality.json     A4
  prepared_data.json    A5 (+ datasets/prepared.parquet)
  results/*.json        A6, one per step or follow-up (+ CSV tables)
  analyses_index.json   plan coverage, follow-ups, multiple testing
  review.json           A7 verdicts (open while reruns are pending)
  insights.json         A7
  report.md / .html     A7
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

Examples: a scope revision invalidates feasibility, so approval is refused until A3
rechecks; a follow-up analysis changes the index, so the review must be redone.

## Gates

| Gate | Enforced by |
|---|---|
| Scope is valid (target exists, binary has a positive class, tools exist) | `save_scope.py` |
| Feasibility verdicts can only be made stricter by A3 | `save_feasibility.py` |
| No approval with stale feasibility, blocked steps, leakage drivers, or unanswered questions | `approve_scope.py` |
| Panel data needs a decision: `entity_column` plus a panel tool, or a `panel_reason` | `feasibility.panel_issues` (scope issue) |
| No analysis without a locked, untampered scope and unchanged data file | every A4-A7 script |
| Every tool call re-checked against the scope; follow-ups need a reason | `runner.execute` |
| Verdicts and insights cite existing findings; causal wording refused | `save_review.py`, `save_insights.py` |
