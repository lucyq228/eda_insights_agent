# Business insights: three agents and a shared calculation library

The three logical agents are scoping (`a1-scope-feasibility`), analyst (`a2-analyst`,
the main chat), and independent reviewer (`a3-review-insights`). Shared calculations
live in insight_core/ and are exposed through tool_registry.yaml and CLI skills.

Lifecycle: request -> profile -> scope + feasibility -> activate -> analyst investigation
-> independent review / targeted follow-ups -> evidence-backed report.

- Broad EDA uses exploratory mode. A clear user request authorizes routine read-only
  exploration; no repeated approval or fixed hypothesis/insight counts.
- Confirmatory mode retains explicit approval. Material new objectives, datasets,
  external actions or excluded data require a scope decision. Never fabricate consent.
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

New reports use schema v2 and `.cursor/skills/business-reporting/SKILL.md`. Keep exactly three
agents. Analysts propose actions; reviewers judge their usefulness and evidence, then produce a
decision-first report. No fixed action count, invented lift, or forced business recommendation.
