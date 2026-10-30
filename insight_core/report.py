"""Build the insight report (Markdown + self-contained HTML) from saved artifacts."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from . import registry
from .state import read_artifact


def _results(run_dir: Path) -> dict:
    return {json.loads(p.read_text(encoding="utf-8"))["label"]: json.loads(p.read_text(encoding="utf-8"))
            for p in (run_dir / "results").glob("*.json")}


def _qmap(results: dict) -> dict:
    mt = (results.get("multiple-testing-adjustment") or results.get("multiple-testing") or {})
    return {(r["result"], r["label"]): r["q"] for r in mt.get("q_values", [])}


def _fmt(v, digits=3):
    return "n/a" if v is None else f"{v:.{digits}g}" if isinstance(v, float) else str(v)


def evidence_line(f: dict, q) -> str:
    if f.get("evidence_type") == "descriptive":
        return f"{f['label']}: {_fmt(f.get('estimate'))}; observed n = {f.get('n')}; descriptive (no significance test)"
    ci = f"[{_fmt(f.get('ci_low'))}, {_fmt(f.get('ci_high'))}]" if f.get("ci_low") is not None else "(no CI)"
    ents = f", entities = {f['n_entities']}" if f.get("n_entities") and f.get("n_entities") != f.get("n") else ""
    return f"{f['label']}: {f['metric']} = {_fmt(f.get('estimate'))} {ci}, n = {f.get('n')}{ents}, q = {_fmt(q)}"


def panel_line(scope: dict) -> str | None:
    ent = scope.get("entity_column")
    if not ent:
        return None
    return (f"Panel data: each {ent} is observed repeatedly. Within-{ent} estimates compare the same {ent} over time; "
            f"between-{ent} estimates compare {ent} averages (n = number of entities). CIs from panel tools are "
            f"clustered by {ent}.")


def supporting_tools(insight: dict, results: dict) -> list[str]:
    """Unique canonical tool names from this insight's cited, valid evidence only."""
    names = []
    for evidence in insight.get("evidence", []):
        result = results.get(evidence.get("result"), {})
        if result.get("error") or not result.get("tool"):
            continue
        if evidence.get("finding") and not any(
                f.get("label") == evidence["finding"] for f in result.get("findings", [])):
            continue
        tool, _ = registry.resolve_call(result["tool"], result.get("params", {}), {})
        # Legacy categorical deep dives used group profiles, before canonical routing.
        if result["tool"] == "pair-deep-dive" and any(
                f.get("metric") == "cramers_v" or
                (f.get("metric") == "eta" and str(f.get("direction", "")).startswith("highest in "))
                for f in result.get("findings", [])):
            tool = "target-by-group"
        if tool not in names:
            names.append(tool)
    return names


