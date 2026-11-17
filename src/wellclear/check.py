"""
Grading of implementations against the exact model and against each other.

Each implementation is represented by a CSV file with the columns ``id``,
``t_in``, ``t_out``, ``conflict``, ``violation``, ``conflict_bt``, and
``error`` (one row per test vector). Each implementation is graded on every
vector against the oracle record for that vector (see
:obj:`wellclear.oracle.evaluate`) as described below.

* SEM-5 and ACC-2: the conflict decision and the interval endpoints are
  compared with the exact semantics outside the boundary band.
* SEM-8: the violation flag is compared with the exact convention, and contact
  with the boundary at time zero is recorded.
* ACC-1: decisions inside the boundary band are recorded but not graded.
* SEM-6 and SEM-1: the answers on swapped and translated vectors are compared
  with the implementation's own answer on the base vector (metamorphic
  testing).
* ENV-4 and IMP-1: the behavior on invalid inputs (an error or a silent answer)
  is recorded.

Pairs of implementations are also compared directly (differential testing).
"""
from __future__ import annotations
from typing import Iterable
import collections
import doctest
import json
import math
import pathlib

from wellclear.vectors import read

TOLERANCE = 1e-6
"""
Maximum endpoint error (in seconds) outside the boundary band (ACC-2).
"""

def _number(text: str) -> float:
    """
    Return the number represented by a CSV entry (NaN if the entry is empty).

    >>> _number('1.5'), _number('inf'), _number('')
    (1.5, inf, nan)
    """
    return float(text) if text not in ('', None) else math.nan

def _new_grade() -> dict:
    """
    Return an empty grade record.
    """
    return {
        'conflict': collections.Counter(),
        'violation': collections.Counter(),
        'endpoints': {'n': 0, 'fail': 0, 'max_err': 0.0},
        'err_hist': collections.Counter(),
        'band': collections.Counter(),
        'touch': collections.Counter(),
        'meta': collections.Counter(),
        'robust': [],
        'failures': [],
        'by_cat': collections.defaultdict(collections.Counter)
    }

def _endpoints(record: dict, item: tuple, expected: dict, actual: dict) -> None:
    """
    Grade the interval endpoints reported for a conflict (SEM-5, ACC-2).
    """
    (key, vector) = item
    error = max(
        abs(_number(actual['t_in']) - float(expected['lo'])),
        abs(_number(actual['t_out']) - float(expected['hi']))
    )
    record['endpoints']['n'] += 1
    record['endpoints']['max_err'] = max(record['endpoints']['max_err'], error)
    if not math.isfinite(error): # An implementation reported a non-finite endpoint.
        bucket = str(error)
    elif error == 0:
        bucket = '0'
    else:
        bucket = str(math.floor(math.log10(error)))

    record['err_hist'][bucket] += 1
    if math.isnan(error) or error > TOLERANCE:
        record['endpoints']['fail'] += 1
        record['failures'].append(
            {'id': key, 'cat': vector['cat'], 'what': 'endpoint error', 'err': error}
        )

def _conflict(record: dict, item: tuple, expected: dict, actual: dict) -> None:
    """
    Grade the conflict decision for a single vector, or record it if the vector
    lies in the boundary band (ACC-1).
    """
    (key, vector) = item
    (reported, exact) = (actual['conflict'] == '1', expected['conf_exp'] == '1')
    outcome = 'agree' if reported == exact else 'differ'
    if expected['conf_band']:
        record['band']['n'] += 1
        record['band'][outcome] += 1
        for reason in expected['conf_band'].split(';'):
            record['band'][reason + '_' + outcome] += 1
        return

    result = 'pass' if reported == exact else 'fail'
    record['conflict'][result] += 1
    record['by_cat'][vector['cat'].partition(':')[0]][result] += 1
    if reported != exact:
        record['failures'].append({
            'id': key, 'cat': vector['cat'], 'what': 'conflict decision',
            'got': int(reported), 'exact': int(exact)
        })
    elif exact:
        _endpoints(record, item, expected, actual)

def _violation(record: dict, item: tuple, expected: dict, actual: dict) -> None:
    """
    Grade the violation flag for a single vector (SEM-8) and record whether
    any contact with the boundary at time zero is reported as a violation.
    """
    (key, vector) = item
    (reported, exact) = (actual['violation'] == '1', expected['viol_exp'] == '1')
    if expected['viol_band']:
        record['violation']['band_' + ('agree' if reported == exact else 'differ')] += 1
    else:
        record['violation']['pass' if reported == exact else 'fail'] += 1
        if reported != exact:
            record['failures'].append({
                'id': key, 'cat': vector['cat'], 'what': 'violation flag',
                'got': int(reported), 'exact': int(exact)
            })

    if expected['touch_only'] == '1':
        record['touch']['n'] += 1
        record['touch']['reports_violation' if reported else 'follows_convention'] += 1

