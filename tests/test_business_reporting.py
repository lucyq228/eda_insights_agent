"""Decision-first rendering, provenance and legacy compatibility."""
import copy
import json
from pathlib import Path

import pytest

from insight_core.report import build
from insight_core.review import validate_insights
from insight_core.report_contract import REVIEW_AREAS


@pytest.fixture
def case(tmp_path):
    (tmp_path / 'results').mkdir()
    (tmp_path / 'charts').mkdir()
    result = {'label': 'H1', 'tool': 'business-summary', 'summary': 'Observed frequency difference',
              'findings': [{'label': 'frequency', 'metric': 'transactions_per_customer', 'estimate': 4.9,
                            'n': 100, 'evidence_type': 'descriptive'}], 'charts': []}
    scope = {'project_name': 'Retail', 'purpose': 'Prioritize sales opportunities',
             'decision_supported': 'Choose a pilot', 'target': {'column': 'sales', 'definition': 'Category sales'},
             'unit_of_analysis': 'customer', 'report_schema_version': 2}
    ev = {'result': 'H1', 'finding': 'frequency'}
    draft = {'schema_version': 2, 'headline_summary': 'Purchase frequency differs across segments.',
             'decision_requested': 'Approve pilot design subject to contact eligibility.',
             'decision_uncertainties': ['Contact eligibility is unknown.'],
             'insights': [{'id': 'I1', 'title': 'Frequency differs', 'statement': 'Full analytical explanation',
                           'brief_summary': 'The observed frequency is 4.9 purchases per customer.',
                           'business_implication': 'A frequency pilot is a candidate, not proven lift.',
                           'decision_caveat': 'Tenure is unavailable.', 'strength': 'moderate', 'confidence': 'medium',
                           'evidence': [ev], 'key_evidence': [ev], 'caveats': ['Store clustering unresolved.']}],
             'recommendations': [{'id': 'A1', 'action': 'Pilot a repeat-purchase reminder', 'action_type': 'pilot',
                 'rationale': 'Observed purchasing frequency varies.', 'audience': 'Eligible opted-in category buyers',
                 'intervention': 'Randomize a reminder versus no reminder.',
                 'mechanism_hypothesis': 'Test whether a reminder increases repeat purchases.',
                 'priority_reason': 'A low-cost candidate if contact consent exists.',
                 'alternatives_considered': ['No contact: avoids messaging costs.'],
                 'dependencies': ['Confirm contact eligibility.'], 'expected_benefit': 'Unknown incremental sales.',
                 'benefit_basis': 'unquantified', 'decision_rule': 'Expand only if incremental margin clears a prespecified business hurdle.',
                 'success_metric': 'Incremental category sales and contact cost.', 'validation_plan': 'Randomized holdout.',
                 'assumptions': ['Contact channel exists.'], 'risks': ['Unsubscribe risk.'], 'evidence_type': 'descriptive',
                 'evidence': [ev]}],
             'business_review': {k: {'status': 'pass', 'reason': 'Reviewed against available evidence and unknowns.'} for k in REVIEW_AREAS},
             'limitations': ['One category.'], 'next_steps': ['Confirm contact eligibility.']}
    for name, value in [('approved_scope.json', scope), ('insights.json', draft),
                        ('review.json', {'hypothesis_verdicts': [{'id': 'H1', 'verdict': 'supported', 'reasoning': 'Observed.'}]}),
                        ('results/H1.json', result)]:
        (tmp_path / name).write_text(json.dumps(value))
    return tmp_path, draft


def test_v2_preserves_test_hypotheses_but_rejects_factual_causal_claim(case):
    root, draft = case
    assert validate_insights(draft, root) == []
    draft['recommendations'][0]['rationale'] = 'Reminders cause higher sales.'
    assert any('causal wording' in x for x in validate_insights(draft, root))


def test_v2_cannot_silently_downgrade_or_skip_business_review(case):
    root, draft = case
    draft['schema_version'] = 1
    assert any('requires schema_version' in x for x in validate_insights(draft, root))
    draft['schema_version'] = 2
    draft['business_review']['actionability']['status'] = 'revise'
    assert any('resolve revisions' in x for x in validate_insights(draft, root))


def test_no_actions_requires_explanation_not_padding(case):
    root, draft = case
    draft['recommendations'] = []
    assert any('no_recommendations_reason' in x for x in validate_insights(draft, root))
    draft['no_recommendations_reason'] = 'No intervention is justified with the available evidence.'
    assert validate_insights(draft, root) == []


