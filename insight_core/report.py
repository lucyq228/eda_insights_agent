"""Build the insight report (Markdown + self-contained HTML) from saved artifacts."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from .state import read_artifact


def _results(run_dir: Path) -> dict:
    return {json.loads(p.read_text(encoding="utf-8"))["label"]: json.loads(p.read_text(encoding="utf-8"))
            for p in (run_dir / "results").glob("*.json")}


def _qmap(results: dict) -> dict:
    mt = results.get("multiple-testing", {})
    return {(r["result"], r["label"]): r["q"] for r in mt.get("q_values", [])}


def _fmt(v, digits=3):
    if v is None:
        return "n/a"
    if isinstance(v, (int, float)):
        if v != 0 and abs(v) < .0001:
            return f"{v:.{digits}g}"
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return str(v)


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


def _text(value):
    return '; '.join(str(x) for x in value) if isinstance(value, list) else str(value)


def _evidence(refs, results, qmap):
    lines = []
    for ev in refs:
        r = results.get(ev.get('result'), {})
        f = next((x for x in r.get('findings', []) if x['label'] == ev.get('finding')), None)
        if f:
            lines.append(f"{ev['result']} — {evidence_line(f, qmap.get((ev['result'], ev['finding'])))}")
        else:
            lines.append(f"{ev.get('result')} — {ev.get('finding') or r.get('summary', 'result reference')}")
    return lines


ACTION_MAIN = [('audience', 'Who / where'), ('intervention', 'What to do'),
               ('expected_benefit', 'Expected benefit'),
               ('success_metric', 'Measure success'), ('decision_rule', 'Decision rule'),
               ('proposed_owner', 'Proposed owner')]
ACTION_DETAIL = [('priority_reason', 'Why this priority'), ('dependencies', 'Dependencies'),
                 ('mechanism_hypothesis', 'Hypothesis to validate'), ('benefit_basis', 'Benefit basis'),
                 ('benefit_calculation', 'Benefit calculation / assumptions'),
                 ('implementation_basis', 'Basis for implementation'),
                 ('alternatives_considered', 'Alternatives considered'), ('validation_plan', 'Validation plan'),
                 ('assumptions', 'Assumptions'), ('risks', 'Risks'), ('evidence_type', 'Evidence type')]


def build(run_dir: Path) -> dict:
    from .report_contract import selected_charts
    scope = read_artifact(run_dir, 'approved_scope.json')
    draft = read_artifact(run_dir, 'insights.json')
    review = read_artifact(run_dir, 'review.json')
    prep = read_artifact(run_dir, 'prepared_data.json') or {}
    dq = read_artifact(run_dir, 'data_quality.json') or {}
    analyses = read_artifact(run_dir, 'analyses_index.json') or {}
    results = _results(run_dir)
    qmap = _qmap(results)
    e = lambda value: html.escape(_text(value), quote=True)
    paras = lambda pairs: ''.join(f'<p><b>{e(label)}:</b> {e(value)}</p>' for label, value in pairs if value)
    lis = lambda values: '<ul>' + ''.join(f'<li>{e(v)}</li>' for v in values) + '</ul>'
    details = lambda title, content: f'<details><summary>{e(title)}</summary>{content}</details>'
    md = [f"# {scope['project_name']}", '', '## Executive takeaway', '', draft['headline_summary'], '']
    body = [f"<h1>{e(scope['project_name'])}</h1>", '<section class="executive"><h2>Executive takeaway</h2>',
            f"<p class='lead'>{e(draft['headline_summary'])}</p>"]
    decision = draft.get('decision_requested', scope['decision_supported'])
    md += [f'**Decision requested:** {decision}', '']
    body += [paras([('Decision requested', decision)]), '</section>']
    note = 'Observed patterns inform proposed actions; they do not establish intervention lift.'
    body.append(f'<p class="note">{e(note)}</p>')
    md += [f'> {note}', '', '## Prioritized actions', '']
    body.append('<h2>Prioritized actions</h2>')
    action_appendix = []
    recommendations = draft.get('recommendations', [])
    if not recommendations:
        reason = draft.get('no_recommendations_reason', 'No recommendations were recorded in this legacy report.')
        body.append(f'<p>{e(reason)}</p>'); md += [reason, '']
    for i, rec in enumerate(recommendations, 1):
        heading = f"{i}. {rec['action']}"
        kind = rec.get('action_type', 'proposal')
        main = [(label, rec.get(key)) for key, label in ACTION_MAIN]
        extra = [(label, rec.get(key)) for key, label in ACTION_DETAIL]
        ev = _evidence(rec.get('evidence', []), results, qmap)
        body += [f'<section class="action"><span class="tag">{e(kind)}</span><h3>{e(heading)}</h3>',
                 f"<p>{e(rec['rationale'])}</p>", paras(main),
                 details('Evidence, alternatives and validation', paras(extra) + lis(ev)), '</section>']
        md += [f'### {heading}', '', f'*Action type: {kind}*', '', rec['rationale'], '']
        md += [f'**{label}:** {_text(value)}  ' for label, value in main if value] + ['']
        action_appendix += [f'### Action {i}: evidence and validation', '']
        action_appendix += [f'**{label}:** {_text(value)}  ' for label, value in extra if value]
        action_appendix += [''] + [f'- {x}' for x in ev] + ['']
    uncertainties = draft.get('decision_uncertainties', draft.get('limitations', []))
    if uncertainties:
        body += ['<h2>What could change the decision</h2>', lis(uncertainties)]
        md += ['## What could change the decision', ''] + [f'- {x}' for x in uncertainties] + ['']
    body.append('<h2>Supporting findings</h2>'); md += ['## Supporting findings', '']
    finding_appendix = []
    n_charts = 0
    for ins in draft.get('insights', []):
        brief = ins.get('brief_summary', ins['statement'])
        title = f"{ins['id']}. {ins['title']}"
        full = _evidence(ins['evidence'], results, qmap)
        key = _evidence(ins.get('key_evidence', []), results, qmap)
        charts = selected_charts(ins, results, run_dir)
        n_charts += len(charts)
        meaning = ins.get('business_implication')
        caveat = ins.get('decision_caveat')
        body += [f'<section class="finding"><h3>{e(title)}</h3><p>{e(brief)}</p>',
                 paras([('Why it matters', meaning), ('Decision caveat', caveat)])]
        if key:
            body.append(lis(key))
        md += [f'### {title}', '', brief, '']
        md += [f'**{label}:** {value}' for label, value in [('Why it matters', meaning), ('Decision caveat', caveat)] if value]
        md += [''] + [f'- {x}' for x in key] + ['']
        for path, caption in charts:
            encoded = base64.b64encode(path.read_bytes()).decode()
            body.append(f'<figure><img src="data:image/png;base64,{encoded}" alt="{e(caption)}"><figcaption>{e(caption)}</figcaption></figure>')
            md += [f'![Supporting chart]({path.relative_to(run_dir.resolve()).as_posix()})', '', caption, '']
        evidence_body = paras([('Full explanation', ins['statement']), ('Strength', ins['strength']),
                               ('Confidence', ins['confidence'])]) + lis(full) + lis(ins.get('caveats', []))
        if ins.get('suggested_next_step'):
            evidence_body += paras([('Analytical follow-up', ins['suggested_next_step'])])
        body += [details('Full evidence and qualifications', evidence_body), '</section>']
        finding_appendix += [f'### {title}', '', ins['statement'], '',
                             f"Strength: {ins['strength']}; confidence: {ins['confidence']}", '']
        finding_appendix += [f'- {x}' for x in full]
        finding_appendix += [f'- Caveat: {x}' for x in ins.get('caveats', [])]
        if ins.get('suggested_next_step'):
            finding_appendix += [f"- Analytical follow-up: {ins['suggested_next_step']}"]
        finding_appendix += ['']
    if not draft.get('insights'):
        reason = draft.get('no_findings_reason', 'No findings recorded.')
        body.append(f'<p>{e(reason)}</p>'); md += [reason, '']
    meta = [('Purpose', scope['purpose']), ('Decision supported', scope['decision_supported']),
            ('Target', f"{scope['target']['column']}: {scope['target']['definition']}"),
            ('Data', f"{prep.get('n_rows')} rows; unit = {scope['unit_of_analysis']}"),
            ('Panel interpretation', panel_line(scope))]
    context = scope.get('business_context', {})
    meta += [(key.replace('_', ' ').capitalize(), value) for key, value in context.items()]
    statistical_note = 'Statistical estimates show available n, confidence intervals and Benjamini-Hochberg q-values across recorded tests. Data-selected follow-ups remain exploratory.'
    technical = ['<h3>Scope and methodology</h3>', paras(meta), f'<p>{e(statistical_note)}</p>', '<h3>Hypothesis verdicts</h3>']
    md += ['## Technical appendix', ''] + [f'**{label}:** {_text(value)}  ' for label, value in meta if value]
    md += ['', statistical_note, ''] + action_appendix + finding_appendix + ['### Hypothesis verdicts', '']
    for verdict in review.get('hypothesis_verdicts', []):
        title = f"{verdict['id']}: {verdict['verdict']}"
        technical += [f'<h4>{e(title)}</h4><p>{e(verdict["reasoning"])}</p>']
        md += [f'**{title}**', '', verdict['reasoning'], '']
    for title, values in [('Limitations', draft.get('limitations', [])),
                          ('Additional next steps', draft.get('next_steps', [])),
                          ('Data preparation', prep.get('log', []))]:
        technical += [f'<h3>{e(title)}</h3>', lis(values)]
        md += [f'### {title}', ''] + [f'- {x}' for x in values] + ['']
    technical.append(paras([('Data quality', dq.get('summary', 'n/a'))]))
    md += [f"Data quality: {dq.get('summary', 'n/a')}", '']
    judgments = draft.get('business_review', {})
    if judgments:
        values = [f"{area}: {j['status']} — {j['reason']}" for area, j in judgments.items()]
        technical += ['<h3>Business review</h3>', lis(values)]
        md += ['### Business review', ''] + [f'- {x}' for x in values] + ['']
    runs = [f"{k} — {r['tool']}: {r.get('summary') or r.get('error')}" +
            (f" (follow-up: {r['followup_reason']})" if r.get('followup_reason') else '') for k, r in sorted(results.items())]
    runs += [f"{s['step_id']} — {s['tool']} (user-approved skip): {s.get('skip_reason')}"
             for s in analyses.get('steps', []) if s.get('status') == 'skipped']
    technical += ['<h3>Analyses run</h3>', lis(runs)]
    md += ['### Analyses run', ''] + [f'- {x}' for x in runs]
    body.append(details('Technical appendix: methods, limitations and audit trail', ''.join(technical)))
    css = '''body{font-family:Segoe UI,Arial,sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#213547;line-height:1.6}
    h1{font-size:2rem}h2{margin-top:2rem}h3{line-height:1.35}p,li{overflow-wrap:anywhere}
    .executive{background:#eef5fa;border-left:5px solid #245f87;padding:16px 24px}.lead{font-size:1.2rem}
    .action{border-top:2px solid #245f87;padding:20px 0}.tag{font-size:.85rem;text-transform:uppercase;color:#245f87;font-weight:700}
    .finding{border-top:1px solid #ccd6de;padding:12px 0}.note{color:#526575;font-size:.95rem}
    details{margin:16px 0;padding:12px;background:#f5f7f9}summary{cursor:pointer;font-weight:600}
    figure{margin:20px 0}img{max-width:100%;height:auto}figcaption{color:#526575}
    @media(max-width:600px){body{padding:0 16px;margin:20px auto}.executive{padding:12px}}
    @media print{details{display:block}details>*{display:block}summary{display:block}.action,.finding{break-inside:avoid}}
    '''
    document = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(scope["project_name"])}</title><style>{css}</style></head><body><main>{"".join(body)}</main></body></html>'
    (run_dir / 'report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    (run_dir / 'report.html').write_text(document, encoding='utf-8')
    return {'files': ['report.md', 'report.html'], 'n_insights': len(draft.get('insights', [])),
            'n_charts': n_charts, 'schema_version': draft.get('schema_version', 1)}
