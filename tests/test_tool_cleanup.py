"""Tool contracts, legacy dispatch and evidence reuse across analysis views."""
import json

import numpy as np
import pandas as pd
import pytest

from insight_core import registry, stats
from insight_core.context import Ctx
from insight_core.tools_analysis import (
    adjusted_correlation, correlation_by_group, feature_target_associations,
    multiple_testing_adjustment, pair_deep_dive, target_by_group, target_by_numeric_bins,
)


@pytest.fixture
def ctx(tmp_path):
    for folder in ('charts', 'results'):
        (tmp_path / folder).mkdir()
    rng = np.random.default_rng(11)
    x = rng.normal(size=100)
    df = pd.DataFrame({'x': x, 'y': x + rng.normal(size=100), 'group': ['a'] * 50 + ['b'] * 50,
                       'control': rng.normal(size=100)})
    return Ctx(tmp_path, df, {'x': 'numeric', 'y': 'numeric', 'group': 'categorical', 'control': 'numeric'},
               {'target': {'column': 'y', 'type': 'numeric'}, 'min_n': 5}, 'demo', ['x'])


def test_catalogue_only_exposes_new_ids_and_reuse_guidance():
    catalogue = {t['id']: t for t in registry.catalogue('analysis')}
    for old, new in registry.ALIASES.items():
        assert old not in catalogue
        assert new in catalogue
        assert registry.get(old) == registry.get(new)
    assert catalogue['adjusted-correlation']['reuse']


def test_legacy_categorical_dispatch_and_clear_new_contracts(ctx):
    name, params = registry.resolve_call('pair-deep-dive', {'x': 'group', 'bins': 3}, ctx.types)
    assert (name, params) == ('target-by-group', {'by': 'group'})
    old = pair_deep_dive(ctx, {'x': 'group'})
    new = target_by_group(ctx, {'by': 'group'})
    pd.testing.assert_frame_equal(old['tables']['breakdown'], new['tables']['breakdown'])
    with pytest.raises(ValueError, match='numeric x'):
        target_by_numeric_bins(ctx, {'x': 'group'})
    with pytest.raises(ValueError, match='categorical'):
        target_by_group(ctx, {'by': 'x'})


def test_numeric_bins_do_not_change_underlying_test(ctx):
    screen = feature_target_associations(ctx, {})['findings'][0]
    for bins in (3, 5):
        result = target_by_numeric_bins(ctx, {'x': 'x', 'bins': bins})
        assert result['findings'][0]['test_id'] == screen['test_id']
        assert result['findings'][0]['estimate'] == screen['estimate']
        assert len(result['tables']['profile']) == bins


def test_group_within_matches_adjusted_and_extra_controls_are_distinct(ctx):
    grouped = correlation_by_group(ctx, {'x': 'x', 'by': 'group'})
    within = next(f for f in grouped['findings'] if f['segment'] == 'within')
    adjusted = adjusted_correlation(ctx, {'x': 'x', 'controls': ['group']})['findings'][1]
    assert adjusted['estimate'] == within['estimate']
    assert adjusted['test_id'] == within['test_id']
    extra = adjusted_correlation(ctx, {'x': 'x', 'controls': ['group', 'control']})['findings'][1]
    assert extra['test_id'] != adjusted['test_id']
    ctx.df = ctx.df.iloc[:-1]
    subset = adjusted_correlation(ctx, {'x': 'x', 'controls': ['group']})['findings'][1]
    assert subset['test_id'] != adjusted['test_id']


def test_fdr_deduplicates_tests_but_preserves_all_references(ctx):
    for label, test_id, p in [('screen', 'a', .01), ('dive', 'a', .01), ('other', 'b', .04)]:
        record = {'tool': 'test', 'label': label, 'findings': [
            {'label': 'relationship', 'metric': 'spearman_r', 'estimate': .3, 'p': p, 'test_id': test_id}]}
        (ctx.run_dir / 'results' / f'{label}.json').write_text(json.dumps(record))
    result = multiple_testing_adjustment(ctx, {})
    assert result['n_unique_tests'] == 2
    rows = {r['result']: r for r in result['q_values']}
    assert len(rows) == 3
    assert rows['screen']['q'] == rows['dive']['q'] == pytest.approx(.02)
    assert rows['other']['q'] == pytest.approx(.04)


def test_inconsistent_duplicate_evidence_is_rejected(ctx):
    for i,p in enumerate([.01,.03]):
        (ctx.run_dir/'results'/f'{i}.json').write_text(json.dumps({'tool':'test','label':str(i),'findings':[
            {'label':'same','metric':'r','estimate':.2,'p':p,'test_id':'same'}]}))
    with pytest.raises(ValueError, match='inconsistent'):
        multiple_testing_adjustment(ctx,{})


def test_legacy_findings_are_not_deduplicated_by_guessing(ctx):
    for i in range(2):
        (ctx.run_dir/'results'/f'{i}.json').write_text(json.dumps({'tool':'test','label':str(i),'findings':[
            {'label':'same','metric':'r','estimate':.2,'p':.01}]}))
    assert multiple_testing_adjustment(ctx,{})['n_unique_tests'] == 2


def test_executor_accepts_legacy_categorical_plan_and_records_canonical_tool(ctx, monkeypatch):
    from insight_core import runner
    from insight_core.data import profile
    ctx.scope.update({'unit_of_analysis': 'house', 'drivers': ['group'], 'hypotheses': []})
    monkeypatch.setattr(runner, 'load_approved', lambda path: ctx.scope)
    monkeypatch.setattr(runner, 'load_prepared', lambda path: (ctx.df, {'columns': ctx.types}))
    monkeypatch.setattr(runner, 'read_artifact', lambda path, name: profile(ctx.df) if name == 'profile.json' else {})
    monkeypatch.setattr(runner, 'leakage_columns', lambda path: [])
    monkeypatch.setattr(runner.events, 'emit', lambda *args, **kwargs: None)
    result = runner.execute(ctx.run_dir, 'pair-deep-dive', {'x': 'group'}, 'legacy', 'test', step={'step_id': 'H1.S1'})
    assert 'error' not in result
    assert result['tool'] == 'target-by-group'
    assert result['requested_tool'] == 'pair-deep-dive'
    assert result['params'] == {'by': 'group'}
    assert result['findings'][0]['test_id']


def test_executor_ids_distinguish_views_and_reuse_exact_model_reruns(ctx, monkeypatch):
    from insight_core import runner
    from insight_core.data import profile
    ctx.scope.update({'unit_of_analysis': 'house', 'drivers': ['x'], 'hypotheses': []})
    monkeypatch.setattr(runner, 'load_approved', lambda path: ctx.scope)
    monkeypatch.setattr(runner, 'load_prepared', lambda path: (ctx.df, {'columns': ctx.types}))
    monkeypatch.setattr(runner, 'read_artifact', lambda path, name: profile(ctx.df) if name == 'profile.json' else {})
    monkeypatch.setattr(runner, 'leakage_columns', lambda path: [])
    monkeypatch.setattr(runner.events, 'emit', lambda *args, **kwargs: None)
    monkeypatch.setattr(registry, 'function', lambda tool: lambda c, p: {'findings': [
        {'label': 'x adjusted slope', 'metric': 'std_coef', 'estimate': .3, 'p': .01}]})
    def execute(label):
        return runner.execute(ctx.run_dir, 'predictive-feature-importance', {}, label, 'test', step={})['findings'][0]['test_id']
    first = execute('one')
    assert execute('two') == first
    ctx.scope['active_view'] = 'other-grain'
    assert execute('three') != first
