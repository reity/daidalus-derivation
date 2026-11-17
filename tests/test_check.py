"""
Tests of the grading of implementations against the exact model.
"""
import json
import pathlib

from wellclear import check

ROOT = pathlib.Path(__file__).resolve().parent.parent

def expected(**fields):
    record = {
        'valid': '1', 'conf_exp': '1', 'conf_band': '', 'lo': '1.0', 'hi': '2.0',
        'viol_exp': '0', 'viol_band': '', 'touch_only': '0'
    }
    record.update(fields)
    return record

def result(**fields):
    record = {'conflict': '1', 't_in': '1.0', 't_out': '2.0', 'violation': '0', 'error': ''}
    record.update(fields)
    return record

def test_decisions_outside_band_are_graded():
    vectors = {'a': {'cat': 'cpa', 'base': ''}, 'b': {'cat': 'cpa', 'base': ''}}
    oracle = {'a': expected(), 'b': expected(conf_exp='0', lo='', hi='')}
    grade = check.grade(vectors, oracle, {'a': result(), 'b': result()})
    assert dict(grade['conflict']) == {'pass': 1, 'fail': 1}
    assert grade['failures'] == [
        {'id': 'b', 'cat': 'cpa', 'what': 'conflict decision', 'got': 1, 'exact': 0}
    ]

def test_band_decisions_are_recorded_not_graded():
    vectors = {'a': {'cat': 'cliff_hmd', 'base': ''}}
    oracle = {'a': expected(conf_exp='0', conf_band='hmd;short')}
    grade = check.grade(vectors, oracle, {'a': result()})
    assert not grade['conflict'] and not grade['failures']
    assert dict(grade['band']) == {'n': 1, 'differ': 1, 'hmd_differ': 1, 'short_differ': 1}

def test_endpoint_errors_beyond_tolerance_fail():
    vectors = {'a': {'cat': 'cpa', 'base': ''}, 'b': {'cat': 'cpa', 'base': ''}}
    oracle = {'a': expected(), 'b': expected()}
    results = {'a': result(t_out='2.00001'), 'b': result(t_in='nan')}
    grade = check.grade(vectors, oracle, results)
    assert grade['endpoints']['n'] == 2 and grade['endpoints']['fail'] == 2
    assert [f['what'] for f in grade['failures']] == ['endpoint error', 'endpoint error']

def test_invalid_inputs_and_errors():
    vectors = {'a': {'cat': 'robust:nan_sox', 'base': ''}, 'b': {'cat': 'cpa', 'base': ''}}
    oracle = {'a': {'valid': '0'}, 'b': expected()}
    results = {'a': result(conflict='', error='NonFiniteInput'), 'b': result(error='Oops')}
    grade = check.grade(vectors, oracle, results)
    assert grade['robust'][0]['error'] == 'NonFiniteInput'
    assert grade['failures'][0]['what'] == 'error on valid input'

def test_violation_and_boundary_contact():
    vectors = {'a': {'cat': 'edge:on_circle', 'base': ''}}
    oracle = {'a': expected(conf_exp='0', viol_exp='0', touch_only='1')}
    grade = check.grade(vectors, oracle, {'a': result(conflict='0', violation='1')})
    assert dict(grade['violation']) == {'fail': 1}
    assert dict(grade['touch']) == {'n': 1, 'reports_violation': 1}

def test_metamorphic_comparison_uses_own_base_answer():
    vectors = {
        'a': {'cat': 'cpa', 'base': ''},
        'a:sym': {'cat': 'sym', 'base': 'a'},
        'a:shift': {'cat': 'shift', 'base': 'a'}
    }
    oracle = {key: expected() for key in vectors}
    results = {'a': result(), 'a:sym': result(), 'a:shift': result(t_in='1.1')}
    grade = check.grade(vectors, oracle, results)
    assert dict(grade['meta']) == {'sym_same': 1, 'shift_diff': 1}

def test_pairwise_agreement():
    oracle = {'a': expected(), 'b': expected(conf_band='hmd')}
    first = {'a': result(), 'b': result()}
    second = {'a': result(t_out='2.5'), 'b': result(conflict='0')}
    comparison = check.pairwise(['a', 'b'], oracle, first, second)
    assert dict(comparison['counts']) == {'same': 1, 'endpoints_differ': 1, 'band_diff': 1}
    assert comparison['max_endpoint_diff'] == 0.5 and comparison['decision_diffs'] == ['b']

def test_committed_report_agrees_with_summary():
    report = json.loads((ROOT / 'results' / 'grades.json').read_text('utf-8'))
    summary = json.loads((ROOT / 'results' / 'summary.json').read_text('utf-8'))
    for (name, grade) in report['grades'].items():
        assert summary['grades'][name]['conflict'] == grade['conflict']
        assert summary['grades'][name]['endpoints'] == grade['endpoints']
        assert summary['grades'][name]['failures'] == len(grade['failures']) == 0
    assert report['pairs']['rust|js']['counts'].get('endpoints_differ', 0) == 0
