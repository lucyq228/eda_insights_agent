"""Versioned business report structure. Semantic judgments belong to the reviewer."""
from pathlib import Path

REVIEW_AREAS = ('decision_clarity', 'actionability', 'evidence_alignment', 'uncertainty', 'communication')
ACTION_TYPES = ('investigate', 'pilot', 'implement', 'monitor')


def selected_charts(insight, results, run_dir):
    """Only embed explicitly selected, registered PNGs inside this run's chart directory."""
    out = []
    root = (Path(run_dir) / 'charts').resolve()
    for choice in insight.get('charts', []):
        if not isinstance(choice, dict):
            continue
        charts = results.get(choice.get('result'), {}).get('charts', [])
        index = choice.get('index')
        if type(index) is not int or not 0 <= index < len(charts):
            continue
        path = Path(charts[index])
        if not path.is_absolute():
            path = Path(run_dir) / path
        path = path.resolve()
        if path.is_relative_to(root) and path.is_file() and path.suffix.lower() == '.png':
            out.append((path, choice.get('caption', '')))
    return out


def validate_v2(draft, results, run_dir):
    errors = []
    def text(obj, key, where):
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            errors.append(f'{where}: needs nonempty {key}')
    def strings(obj, key, where, nonempty=False):
        value = obj.get(key)
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value) or (nonempty and not value):
            errors.append(f'{where}: {key} must be a list of nonempty strings')
    text(draft, 'decision_requested', 'report')
    strings(draft, 'decision_uncertainties', 'report')
    if not draft.get('recommendations'):
        text(draft, 'no_recommendations_reason', 'report')
    for ins in draft.get('insights', []):
        where = f"insight {ins.get('id')}"
        for key in ('brief_summary', 'business_implication', 'decision_caveat'):
            text(ins, key, where)
        keys = ins.get('key_evidence')
        if not isinstance(keys, list) or not keys:
            errors.append(f'{where}: select key_evidence')
        else:
            for ev in keys:
                if ev not in ins.get('evidence', []):
                    errors.append(f'{where}: key_evidence must be a subset of evidence')
        choices = ins.get('charts', [])
        if not isinstance(choices, list):
            errors.append(f'{where}: charts must be a list'); continue
        for choice in choices:
            if not isinstance(choice, dict):
                errors.append(f'{where}: chart must be an object'); continue
            text(choice, 'caption', where)
            if choice.get('result') not in {x.get('result') for x in ins.get('evidence', [])}:
                errors.append(f'{where}: chart result must be cited as evidence')
        if len(selected_charts(ins, results, run_dir)) != len(choices):
            errors.append(f'{where}: chart must select an existing registered PNG inside run/charts')
    for rec in draft.get('recommendations', []):
        where = f"recommendation {rec.get('id', '?')}"
        for key in ('id', 'audience', 'intervention', 'mechanism_hypothesis', 'priority_reason',
                    'decision_rule', 'expected_benefit'):
            text(rec, key, where)
        if rec.get('action_type') not in ACTION_TYPES:
            errors.append(f'{where}: action_type must be one of {ACTION_TYPES}')
        if rec.get('benefit_basis') not in ('unquantified', 'scenario', 'measured'):
            errors.append(f'{where}: benefit_basis must be unquantified, scenario or measured')
        if rec.get('benefit_basis') in ('scenario', 'measured'):
            text(rec, 'benefit_calculation', where)
        if rec.get('action_type') == 'implement':
            text(rec, 'implementation_basis', where)
        strings(rec, 'alternatives_considered', where, nonempty=True)
        strings(rec, 'dependencies', where)
        for ev in rec.get('evidence', []):
            if not ev.get('finding'):
                errors.append(f'{where}: evidence needs an exact finding reference')
    for field in ('insights', 'recommendations'):
        ids = [x.get('id') for x in draft.get(field, [])]
        if len(ids) != len(set(ids)):
            errors.append(f'{field}: ids must be unique')
    judgments = draft.get('business_review', {})
    if not isinstance(judgments, dict):
        judgments = {}
    for area in REVIEW_AREAS:
        judgment = judgments.get(area, {})
        if not isinstance(judgment, dict) or judgment.get('status') not in ('pass', 'not_applicable'):
            errors.append(f'business_review.{area}: resolve revisions before saving')
        else:
            text(judgment, 'reason', f'business_review.{area}')
    return errors
