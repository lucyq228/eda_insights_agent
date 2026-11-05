"""Evidence-backed presentation of a reviewed run; never modify analytical reports."""
from __future__ import annotations

import base64
import html
import io
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .state import read_artifact, sha, write_artifact

RATE = "rate-change-decomposition"
COUNT = "count-change-contribution"
E = html.escape


def evidence_files(run_dir: Path) -> dict:
    """Bind the presentation to its checkpoint and exact saved aggregate evidence."""
    names = ["approved_scope.json", "prepared_data.json", "analyses_index.json", "review.json",
             "insights.json", "report.json", "report.html", "report.md"]
    paths = [run_dir / n for n in names]
    paths += sorted((run_dir / "results").glob("*.json"))
    paths += sorted((run_dir / "results").glob("*.csv"))
    return {p.relative_to(run_dir).as_posix(): sha(p) for p in paths}


def checked_path(run_dir: Path, relative: str, parent: str = "results") -> Path:
    path = (run_dir / parent / relative).resolve()
    if not path.is_relative_to((run_dir / parent).resolve()) or not path.is_file():
        raise ValueError(f"missing or unsafe evidence file: {relative}")
    return path


def source(run_dir: Path, label: str) -> dict:
    r = json.loads(checked_path(run_dir, label + ".json").read_text(encoding="utf-8"))
    if r.get("error"):
        raise ValueError(f"{label}: result failed")
    return r


def read_table(run_dir: Path, result: dict, name: str) -> pd.DataFrame:
    meta = result.get("tables", {}).get(name)
    if not meta:
        raise ValueError(f"missing aggregate table: {name}")
    # Read the complete saved table, never the bounded JSON preview.
    return pd.read_csv(checked_path(run_dir, meta["file"]))


def change_table(run_dir: Path, result: dict) -> tuple[pd.DataFrame, list[str], float, float]:
    """One complete calculation table drives both charts and displayed attributions."""
    t = read_table(run_dir, result, "groups")
    groups = list(result.get("grouping_columns", {})) or ["group"]
    if result["tool"] == RATE:
        c = read_table(run_dir, result, "cohorts").set_index("role")
        a, b = c.loc["baseline"], c.loc["comparison"]
        for role, row in (("baseline", a), ("comparison", b)):
            if row["n"] <= 0 or not math.isclose(t[f"{role}_n"].sum(), row["n"]):
                raise ValueError("rate denominators do not reconcile")
            if not math.isclose(t[f"{role}_events"].sum(), row["events"]):
                raise ValueError("rate event counts do not reconcile")
            if not np.allclose(t[f"{role}_share"], t[f"{role}_n"] / row["n"]):
                raise ValueError("saved shares do not match denominators")
            rates = t[f"{role}_events"] / t[f"{role}_n"].replace(0, np.nan)
            if not np.allclose(t[f"{role}_rate"], rates, equal_nan=True):
                raise ValueError("saved rates do not match events / eligible counts")
        mix = 100 * (t.comparison_share - t.baseline_share) * t.baseline_rate
        within = 100 * (t.comparison_events - t.expected_events) / b["n"]
        expected = (t.comparison_n * t.baseline_rate).where(t.comparison_n > 0, 0)
        if not np.allclose(t.expected_events, expected, equal_nan=True):
            raise ValueError("expected events do not match baseline reference rates")
        if not np.allclose(t.mix_pp, mix, equal_nan=True) or not np.allclose(t.within_pp, within, equal_nan=True):
            raise ValueError("saved rate contributions do not match their formulas")
        t["volume_change"] = t.comparison_n - t.baseline_n
        t["rate_change_pp"] = 100 * (t.comparison_rate - t.baseline_rate)
        t["share_change_pp"] = 100 * (t.comparison_share - t.baseline_share)
        t["total_pp"] = t.mix_pp + t.within_pp
        start, end = 100 * a["events"] / a["n"], 100 * b["events"] / b["n"]
        if t.expected_events.notna().all() and not math.isclose(t.total_pp.sum(), end-start, abs_tol=1e-8):
            raise ValueError("rate contributions do not reconcile")
    else:
        if not np.allclose(t.contribution, t.observed-t.expected):
            raise ValueError("count contributions do not reconcile")
        start, end = t.expected.sum(), t.observed.sum()
        metrics = {f["metric"]: f.get("estimate") for f in result["findings"]}
        for key, value in (("expected_count", start), ("observed_count", end), ("net_change", end-start)):
            if not math.isclose(metrics[key], value, abs_tol=1e-8):
                raise ValueError("count table does not match result totals")
    t["segment"] = t[groups].fillna("Missing").astype(str).agg(" · ".join, axis=1)
    return t, groups, float(start), float(end)