def test_selected_proof_and_benefit_require_provenance(case):
    root, draft = case
    draft['insights'][0]['key_evidence'] = [{'result': 'invented', 'finding': 'lift'}]
    draft['recommendations'][0]['benefit_basis'] = 'scenario'
    errors = validate_insights(draft, root)
    assert any('subset of evidence' in x for x in errors)
    assert any('benefit_calculation' in x for x in errors)


def test_report_is_decision_first_and_keeps_audit_trail(case):
    root, draft = case
    build(root)
    page = (root / 'report.html').read_text()
    md = (root / 'report.md').read_text()
    assert page.index('Prioritized actions') < page.index('Supporting findings')
    assert page.index('Contact eligibility is unknown.') < page.index('Supporting findings')
    assert 'Full evidence and qualifications' in page and '<details>' in page
    assert 'H1 — frequency' in page and 'Store clustering unresolved.' in page
    assert md.index('Prioritized actions') < md.index('Supporting findings') < md.index('Technical appendix')
    assert 'Full analytical explanation' in md and 'Hypothesis verdicts' in md


def test_legacy_report_renders_without_fabricating_actions(case):
    root, draft = case
    for key in ('schema_version', 'recommendations', 'decision_requested', 'decision_uncertainties', 'business_review'):
        draft.pop(key, None)
    (root / 'insights.json').write_text(json.dumps(draft))
    build(root)
    assert 'No recommendations were recorded' in (root / 'report.html').read_text()


def test_html_escapes_business_text(case):
    root, draft = case
    draft['recommendations'][0]['intervention'] = '<script>alert(1)</script>'
    (root / 'insights.json').write_text(json.dumps(draft))
    build(root)
    page = (root / 'report.html').read_text()
    assert '<script>' not in page and '&lt;script&gt;' in page


def test_chart_requires_explicit_registered_safe_selection(case):
    root, draft = case
    outside = root / 'private.png'; outside.write_bytes(b'private')
    result = json.loads((root / 'results/H1.json').read_text())
    result['charts'] = [str(outside)]
    (root / 'results/H1.json').write_text(json.dumps(result))
    draft['insights'][0]['charts'] = [{'result': 'H1', 'index': 0, 'caption': 'Proof'}]
    assert any('registered PNG' in x for x in validate_insights(draft, root))
    draft['insights'][0]['charts'] = []
    (root / 'insights.json').write_text(json.dumps(draft))
    assert build(root)['n_charts'] == 0


def test_scope_v2_accepts_explicit_unknown_context():
    from insight_core.scope import validate
    scope = {'project_name': 'EDA', 'purpose': 'Explore', 'decision_supported': 'Prioritize',
             'target': {'column': 'sales', 'type': 'numeric', 'definition': 'Sales'},
             'unit_of_analysis': 'line', 'report_schema_version': 2,
             'business_context': {'audience': 'unknown', 'decision': 'Prioritize opportunities',
                'available_levers': [], 'constraints': [], 'success_measures': [], 'unknowns': ['Budget unknown']},
             'hypotheses': [{'id': 'H1', 'statement': 'Describe sales', 'rationale': 'Size',
                'support_criteria': 'Reconciled total', 'pathway': [{'tool': 'business-summary', 'purpose': 'Describe', 'params': {}}]}]}
    profile = {'columns': [{'name': 'sales', 'type': 'numeric'}]}
    assert validate(scope, profile)[0] == []
    del scope['business_context']
    assert 'v2 scope needs business_context' in validate(scope, profile)[0]


def test_selected_chart_renders_with_caption(case):
    import base64
    root, draft = case
    path = root / 'charts' / 'proof.png'
    path.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII='))
    result = json.loads((root / 'results/H1.json').read_text())
    result['charts'] = [str(path)]
    (root / 'results/H1.json').write_text(json.dumps(result))
    draft['insights'][0]['charts'] = [{'result': 'H1', 'index': 0, 'caption': 'Observed frequency by segment'}]
    assert validate_insights(draft, root) == []
    (root / 'insights.json').write_text(json.dumps(draft))
    assert build(root)['n_charts'] == 1
    assert '<figcaption>Observed frequency by segment</figcaption>' in (root / 'report.html').read_text()
