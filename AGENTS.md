# Cursor agents: general correlation and insights

Bring any table (CSV, TSV, XLSX, Parquet) and ask "what insights are in here?" or
"what correlates with X?". A team of Cursor agents asks what outcome you care
about and why, proposes a testable plan, checks it against the data, and only
after you approve runs it, challenges it, and writes a short report.

There is no orchestrator program. Agents are Markdown files; every calculation
is a deterministic script packaged as a skill.

## The team

| Agent | Where it lives | Model | Owns |
|---|---|---|---|
| A1 Routing Manager | Main chat, following `.cursor/skills/run-insights-project/SKILL.md` | the chat's model | user dialogue, approval, routing |
| A2 Scope | `.cursor/agents/a2-scope.md` | grok-4.7-high-fast | `scope_proposal.json` |
| A3 Feasibility | `.cursor/agents/a3-feasibility.md` | grok-4.7-high-fast | `feasibility.json` |
| A4 Data Quality & EDA | `.cursor/agents/a4-data-quality-eda.md` | composer-2.5 | `profile.json`, `data_quality.json` |
| A5 Data Prep | `.cursor/agents/a5-data-prep.md` | composer-2.5 | `prepared_data.json` |
| A6 Analysis | `.cursor/agents/a6-analysis.md` | composer-2.5 | `results/`, `analyses_index.json` |
| A7 Review & Insights | `.cursor/agents/a7-review-insights.md` | grok-4.7-high-fast | `review.json`, `insights.json`, `report.html` |

The shared tools (the shelf) are 17 tools in `tool_registry.yaml`, implemented in
`insight_core/`. Agents pick analysis tools from the registry. For panel data (the
same stores, restaurants, markets, or customers observed over time) the scope sets
`entity_column` and adds `panel-decomposition` / `panel-drivers`, which split each
association into within-entity and between-entity parts.

## Lifecycle (never skip a step)

```text
start -> A4 profile -> manager asks target + purpose -> A2 scope -> A3 feasibility
 -> user loop (answers, revisions) -> user approves -> lock scope
 -> A4 data quality -> A5 prepare -> A6 analyses
 -> A7 review (may request reruns) -> A7 insights -> A7 report -> finalize
```

Subagents cannot talk to the user. They return questions to the manager, who
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
- `.cursor/skills/`: the manager playbook and one skill per agent task.
- `examples/example_scope.json`: a complete approved-quality scope for the store data.
- `runs/<run-id>/`: every artifact, charts, `report.html`, and `live_run.log`.