def mask(table: pd.DataFrame, where: dict) -> pd.Series:
    if not isinstance(where, dict) or not where:
        raise ValueError("highlight/component where must contain group labels")
    out = pd.Series(True, index=table.index)
    for col, value in where.items():
        if col not in table:
            raise ValueError(f"unknown grouping column: {col}")
        out &= table[col].isna() if value is None else table[col].astype(str).eq(str(value))
    if not out.any():
        raise ValueError(f"group selection matches no rows: {where}")
    return out


def table_html(table: pd.DataFrame, highlights: list[dict], labels: dict | None = None) -> str:
    marked = pd.Series(False, index=table.index)
    for where in highlights:
        marked |= mask(table, where)
    labels = labels or {}
    def fmt(v):
        if pd.isna(v):
            return "Undefined"
        if isinstance(v, (float, np.floating)):
            return f"{v:,.3f}".rstrip("0").rstrip(".")
        return str(v)
    head = "".join(f"<th>{E(labels.get(c, c.replace('_', ' ')))}</th>" for c in table)
    rows = []
    for i, row in table.iterrows():
        cells = "".join(f"<td>{E(fmt(v))}</td>" for v in row)
        rows.append(f'<tr class="{ "highlight" if marked[i] else ""}">{cells}</tr>')
    return '<div class="table-scroll"><table><thead><tr>'+head+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'


def chart_html(table: pd.DataFrame, spec: dict, highlights: list[dict]) -> str:
    """Use column references only: no manually authored chart values or hidden top-N."""
    x, ys = spec["x"], spec["y"]
    kind = spec.get("kind", "bar")
    if kind not in ("bar", "line") or not isinstance(ys, list) or not ys:
        raise ValueError("chart needs kind bar/line and a nonempty y column list")
    if x not in table or any(c not in table for c in ys):
        raise ValueError("chart columns must exist in the referenced table")
    values = table[ys].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("chart contains undefined values; use a table and explain the gap")
    if not spec.get("title") or not spec.get("unit"):
        raise ValueError("chart needs an informative title and unit")
    marked = pd.Series(False, index=table.index)
    for where in highlights:
        marked |= mask(table, where)
    fig, ax = plt.subplots(figsize=(10, max(3, .32*len(table)+1)))
    positions = np.arange(len(table))
    palette = ["#8199ad", "#087f8c", "#bc640a"]
    names = spec.get("labels", {})
    for i, c in enumerate(ys):
        if kind == "bar":
            width = .8/len(ys)
            bars = ax.barh(positions+(i-(len(ys)-1)/2)*width, values[c], height=width,
                           label=names.get(c, c.replace('_', ' ')), color=palette[i % 3])
            for bar, hit in zip(bars, marked):
                bar.set_alpha(1 if hit or not marked.any() else .4)
        else:
            ax.plot(positions, values[c], marker="o", color=palette[i % 3], label=names.get(c, c))
    if kind == "bar":
        ax.set_yticks(positions, table[x].astype(str)); ax.invert_yaxis(); ax.set_xlabel(spec["unit"])
    else:
        ax.set_xticks(positions, table[x].astype(str), rotation=30, ha="right"); ax.set_ylabel(spec["unit"])
    ax.set_title(spec["title"], loc="left", pad=25)
    if len(ys)>1:
        legend = ax.legend(loc="lower left", bbox_to_anchor=(0,1), ncol=min(3,len(ys)), frameon=False)
        for handle in legend.legend_handles:
            handle.set_alpha(1)
    ax.spines[["top", "right"]].set_visible(False)
    return figure_html(fig, spec["title"])


def figure_html(fig, title: str) -> str:
    fig.tight_layout()
    stream = io.BytesIO(); fig.savefig(stream, format="png", dpi=140, bbox_inches="tight"); plt.close(fig)
    return f'<img class="chart" alt="{E(title)}" src="data:image/png;base64,{base64.b64encode(stream.getvalue()).decode()}">'