def _metamorphic(record: dict, item: tuple, oracle: dict, implementation: dict) -> None:
    """
    Compare the answer on a swapped or translated vector with the answer of the
    same implementation on the base vector (SEM-6, SEM-1).
    """
    (key, vector) = item
    (base, actual) = (implementation[vector['base']], implementation[key])
    band = bool(oracle[key]['conf_band'] or oracle[vector['base']]['conf_band'])
    same = base['conflict'] == actual['conflict'] and base['violation'] == actual['violation']
    if same and actual['conflict'] == '1':
        same = (
            abs(_number(base['t_in']) - _number(actual['t_in'])) <= TOLERANCE and
            abs(_number(base['t_out']) - _number(actual['t_out'])) <= TOLERANCE
        )

    category = vector['cat'].partition(':')[0]
    record['meta'][category + ('_band' if band else '') + ('_same' if same else '_diff')] += 1
    if not same and not band:
        record['failures'].append(
            {'id': key, 'cat': vector['cat'], 'what': 'metamorphic', 'base': vector['base']}
        )

def grade(vectors: dict, oracle: dict, implementation: dict) -> dict:
    """
    Return the grade record of an implementation, given dictionaries (keyed by
    vector identifier) of the test vectors, the oracle records, and the
    implementation's results.

    >>> vectors = {'a': {'cat': 'edge:a', 'base': ''}}
    >>> oracle = {'a': {
    ...     'valid': '1', 'conf_exp': '1', 'conf_band': '', 'lo': '1.0', 'hi': '2.0',
    ...     'viol_exp': '0', 'viol_band': '', 'touch_only': '0'
    ... }}
    >>> results = {'a': {'conflict': '1', 't_in': '1.0', 't_out': '2.0000001',
    ...     'violation': '0', 'error': ''}}
    >>> result = grade(vectors, oracle, results)
    >>> dict(result['conflict']), result['endpoints']['n'], result['failures']
    ({'pass': 1}, 1, [])
    """
    result = _new_grade()
    for (key, vector) in vectors.items():
        (expected, actual) = (oracle[key], implementation[key])
        if expected['valid'] != '1':
            result['robust'].append({
                'id': key, 'cat': vector['cat'], 'error': actual.get('error', ''),
                'conflict': actual.get('conflict', ''), 't_in': actual.get('t_in', ''),
                'violation': actual.get('violation', '')
            })
        elif actual.get('error'):
            result['failures'].append({
                'id': key, 'cat': vector['cat'], 'what': 'error on valid input',
                'got': actual['error']
            })
            result['conflict']['fail'] += 1
        else:
            _conflict(result, (key, vector), expected, actual)
            _violation(result, (key, vector), expected, actual)
            if vector['cat'].partition(':')[0] in ('sym', 'shift'):
                _metamorphic(result, (key, vector), oracle, implementation)

    return result

def pairwise(vectors: Iterable[str], oracle: dict, first: dict, second: dict) -> dict:
    """
    Return the agreement between two implementations on the valid vectors
    (differential testing): decision agreement inside and outside the boundary
    band, endpoint agreement, and the identifiers of vectors with different
    decisions.

    >>> oracle = {'a': {'valid': '1', 'conf_band': '', 'viol_band': ''}}
    >>> first = {'a': {'conflict': '1', 't_in': '1.0', 't_out': '2.0', 'violation': '0'}}
    >>> result = pairwise(['a'], oracle, first, first)
    >>> dict(result['counts']), result['max_endpoint_diff']
    ({'same': 1, 'bitwise_equal': 1}, 0.0)
    """
    counts = collections.Counter()
    (largest, differences) = (0.0, [])
    for key in vectors:
        (expected, a, b) = (oracle[key], first[key], second[key])
        if expected['valid'] != '1' or a.get('error') or b.get('error'):
            continue

        same = a['conflict'] == b['conflict']
        counts[('band_' if expected['conf_band'] else '') + ('same' if same else 'diff')] += 1
        if same and a['conflict'] == '1':
            difference = max(
                abs(_number(a['t_in']) - _number(b['t_in'])),
                abs(_number(a['t_out']) - _number(b['t_out']))
            )
            largest = max(largest, difference)
            counts['bitwise_equal' if difference == 0 else 'endpoints_differ'] += 1

        if not same:
            differences.append(key)

        if a['violation'] != b['violation']:
            counts['violation_diff' + ('_band' if expected['viol_band'] else '')] += 1

    return {'counts': counts, 'max_endpoint_diff': largest, 'decision_diffs': differences}

def run(vectors: str | pathlib.Path, oracle: str | pathlib.Path, implementations: dict) -> dict:
    """
    Grade every implementation (a dictionary that maps each implementation name
    to the path of its results file) and compare every pair of implementations.
    Return a dictionary with the entries ``grades`` and ``pairs``.
    """
    (vectors, oracle) = (read(vectors), read(oracle))
    results = {name: read(path) for (name, path) in implementations.items()}
    report = {'grades': {}, 'pairs': {}}
    for (name, result) in results.items():
        report['grades'][name] = grade(vectors, oracle, result)

    names = list(results)
    for (i, first) in enumerate(names):
        for second in names[i + 1:]:
            report['pairs'][first + '|' + second] = \
                pairwise(vectors, oracle, results[first], results[second])

    return report

def write(path: str | pathlib.Path, report: dict) -> None:
    """
    Write a grading report to a JSON file.
    """
    pathlib.Path(path).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')

if __name__ == '__main__':
    doctest.testmod() # pragma: no cover
