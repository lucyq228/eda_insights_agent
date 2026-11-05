"""Presentation contracts: source arithmetic, complete coverage and checkpoint preservation."""
import copy
import json

import pandas as pd
import pytest

from insight_core.executive import build, bridge, change_table, RATE, COUNT
from insight_core.state import MILESTONES, write_artifact, sha, milestone_status


@pytest.fixture
def checkpoint(tmp_path):
    (tmp_path / 'results').mkdir()
    for _, name, _, upstream in MILESTONES[:-1]:
        data = {}
        if name == 'approved_scope.json':
            data = {'target': {'definition': 'Events / eligible units'}, 'unit_of_analysis': 'eligible unit'}
        if name == 'insights.json':
            data = {'insights': [{'id': 'I1', 'evidence': [{'result': 'H1.S1'}]}], 'limitations': ['Descriptive evidence']}
        write_artifact(tmp_path, name, data, upstream)
    write_artifact(tmp_path, 'scope.lock.json', {'sha256': sha(tmp_path / 'approved_scope.json')})
    (tmp_path / 'report.html').write_text('<p>Original hypotheses and tools</p>')
    (tmp_path / 'report.md').write_text('Original hypotheses and tools')
    # Two groups, equal total volume; the mix changes and one group rate rises.
    t = pd.DataFrame({'group': ['A', 'B'], 'baseline_n': [80, 20], 'comparison_n': [60, 40],
                      'baseline_events': [8, 4], 'comparison_events': [6, 12]})
    for role in ('baseline', 'comparison'):
        t[role + '_share'] = t[role + '_n'] / 100
        t[role + '_rate'] = t[role + '_events'] / t[role + '_n']
    t['expected_events'] = t.comparison_n * t.baseline_rate
    t['mix_pp'] = 100 * (t.comparison_share - t.baseline_share) * t.baseline_rate
    t['within_pp'] = t.comparison_events - t.expected_events
    t.to_csv(tmp_path / 'results/groups.csv', index=False)
    pd.DataFrame({'role': ['baseline', 'comparison'], 'n': [100, 100], 'events': [12, 18]}).to_csv(tmp_path / 'results/cohorts.csv', index=False)
    r = {'tool': RATE, 'tables': {'groups': {'file': 'groups.csv'}, 'cohorts': {'file': 'cohorts.csv'}}, 'params': {}}
    write_artifact(tmp_path, 'results/H1.S1.json', r)
    story = {'checkpoint_sha256': sha(tmp_path / 'report.json'), 'title': 'Mix and rates explain the increase',
             'summary': 'Rate rose from 12% to 18%.', 'conclusion': 'Compare both mechanisms.',
             'sections': [{'headline': 'Both groups remain visible', 'message': 'Group B gained share and its rate rose.',
                           'result': 'H1.S1', 'insight_ids': ['I1'], 'highlight': [{'group': 'B'}],
                           'charts': [{'x': 'segment', 'y': ['baseline_share_pct', 'comparison_share_pct'],
                                       'title': 'Group shares', 'unit': 'Share (%)'}]}],
             'recap': {'result': 'H1.S1'}}
    return tmp_path, r, story


def test_render_preserves_checkpoint_and_all_groups(checkpoint):
    p, r, story = checkpoint
    before = {n: (p / n).read_bytes() for n in ['report.html', 'report.md', 'report.json']}
    build(p, story)
    html = (p / 'executive_report.html').read_text()
    assert 'Full calculation table' in html and 'data:image/png;base64' in html
    assert 'Eligible units' in html and 'Loans' not in html
    assert '<td>A</td>' in html and '<td>B</td>' in html
    assert 'report.html' in html and 'report.md' in html
    assert all((p / n).read_bytes() == data for n, data in before.items())
    assert milestone_status(p)[-1]['status'] == 'done'
    t, _, start, end = change_table(p, r)
    assert (start, end) == (12, 18)
    assert t.mix_pp.sum() == pytest.approx(2) and t.within_pp.sum() == pytest.approx(4)
    with (p / 'results/groups.csv').open('a') as f:
        f.write('\n')
    assert milestone_status(p)[-1]['status'] == 'stale'