def build(run_dir: Path) -> dict:
    scope = read_artifact(run_dir, "approved_scope.json")
    insights = read_artifact(run_dir, "insights.json")
    review = read_artifact(run_dir, "review.json")
    dq = read_artifact(run_dir, "data_quality.json") or {}
    prep = read_artifact(run_dir, "prepared_data.json") or {}
    analyses = read_artifact(run_dir, "analyses_index.json") or {}
    results = _results(run_dir)
    skipped = [s for s in analyses.get("steps", []) if s.get("status") == "skipped"]
    qmap = _qmap(results)

    md = [f"# {scope['project_name']}", "",
          f"**Purpose:** {scope['purpose']}  ", f"**Decision supported:** {scope['decision_supported']}  ",
          f"**Target:** `{scope['target']['column']}` ({scope['target']['type']}) - {scope['target']['definition']}  ",
          f"**Data:** {prep.get('n_rows')} rows after preparation; unit = {scope['unit_of_analysis']}", "",
          "> Descriptive findings and observational associations do not establish causes. Statistical estimates show available n, CI, "
          "and q (Benjamini-Hochberg across recorded tests). Data-selected follow-ups remain exploratory.", ""]
    if panel_line(scope):
        md += [f"> {panel_line(scope)}", ""]
    md += ["## Summary", "", insights["headline_summary"], "", "## Key insights", ""]
    blocks = []
    for ins in insights["insights"]:
        ev_lines, imgs = [], []
        for ev in ins["evidence"]:
            r = results.get(ev["result"], {})
            f = next((x for x in r.get("findings", []) if x["label"] == ev["finding"]), None)
            if f:
                ev_lines.append(evidence_line(f, qmap.get((ev["result"], ev["finding"]))))
            imgs += [c for c in r.get("charts", []) if c and Path(c).exists()][:1]
        imgs = list(dict.fromkeys(imgs))[:2]
        md += [f"### {ins['id']}. {ins['title']}", "", ins["statement"], "",
               f"*Strength:* {ins['strength']} | *Confidence:* {ins['confidence']}", ""]
        tools = supporting_tools(ins, results)
        if tools:
            md += ["*Supporting tools:* " + ", ".join(f"`{tool}`" for tool in tools), ""]
        md += [f"- {e}" for e in ev_lines]
        md += [f"- Caveat: {c}" for c in ins.get("caveats", [])]
        if ins.get("suggested_next_step"):
            md += [f"- Next step: {ins['suggested_next_step']}"]
        md += [f"![{ins['id']}](charts/{Path(i).name})" for i in imgs] + [""]
        blocks.append((ins, ev_lines, imgs))

    md += ["## Proposed business actions", ""]
    for rec in insights.get("recommendations", []):
        md += [f"### {rec['action']}", rec['rationale'],
               f"Evidence: {rec['evidence_type']}", f"Validation: {rec['validation_plan']}",
               f"Success metric: {rec['success_metric']}", f"Assumptions: {rec['assumptions']}",
               f"Risks: {rec['risks']}", ""]
    md += ["## Hypothesis verdicts", "", "| Hypothesis | Verdict | Reasoning |", "|---|---|---|"]
    for v in review["hypothesis_verdicts"]:
        md.append(f"| {v['id']} | {v['verdict']} | {v['reasoning'].replace('|', '/')} |")
    md += ["", "## Limitations", ""] + [f"- {x}" for x in insights.get("limitations", [])]
    md += ["", "## Recommended next steps", ""] + [f"- {x}" for x in insights.get("next_steps", [])]
    md += ["", "## Appendix: how the data was prepared", ""] + [f"- {x}" for x in prep.get("log", [])]
    md += [f"- Data quality: {dq.get('summary', 'n/a')}", "", "## Appendix: analyses run", ""]
    for label, r in sorted(results.items()):
        tag = " (follow-up: " + r["followup_reason"] + ")" if r.get("followup_reason") else ""
        md.append(f"- `{label}` {r['tool']}{tag}: {r.get('summary') or r.get('error')}")
    for step in skipped:
        md.append(f"- `{step['step_id']}` {step['tool']} (user-approved skip): {step.get('skip_reason')}")
    (run_dir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (run_dir / "report.html").write_text(_html(scope, insights, review, blocks, prep, dq, results, skipped), encoding="utf-8")
    return {"files": ["report.md", "report.html"], "n_insights": len(insights["insights"]),
            "n_charts": sum(len(b[2]) for b in blocks)}


def _img(path: str) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="chart">'


def _html(scope, insights, review, blocks, prep, dq, results, skipped) -> str:
    e = html.escape
    cards = []
    for ins, ev_lines, imgs in blocks:
        tool_tags = "".join(f'<span class="tool-tag">tool: {e(tool)}</span>'
                            for tool in supporting_tools(ins, results))
        cards.append(
            f'<section class="card"><h3>{e(ins["id"])}. {e(ins["title"])}</h3><p>{e(ins["statement"])}</p>'
            f'<p class="tags"><span>{e(ins["strength"])}</span><span>confidence: {e(ins["confidence"])}</span>{tool_tags}</p>'
            f'<ul class="ev">{"".join(f"<li>{e(x)}</li>" for x in ev_lines)}</ul>'
            + "".join(f'<p class="caveat">Caveat: {e(c)}</p>' for c in ins.get("caveats", []))
            + (f'<p class="next">Next step: {e(ins["suggested_next_step"])}</p>' if ins.get("suggested_next_step") else "")
            + f'<div class="imgs">{"".join(_img(i) for i in imgs)}</div></section>')
    verdicts = "".join(f"<tr><td>{e(v['id'])}</td><td class='v-{e(v['verdict'])}'>{e(v['verdict'])}</td>"
                       f"<td>{e(v['reasoning'])}</td></tr>" for v in review["hypothesis_verdicts"])
    lims = "".join(f"<li>{e(x)}</li>" for x in insights.get("limitations", []))
    nexts = "".join(f"<li>{e(x)}</li>" for x in insights.get("next_steps", []))
    runs = "".join(f"<li><code>{e(k)}</code> {e(r['tool'])}: {e(str(r.get('summary') or r.get('error')))}</li>"
                   for k, r in sorted(results.items()))
    runs += "".join(f"<li><code>{e(s['step_id'])}</code> {e(s['tool'])} (user-approved skip): "
                    f"{e(str(s.get('skip_reason')))}</li>" for s in skipped)
    actions = "".join(f"<section class='card'><h3>{e(r['action'])}</h3><p>{e(r['rationale'])}</p>"
                      f"<p>Evidence: {e(r['evidence_type'])}</p><p>Validation: {e(r['validation_plan'])}</p>"
                      f"<p>Success metric: {e(r['success_metric'])}</p><p>Assumptions: {e(str(r['assumptions']))}</p>"
                      f"<p>Risks: {e(str(r['risks']))}</p></section>" for r in insights.get("recommendations", []))
    t = scope["target"]
    panel_html = f'<p class="note">{e(panel_line(scope))}</p>' if panel_line(scope) else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(scope['project_name'])}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:980px;margin:32px auto;padding:0 20px;color:#1f2933;line-height:1.5}}
