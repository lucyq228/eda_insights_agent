# Insights agents: correlation analysis on any table, scoped with you

A demo of a small Cursor agent team that turns "can you find insights in this
data?" into a reviewed, honest report. It works on any tabular file, and the
user stays in charge of what gets analysed.

## Why scoping first

Most "find me insights" requests fail in one of four ways: no clear outcome,
testing every column until something looks significant, reading correlations as
causes, or columns that quietly leak the answer. The agents are built around
those failure modes:

- the manager asks **what outcome matters and what decision it informs** before any analysis;
- hypotheses are written and approved **before** results exist, and every test joins one
  **multiple-testing** family (Benjamini-Hochberg);
- feasibility **blocks leakage** (columns derived from the target) and under-powered cuts;
- review checks **Simpson's paradox**, curves hidden by weak correlations, and overlapping drivers;
- the save scripts **refuse causal wording**.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\make_sample_data.py      # two demo datasets
.venv\Scripts\python.exe -m pytest tests -q              # full flow on both
```

Then open this folder in Cursor and say, for example:

> Use /run-insights-project on `data/store_weekly_sales.csv`. Can you help me find what moves with sales?

or bring your own file:

> Use /run-insights-project on `C:\path\to\my_data.xlsx`. What correlates with churn?

The manager profiles the file, asks you for the target and purpose, shows you a
plan with feasibility verdicts, waits for your yes, then runs everything and
returns `runs/<run>/report.html`.

## The team

| Step | Agent | What it does |
|---|---|---|
| route | A1 Manager (main chat) | talks to you, asks the questions, approves only on your yes |
| profile | A4 Data Quality & EDA | column types, missingness, candidate targets, flags |
| scope | A2 Scope | target, purpose, exclusions, 3-6 hypotheses with tool pathways |
| feasibility | A3 Feasibility | can the data answer each step? leakage, power, dates, segments |
| quality | A4 | duplicates, key uniqueness, target balance, outliers, leakage |
| prepare | A5 Data Prep | one clean analysis table |
| analyse | A6 Analysis | runs the approved plan; reruns as recorded follow-ups |
| review + report | A7 Review & Insights | verdicts, reruns, 2-7 insights, HTML report |

## The tool shelf (`tool_registry.yaml`)

| Tool | Answers |
|---|---|
| profile-dataset, data-quality-check, eda-overview | what is in the table; is it fit for the scope |
| prepare-dataset | the analysis table |
| target-associations | which drivers move with the target, ranked, with CI |
| correlation-matrix | which drivers overlap each other |
| pair-deep-dive | the shape of one relationship |
| segment-breakdown | does the target differ by segment |
| segment-correlation | does an association hold within segments (Simpson's paradox) |
| partial-correlation | does it survive holding other columns fixed |
| nonlinearity-check | is it curved or threshold-like |
| time-trend | trend over time and lagged driver correlation |
| driver-importance | joint predictive importance and adjusted coefficients |
| panel-decomposition | panel data: pooled vs within-entity vs between-entity association for one driver |
| panel-drivers | panel data: which drivers move with the target within entities over time, and between them |
| multiple-testing | q-values across every test (automatic) |
| build-report | Markdown + self-contained HTML report |

Measures adapt to column types: Spearman r for numeric drivers (a binary target is
coded 1/0), eta for categorical drivers, Cramer's V or eta for a categorical target.

## Demo datasets

- `data/store_weekly_sales.csv`: 80 stores x 26 weeks, target `weekly_sales_k`.
  Planted: a strong traffic association, promo spend that looks negative pooled but is
  positive within every region, an inverted-U for price, a negative stockout
  association, staffing that matters mostly in malls, a null (temperature), a leakage
  column, duplicates, and missing ratings.
- `data/employee_attrition.csv`: 1,600 employees, binary target `left_company`.
  Planted: engagement (protective), overtime (risk), early-tenure risk, a null
  (remote), and a leakage column (`exit_interview_done`).

The planted truth lives in `synthetic/`, which the agents never open.

## Layout

```text
.cursor/agents/      A2-A7 subagents          .cursor/skills/   manager playbook + one skill per task
.cursor/rules/       guardrails (always on)   .cursor/hooks/    run log for subagent activity
insight_core/        shared Python            tool_registry.yaml  the shelf
data/ examples/ scripts/ tests/               runs/             one folder per run (gitignored)
```

See `docs/architecture.md` for how artifacts, staleness, and the lock fit together.
