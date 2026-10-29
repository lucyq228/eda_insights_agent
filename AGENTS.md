# Business insights: three agents and a shared calculation library

The three logical agents are scoping (`a1-scope-feasibility`), analyst (`a2-analyst`,
the main chat), and independent reviewer (`a3-review-insights`). Shared calculations
live in insight_core/ and are exposed through tool_registry.yaml and CLI skills.

Lifecycle: request -> profile -> scope + feasibility -> activate -> analyst investigation
-> independent review / targeted follow-ups -> evidence-backed report.

- Broad EDA uses exploratory mode. Present a sequential scope table, guide the user with
  recommended defaults, and obtain confirmation once before substantive analysis in either mode.
- Routine follow-ups inside the confirmed boundaries need reasons, not repeated approval.
  New objectives, datasets, populations or excluded factors need a new scoped run. Never fabricate consent.
- Scope snapshots remain immutable and hashed. Declared views and reasoned follow-ups
  permit adaptation without silently changing the objective. A genuinely new scope is a new run.
- Preserve the clean base table, original categories, IDs and metric components.
- Calculations use the shared library. Missing capability is a tool gap, not invented evidence.
- Aggregate tables are available through read_evidence.py; raw personal rows are not
  printed. Never inspect synthetic/ (evaluation answers).
- Keep observational, descriptive, predictive and causal evidence distinct. No guaranteed
  improvement from a correlation. All proposed actions need a validation plan and risks.
- Artifact writes go through scripts; prompts/drafts are agent-authored inputs.

Use `.venv/Scripts/python.exe` on Windows or `python` on Linux with
`.cursor/skills/<skill>/scripts/<script>.py`. See docs/architecture.md and examples/qvi_scope.json.