def bridge(run_dir: Path, spec: dict) -> str:
    r = source(run_dir, spec["result"])
    if r["tool"] not in (RATE, COUNT):
        raise ValueError("waterfall requires additive rate or count attribution, not associations")
    t, groups, start, end = change_table(run_dir, r)
    metrics = ["mix_pp", "within_pp"] if r["tool"] == RATE else ["contribution"]
    if not np.isfinite(t[metrics].to_numpy()).all():
        raise ValueError("incomplete attribution cannot be shown as a complete waterfall")
    used = {m: pd.Series(False, index=t.index) for m in metrics}
    components = spec.get("components") or [{"label":{"mix_pp":"Mix change", "within_pp":"Within-group rate change", "contribution":"Net contribution"}[m],
                                                     "metric":m, "remaining":True} for m in metrics]
    rows=[]
    for c in components:
        m=c["metric"]
        if m not in metrics:
            raise ValueError("waterfall metric is not additive")
        if c.get("remaining") and "where" in c:
            raise ValueError("use where or remaining, not both")
        if "where" in c and not set(c["where"]).issubset(groups):
            raise ValueError("waterfall selections must use grouping columns")
        selected = ~used[m] if c.get("remaining") else mask(t,c["where"])
        if (selected & used[m]).any():
            raise ValueError("overlapping waterfall components double count contributions")
        used[m] |= selected
        rows.append({"Component":c["label"], "Contribution":float(t.loc[selected,m].sum()),
                     "Calculation":f"Sum {m} for " + ("remaining groups" if c.get("remaining") else str(c["where"]))})
    if not all(v.all() for v in used.values()) or not math.isclose(sum(x["Contribution"] for x in rows),end-start,abs_tol=1e-8):
        raise ValueError("waterfall must cover every contribution exactly once and reconcile")
    fig,ax=plt.subplots(figsize=(10,4));ax.bar(0,start,color="#15334c");running=start
    for i,row in enumerate(rows,1):
        value=row["Contribution"];ax.bar(i,abs(value),bottom=min(running,running+value),color="#087f8c" if value>=0 else "#9aaebb")
        ax.text(i,max(running,running+value),f'{value:+.3f}',ha='center',va='bottom');running+=value
    ax.bar(len(rows)+1,end,color="#15334c")
    suffix = "%" if r["tool"] == RATE else ""
    ax.text(0, start, f"{start:,.3f}{suffix}", ha="center", va="bottom")
    ax.text(len(rows)+1, end, f"{end:,.3f}{suffix}", ha="center", va="bottom")
    period=r.get("params",{}); initial="Expected" if period.get("history") else str(period.get("baseline","Baseline"))
    ax.set_xticks(range(len(rows)+2),[initial]+[x["Component"] for x in rows]+[str(period.get("comparison","Comparison"))],rotation=20,ha="right")
    ax.set_ylabel("Rate (%) · contributions in pp" if r["tool"]==RATE else "Count")
    ax.set_title(f"From {start:,.3f} to {end:,.3f}",loc="left");ax.spines[["top","right"]].set_visible(False)
    formula = ("Mix (pp) = (comparison share − baseline share) × baseline rate × 100. "
               "Within (pp) = comparison share × (comparison rate − baseline rate) × 100. "
               "Equivalently, within (pp) = 100 × (comparison events − expected events) / comparison total eligible. "
               "Expected events = comparison eligible × baseline group rate (zero for a departed group). "
               "Shares and rates in the source are fractions." if r["tool"]==RATE else
               "Contribution = observed − expected. Contribution (pp) = 100 × contribution / total expected. "
               "Share change (pp) = 100 × (observed share − expected share). "
               "Expected is the baseline count, or the approved trend projection.")
    shown = calculation_table(t, r)
    highlights = [c["where"] for c in components if c.get("where")]
    return (figure_html(fig,"Reconciliation of the overall change")+table_html(pd.DataFrame(rows),[])
            +'<details open><summary>Full calculation table · all groups</summary><p>'+E(formula)+'</p>'
            +table_html(shown, highlights, r.get("grouping_columns"))+f'<p class="note">Source: {E(spec["result"])} / groups. '
            'Rounded display; calculations use full precision. Other partitions explain the same total and must not be added.</p></details>')


def calculation_table(t: pd.DataFrame, r: dict) -> pd.DataFrame:
    """Readable, complete baseline/comparison inputs and attributions for every group."""
    groups = list(r.get("grouping_columns", {})) or ["group"]
    out = t[groups].copy()
    def pair(a, b, scale=1, unit="", delta=True):
        def text(row):
            x, y = row[a]*scale, row[b]*scale
            def fmt(v):
                return "Undefined" if pd.isna(v) else f"{v:,.3f}".rstrip("0").rstrip(".")
            change = "Undefined" if pd.isna(x) or pd.isna(y) else f"{y-x:+,.3f}"
            return f"{fmt(x)} → {fmt(y)}{unit}" + (f" (Δ {change})" if delta else "")
        return t.apply(text, axis=1)
    if r["tool"] == RATE:
        out["Eligible units: baseline → comparison (change)"] = pair("baseline_n", "comparison_n")
        out["Events: baseline → comparison"] = pair("baseline_events", "comparison_events", delta=False)
        out["Rate %: baseline → comparison (Δ pp)"] = pair("baseline_rate", "comparison_rate", 100)
        out["Share %: baseline → comparison (Δ pp)"] = pair("baseline_share", "comparison_share", 100)
        out["Mix contribution (pp)"] = t.mix_pp
        out["Within contribution (pp)"] = t.within_pp
        out["Total contribution (pp)"] = t.total_pp
    else:
        out["Expected → observed (change)"] = pair("expected", "observed")
        for c in ("expected_share", "observed_share", "share_change_pp", "group_change_pct", "contribution", "contribution_pp"):
            if c in t:
                out[c.replace("_", " ")+(" (%)" if c.endswith("_share") else "")] = t[c]*(100 if c.endswith("_share") else 1)
    return out


