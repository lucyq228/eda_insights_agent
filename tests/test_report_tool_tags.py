"""Insight tags follow cited evidence, not every tool used in a run."""
import json

from insight_core.report import build, supporting_tools


def test_supporting_tools_deduplicate_aliases_and_ignore_uncited_or_invalid_evidence():
    results = {
        'a': {'tool': 'partial-correlation', 'findings': [{'label': 'valid'}]},
        'b': {'tool': 'adjusted-correlation', 'findings': [{'label': 'valid'}]},
        'c': {'tool': 'time-trend', 'findings': [{'label': 'valid'}]},
        'failed': {'tool': 'target-by-group', 'error': 'failed'},
    }
    insight = {'evidence': [{'result': 'a', 'finding': 'valid'}, {'result': 'b', 'finding': 'valid'},
                            {'result': 'c', 'finding': 'missing'}, {'result': 'missing'}, {'result': 'failed'}]}
    assert supporting_tools(insight, results) == ['adjusted-correlation']
    assert supporting_tools({'evidence': []}, results) == []


def test_legacy_categorical_pair_uses_group_tag():
    results = {'a': {'tool': 'pair-deep-dive', 'findings': [
        {'label': 'group', 'metric': 'eta', 'direction': 'highest in A, lowest in B'}]}}
    assert supporting_tools({'evidence': [{'result': 'a', 'finding': 'group'}]}, results) == ['target-by-group']


def test_html_and_markdown_include_only_each_insights_supporting_tools(tmp_path):
    (tmp_path / 'results').mkdir()
    def save(name, data):
        (tmp_path / name).write_text(json.dumps(data))
    save('approved_scope.json', {'project_name': 'Demo', 'purpose': 'Explain prices', 'decision_supported': 'Investigate',
        'target': {'column': 'price', 'type': 'numeric', 'definition': 'sale price'}, 'unit_of_analysis': 'house'})
    finding = {'label': 'size-price', 'metric': 'spearman_r', 'estimate': .6, 'n': 100}
    save('results/a.json', {'label': 'a', 'tool': 'feature-target-associations', 'findings': [finding], 'charts': []})
    save('results/b.json', {'label': 'b', 'tool': 'target-by-numeric-bins', 'findings': [finding], 'charts': []})
    save('results/c.json', {'label': 'c', 'tool': '<custom-tool>', 'findings': [finding], 'charts': []})
    base = {'title': 'Size and price', 'statement': 'An association.', 'strength': 'strong', 'confidence': 'high'}
    save('insights.json', {'headline_summary': 'Demo', 'insights': [
        dict(base, id='I1', evidence=[{'result': 'a', 'finding': 'size-price'}, {'result': 'b', 'finding': 'size-price'},
                                    {'result': 'b', 'finding': 'size-price'}]),
        dict(base, id='I2', evidence=[{'result': 'c', 'finding': 'size-price'}])]})
    save('review.json', {'hypothesis_verdicts': []})
    build(tmp_path)
    html = (tmp_path / 'report.html').read_text()
    first = html.split('<section class="card">')[1].split('</section>')[0]
    second = html.split('<section class="card">')[2].split('</section>')[0]
    assert '<span>strong</span><span>confidence: high</span><span class="tool-tag">' in first
    assert first.count('tool: feature-target-associations') == 1
    assert first.count('tool: target-by-numeric-bins') == 1
    assert 'custom-tool' not in first
    assert 'tool: &lt;custom-tool&gt;' in second
    assert '<custom-tool>' not in html
    assert 'flex-wrap:wrap' in html
    assert '*Supporting tools:* `feature-target-associations`, `target-by-numeric-bins`' in (tmp_path/'report.md').read_text()
