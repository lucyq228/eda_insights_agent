---
name: insight-shelf
description: Execute registered calculations and read bounded aggregate evidence for an active investigation.
---
Use list_tools.py, run_plan.py, run_tool.py --tool <id> --params-file <json>
--followup-reason <reason>, and read_evidence.py --table <name> --offset 0 --limit 50.
Routine exploratory follow-ups within the active scope do not need repeated user approval.
Use business-summary for single or intersecting dimensions, temporal-diagnostics for period
metrics, period-comparison for exact accounting differences, and view: <name> with statistical
tools to analyze approved aggregate views. Preserve explicit units and denominators.
Do not treat descriptive accounting as causal attribution. Use the original statistical
shelf when the question requires inference; respect sample-size, dependence and rank warnings.