def presentation_table(t: pd.DataFrame, r: dict) -> pd.DataFrame:
    shown=t.copy()
    # Explicit display units; never change contribution magnitudes.
    for c in list(shown):
        if c.endswith(("_share","_rate")) and c != "net_change_share":
            shown[c+"_pct"]=100*shown.pop(c)
    if "segment" in shown:
        shown=shown.drop(columns="segment")
    return shown


def build(run_dir: Path, draft: dict) -> dict:
    from .state import milestone_status
    pending=[r["milestone"] for r in milestone_status(run_dir) if r["milestone"]!="executive_report" and r["status"]!="done"]
    if pending:
        raise ValueError(f"complete the analytical checkpoint first: {pending}")
    inputs=evidence_files(run_dir)
    if any(v is None for v in inputs.values()):
        raise ValueError("checkpoint files are missing")
    if draft.get("checkpoint_sha256") != sha(run_dir/"report.json"):
        raise ValueError("storyline targets a different checkpoint; reread the current report")
    for key in ("title","summary","conclusion"):
        if not isinstance(draft.get(key),str) or not draft[key].strip():
            raise ValueError(f"storyline needs {key}")
    if not isinstance(draft.get("sections"),list) or not draft["sections"]:
        raise ValueError("storyline needs ordered evidence sections")
    insights=read_artifact(run_dir,"insights.json")
    scope=read_artifact(run_dir,"approved_scope.json")
    ids={i["id"] for i in insights.get("insights",[])}
    body=[]
    for i,section in enumerate(draft["sections"],1):
        if not section.get("headline") or not section.get("message"):
            raise ValueError("every section needs a conclusion-led headline and explanation")
        if ids and (not section.get("insight_ids") or not set(section["insight_ids"]).issubset(ids)):
            raise ValueError("each section must reference reviewed insight IDs")
        supported = {e["result"] for ins in insights.get("insights", [])
                     if ins["id"] in section.get("insight_ids", []) for e in ins.get("evidence", [])}
        if ids and section["result"] not in supported:
            raise ValueError("section result must support its referenced reviewed insights")
        r=source(run_dir,section["result"])
        highlights=section.get("highlight",[])
        if r["tool"] in (RATE,COUNT):
            t,_,_,_=change_table(run_dir,r)
            display=presentation_table(t,r)
            formula=("Mix (pp) = change in portfolio share (%) × baseline group rate (%) ÷ 100. "
                     "Within (pp) = comparison portfolio share (%) × group rate change (pp) ÷ 100."
                     if r["tool"]==RATE else "Contribution = observed − expected. Share change and contribution_pp are different measures.")
        else:
            t=read_table(run_dir,r,section["table"]);display=t;formula=""
        columns = section.get("columns")
        if columns:
            if not isinstance(columns, dict) or not set(columns).issubset(display.columns):
                raise ValueError("columns must map saved/display column names to readable labels")
            groups = list(r.get("grouping_columns", {})) or (["group"] if "group" in display else [])
            if not set(groups).issubset(columns):
                raise ValueError("keep every grouping label in the comparison table")
            display_table = display[list(columns)]
        else:
            display_table = calculation_table(t,r) if r["tool"] in (RATE,COUNT) else display
        content=table_html(display_table,highlights,columns or r.get("grouping_columns"))
        charts=section.get("charts",[])
        if not charts and not section.get("chart_omission_reason"):
            raise ValueError("each section needs a supporting chart or a reason a table is sufficient")
        for c in charts:
            content+=chart_html(t.assign(**{col: display[col] for col in display if col not in t}),c,highlights)
        if formula:content+='<p class="formula">'+E(formula)+'</p>'
        # Preserve evidence-specific limits next to the claim, not only in a distant appendix.
        caveats=list(r.get("flags",[]))
        caveats += [c for ins in insights.get("insights",[]) if ins["id"] in section.get("insight_ids",[]) for c in ins.get("caveats",[])]
        content+=''.join('<p class="note">'+E(c)+'</p>' for c in dict.fromkeys(caveats))
        body.append(f'<section><span class="step">{i:02d}</span><h2>{E(section["headline"])}</h2><p>{E(section["message"])}</p>'+content+
                    f'<p class="note">Source: {E(section["result"])} · {E(r["tool"])} · '+E(str(r.get("params",{})))+'</p>'+
                    ('<p class="bridge">'+E(section['next_question'])+'</p>' if section.get('next_question') else '')+'</section>')
    if draft.get("recap") and draft["recap"]["result"] not in {s["result"] for s in draft["sections"]}:
        raise ValueError("recap must reconcile evidence explained in the story")
    recap=bridge(run_dir,draft["recap"]) if draft.get("recap") else ''
    if not recap:
        # Associations are not additive: summarize reviewed conclusions without inventing a waterfall.
        recap=table_html(pd.DataFrame([{"Finding":s["headline"],"Evidence":s["result"]} for s in draft["sections"]]),[])
    def detail(value):
        return E('; '.join(map(str, value)) if isinstance(value, list) else str(value))
    actions=''.join('<li><b>'+E(r['action'])+'</b><p>'+E(r['rationale'])+'</p><p>Validation: '+detail(r['validation_plan'])+
                    '</p><details><summary>Success measure, assumptions and risks</summary>'+''.join(
                        '<p><b>'+E(k.replace('_',' ').capitalize())+':</b> '+detail(r.get(k,''))+'</p>'
                        for k in ('success_metric','assumptions','risks','evidence_type'))+'</details></li>'
                    for r in insights.get('recommendations',[]))
    if not actions: actions=''.join('<li>'+E(x)+'</li>' for x in insights.get('next_steps',[]))
    limits=''.join('<li>'+E(x)+'</li>' for x in insights.get('limitations',[]))
    output='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+E(draft['title'])+'''</title><style>
