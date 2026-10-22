# Cursor agents: general correlation and insights

Bring any table (CSV, TSV, XLSX, Parquet) and ask "what insights are in here?" or
"what correlates with X?". A team of Cursor agents asks what outcome you care
about and why, proposes a testable plan, checks it against the data, and only
after you approve runs it, challenges it, and writes a short report.

Cursor is the host. Three logical roles make decisions; every calculation and
pipeline transition is a deterministic script packaged as a skill.

## The team

| Role | Where it lives | Owns |
|---|---|---|
| Coordinator | Main Cursor chat using `.cursor/skills/run-insights-project/SKILL.md` | user dialogue, approval, deterministic execution |
| Scope & Feasibility specialist | `.cursor/agents/a2-scope-feasibility.md` | `scope_proposal.json`, `feasibility.json` |
| Reviewer & Insights specialist | `.cursor/agents/a3-review-insights.md` | `review.json`, `insights.json`, `report.html` |

The shared tools (the shelf) remain in `tool_registry.yaml`, implemented in
`insight_core/`. The scope specialist selects only the tools needed by the approved
hypotheses; the deterministic runner does not run the whole shelf. For panel data (the
same stores, restaurants, markets, or customers observed over time) the scope sets
`entity_column` and adds `panel-decomposition` / `panel-drivers`, which split each
association into within-entity and between-entity parts.

## Lifecycle (never skip a step)

```text
start -> deterministic profile -> coordinator asks target + purpose
 -> scope/feasibility specialist -> user loop -> user approves -> lock scope
 -> deterministic quality + preparation + selected analysis plan
 -> reviewer/insights specialist (may request targeted follow-ups) -> report -> finalize
```

Specialists cannot talk to the user. They return questions to the coordinator, who
asks and records the answers.

## Non-negotiable rules

- **The user owns the scope.** Approval only on their explicit yes. The approved
  scope is locked (SHA-256 in `scope.lock.json`); a different scope is a new run.
- **Calculations come only from the skill scripts.** No ad-hoc code; report tool gaps.
- **Never hand-edit run artifacts.** Agents write drafts in `runs/<run>/drafts/`.
- **No raw rows in the conversation; never open `synthetic/`.**
- **Associations, not causes.** Quote estimates with n and CI.

## Running scripts

From the project root:

```powershell
.venv\Scripts\python.exe .cursor\skills\<skill>\scripts\<script>.py [--run <run-id>]
```

`--run` defaults to `runs/CURRENT`. Every script prints JSON with `ok` and exits
non-zero when it refuses or fails. Pass structured input as files (`--file`,
`--params-file`, `--answers-file`), not inline JSON: PowerShell strips the quotes.

## Where things are

- `data/`: two demo datasets (store weekly sales, employee attrition). Your own files can live anywhere.
- `insight_core/`: shared Python (data profiling, stats, tools, scope lock, run state, report).
- `tool_registry.yaml`: what each tool answers, what it needs, its caveats.
- `.cursor/skills/`: the coordinator playbook and deterministic task skills.
- `examples/example_scope.json`: a complete approved-quality scope for the store data.
- `runs/<run-id>/`: every artifact, charts, `report.html`, and `live_run.log`.