h1{{margin-bottom:4px}} .meta{{color:#52606d}} .note{{background:#f0f4f8;border-left:4px solid #2f6db5;padding:10px 14px}}
.card{{border:1px solid #d9e2ec;border-radius:8px;padding:14px 18px;margin:16px 0}}
.tags{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
.tags span{{overflow-wrap:anywhere;min-width:0;background:#e3ecf7;border-radius:10px;padding:2px 10px;font-size:13px}}
.ev{{font-family:Consolas,monospace;font-size:13px}} .caveat{{color:#8a4b08}} .next{{color:#196c2e}}
.imgs img{{max-width:48%;margin:6px 1% 0 0;border:1px solid #eee}}
table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #d9e2ec;padding:6px 8px;vertical-align:top}}
.v-supported{{color:#196c2e;font-weight:600}} .v-not_supported{{color:#a61b1b;font-weight:600}}
.v-partially_supported,.v-inconclusive,.v-not_evaluated{{color:#8a4b08;font-weight:600}}
</style></head><body>
<h1>{e(scope['project_name'])}</h1>
<p class="meta"><b>Purpose:</b> {e(scope['purpose'])}<br><b>Decision supported:</b> {e(scope['decision_supported'])}<br>
<b>Target:</b> <code>{e(t['column'])}</code> ({e(t['type'])}) - {e(t['definition'])}<br>
<b>Data:</b> {prep.get('n_rows')} rows after preparation; unit = {e(scope['unit_of_analysis'])}</p>
<p class="note">Descriptive findings and observational associations do not establish causes. Statistical estimates show available n, CI, and q
(Benjamini-Hochberg across recorded tests). Data-selected follow-ups remain exploratory.</p>
{panel_html}
<h2>Summary</h2><p>{e(insights['headline_summary'])}</p>
<h2>Key insights</h2>{''.join(cards)}
<h2>Proposed business actions</h2>{actions}<h2>Hypothesis verdicts</h2><table><tr><th>Hypothesis</th><th>Verdict</th><th>Reasoning</th></tr>{verdicts}</table>
<h2>Limitations</h2><ul>{lims}</ul><h2>Recommended next steps</h2><ul>{nexts}</ul>
<h2>Appendix</h2><p>Data quality: {e(str(dq.get('summary', 'n/a')))}</p>
<ul>{''.join(f'<li>{e(x)}</li>' for x in prep.get('log', []))}</ul><h3>Analyses run</h3><ul>{runs}</ul>
</body></html>"""