@pytest.mark.parametrize('case', ['overlap', 'omission', 'unknown', 'bad_arithmetic', 'old_checkpoint', 'missing_original'])
def test_rejects_untraceable_presentation(checkpoint, case):
    p, r, story = checkpoint
    if case == 'overlap':
        story['recap']['components'] = [{'label': 'All', 'metric': 'mix_pp', 'remaining': True},
                                        {'label': 'B', 'metric': 'mix_pp', 'where': {'group': 'B'}}]
    elif case == 'omission':
        story['recap']['components'] = [{'label': 'Mix only', 'metric': 'mix_pp', 'remaining': True}]
    elif case == 'unknown':
        story['sections'][0]['result'] = 'missing'
    elif case == 'bad_arithmetic':
        t = pd.read_csv(p / 'results/groups.csv'); t.loc[0, 'mix_pp'] = 999
        t.to_csv(p / 'results/groups.csv', index=False)
    elif case == 'old_checkpoint':
        story['checkpoint_sha256'] = 'old'
    else:
        (p / 'report.md').unlink()
    with pytest.raises(ValueError):
        build(p, story)
    assert not (p / 'executive_report.html').exists()


def test_generic_tables_are_complete_and_not_additive(checkpoint):
    p, _, story = checkpoint
    r = {'tool': 'target-by-group', 'tables': {'comparison': {'file': 'comparison.csv'}}}
    pd.DataFrame({'group': [f'G{i}' for i in range(35)], 'mean': range(35)}).to_csv(p / 'results/comparison.csv', index=False)
    write_artifact(p, 'results/H1.S1.json', r)
    section = story['sections'][0]
    section.update(table='comparison', highlight=[], charts=[{'x': 'group', 'y': ['mean'], 'title': 'All groups', 'unit': 'Mean'}])
    with pytest.raises(ValueError, match='not associations'):
        build(p, story)
    del story['recap']
    build(p, story)
    assert '<td>G34</td>' in (p / 'executive_report.html').read_text()


def test_count_reconciliation(checkpoint):
    p, _, _ = checkpoint
    pd.DataFrame({'group': ['A', 'B'], 'expected': [80, 20], 'observed': [60, 50], 'contribution': [-20, 30]}).to_csv(p / 'results/groups.csv', index=False)
    r = {'tool': COUNT, 'tables': {'groups': {'file': 'groups.csv'}}, 'findings': [
        {'metric': k, 'estimate': v} for k, v in [('expected_count', 100), ('observed_count', 110), ('net_change', 10)]]}
    write_artifact(p, 'results/H1.S1.json', r)
    assert 'Full calculation table' in bridge(p, {'result': 'H1.S1'})
    r['findings'][0]['estimate'] = 999
    with pytest.raises(ValueError, match='totals'):
        change_table(p, r)


def test_real_tool_joint_groups_and_undefined_reference(checkpoint):
    from insight_core import data, registry
    from insight_core.context import Ctx
    from insight_core.runner import save_result
    p, _, story = checkpoint
    df = pd.DataFrame({'period': ['A', 'A', 'B', 'B'], 'tier': ['low', 'high', 'low', 'high'],
                       'channel': ['direct'] * 4, 'events': [2, 5, 3, 8], 'eligible': [100, 50, 80, 70]})
    scope = {'target': {'column': 'events', 'type': 'numeric'}, 'min_n': 2}
    ctx = Ctx(p, df, data.column_types(df), scope, 'demo')
    params = {'cohort': 'period', 'baseline': 'A', 'comparison': 'B', 'by': ['tier', 'channel'], 'denominator': 'eligible'}
    out = registry.function(RATE)(ctx, params)
    result = save_result(p, 'H1.S1', RATE, params, out, {})
    story['sections'][0]['highlight'] = [{'group_1': 'high', 'group_2': 'direct'}]
    build(p, story)
    assert 'tier' in (p / 'executive_report.html').read_text()
    df.loc[3, 'channel'] = 'new'
    out = registry.function(RATE)(ctx, params)
    result = save_result(p, 'H1.S1', RATE, params, out, {})
    with pytest.raises(ValueError, match='incomplete attribution'):
        bridge(p, {'result': 'H1.S1'})
    del story['recap']
    story['sections'][0].update(highlight=[], charts=[], chart_omission_reason='Undefined baseline rate; complete table preserves the gap.')
    build(p, story)
    html = (p / 'executive_report.html').read_text()
    assert 'Undefined' in html and 'baseline rate' in html