body{font:16px/1.6 Arial,sans-serif;color:#193247;background:#eef3f6;margin:0}main{max-width:1180px;margin:auto;background:white}header{background:#15334c;color:white;padding:40px}h1{font-size:34px;line-height:1.2}h2{font-size:25px;line-height:1.3}section{padding:30px 40px;border-bottom:1px solid #dce5ec}.step,.bridge{color:#087f8c;font-weight:bold}.chart{max-width:100%;height:auto;display:block;margin:20px auto}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}th,td{text-align:right;padding:10px;border-bottom:1px solid #dce5ec;white-space:nowrap}th{background:#eaf0f4}td:first-child,th:first-child{text-align:left}.highlight{background:#e6f5f3;font-weight:bold}.note{font-size:13px;color:#526b7c}.formula,details{padding:16px;background:#f4f7f9;margin-top:18px}summary{cursor:pointer;font-weight:bold}header a{color:#d5f4ff}a{color:#087f8c}@media(max-width:700px){header,section{padding:22px}h1{font-size:28px}}@media print{body{background:white}.chart{break-inside:avoid}h2{break-after:avoid}.table-scroll{overflow:visible}td,th{white-space:normal;font-size:9px;padding:5px}}
</style></head><body><main><header><h1>'''+E(draft['title'])+'</h1><p>'+E(draft['summary'])+'</p><p><a href="report.html">Original analytical report: hypotheses, findings and tools</a> · <a href="report.md">Markdown reference</a></p></header><section><p><b>Metric:</b> '+E(scope['target']['definition'])+' <b>Grain:</b> '+E(scope['unit_of_analysis'])+'</p></section>'+''.join(body)+'<section><h2>What to take away</h2><p>'+E(draft['conclusion'])+'</p>'+recap+'<h3>Recommended next steps</h3><ul>'+actions+'</ul><h3>What limits the conclusion</h3><ul>'+limits+'</ul><p class="note">Figures use saved aggregate evidence. Descriptive attribution and associations do not establish causal effects. Undefined values are not zero. The original analytical report remains the reference checkpoint.</p></section></main></body></html>'
    if evidence_files(run_dir)!=inputs:
        raise ValueError("evidence changed during rendering; review the updated checkpoint")
    (run_dir/'executive_report.html').write_text(output,encoding='utf-8')
    write_artifact(run_dir,'executive_story.json',draft)
    record={"files":["report.html","report.md","executive_report.html"],"sources":inputs,
            "story_sha256":sha(run_dir/'executive_story.json'),"html_sha256":sha(run_dir/'executive_report.html')}
    write_artifact(run_dir,'executive_report.json',record,upstream='report.json')
    return record
