"""
Certificate checking of implementation answers, an exact executable twin of
the checker that is proved sound in Lean (``lean/Wellclear/Check.lean``).

The checker decides, for each answer of an implementation, which guarantee the
answer carries with respect to the exact semantics over the real numbers
(SEM-2 to SEM-5), with the endpoint tolerance :obj:`EPSILON` of ACC-2. It
uses only rational arithmetic: every square root of the closed-form solution is
replaced by a sign test of a quadratic polynomial (see :obj:`r_test` and
:obj:`x_test`). The verdicts are as follows.

* ``interval``: the answer is a conflict on ``[t_in, t_out]``, there is no
  violation within the lookahead window before ``t_in - EPSILON`` or after
  ``t_out + EPSILON``, and there is a violation at every time of a nonempty
  interval whose endpoints lie within ``EPSILON`` of ``t_in`` and ``t_out``.
* ``empty``: the answer is no conflict and there is no violation at any time
  within the lookahead window.
* ``short``: the answer is no conflict and every violation within the lookahead
  window lies strictly within ``EPSILON`` of a hint (SEM-7 suppresses such a
  near-instantaneous loss of well-clear). The hint is untrusted; it is taken
  from the exact model.
* ``uncertified``: none of the above could be established.
* ``invalid``: the input lies outside the domain of the model (ENV-1, ENV-2,
  ENV-4).

The soundness theorems ``certify_interval``, ``certify_empty``, and
``certify_short`` in Lean state that the verdicts ``interval``, ``empty``, and
``short`` imply the guarantees above. The functions of this module mirror the
Lean definitions one for one (``h_a`` is ``hA``, ``clear_test`` is
``ClearTest``, and so on), and ``make lean`` checks that the Lean checker and
this module give the same verdict for every answer.

The example below certifies the answer of an implementation for a head-on
encounter closing at 200 meters per second from 9 kilometers at the same
altitude.

>>> case = oracle.encounter(([0, 0, 0], [100, 0, 0], [9000, 0, 0], [-100, 0, 0]),
...     (1000.0, 100.0, 35.0, 0.0))
>>> window = (Fraction(0), Fraction(180))
>>> certify(case, window, (Fraction(9.2997257), Fraction(50.0000009)), Fraction(0))
'interval'
>>> certify(case, window, (Fraction(9.299723), Fraction(50)), Fraction(0))
'uncertified'
>>> certify(case, (Fraction(0), Fraction(5)), None, Fraction(0))
'empty'
"""
from __future__ import annotations
from typing import Iterable
import collections
import csv
import doctest
from fractions import Fraction
import json
import math
import multiprocessing
import pathlib
import struct

from wellclear import oracle
from wellclear.vectors import FIELDS, read

EPSILON = Fraction(1, 10 ** 6)
"""
Endpoint tolerance in seconds (ACC-2).
"""

VERDICTS = ('interval', 'empty', 'short', 'uncertified', 'invalid')
"""
Possible verdicts, in the order in which they are reported.
"""

LEAN_COLUMNS = ('id',) + FIELDS + ('conflict', 't_in', 't_out', 'hint')
"""
Columns of the input file of the Lean checker. Every number is written as the
hexadecimal IEEE 754 bit pattern of a double-precision value.
"""

def decode(text: str) -> Fraction | None:
    """
    Return the exact value of a double-precision number written in decimal, or
    ``None`` if it is not finite (or missing).

    >>> decode('0.1')
    Fraction(3602879701896397, 36028797018963968)
    >>> decode('inf') is None, decode('') is None
    (True, True)
    """
    value = float(text) if text not in ('', None) else math.nan
    return Fraction(value) if math.isfinite(value) else None

def bits(text: str) -> str:
    """
    Return the hexadecimal IEEE 754 bit pattern of a double-precision number
    written in decimal (a missing number is written as NaN).

    >>> bits('1.5'), bits('-inf'), bits('')
    ('3ff8000000000000', 'fff0000000000000', '7ff8000000000000')
    """
    value = float(text) if text not in ('', None) else math.nan
    return struct.pack('>d', value).hex()

def h_a(case: dict) -> Fraction:
    """
    Return the squared relative horizontal speed (``hA`` in Lean).
    """
    v = case['v']
    return v[0] * v[0] + v[1] * v[1]

def h_b(case: dict) -> Fraction:
    """
    Return the horizontal dot product of relative position and velocity
    (``hB`` in Lean).
    """
    (s, v) = (case['s'], case['v'])
    return s[0] * v[0] + s[1] * v[1]

def h_ss(case: dict) -> Fraction:
    """
    Return the squared horizontal separation (``hSS`` in Lean).
    """
    s = case['s']
    return s[0] * s[0] + s[1] * s[1]

def h_cross(case: dict) -> Fraction:
    """
    Return the horizontal cross product of relative position and velocity
    (``hCross`` in Lean). Its square divided by :obj:`h_a` is the squared
    horizontal miss distance.
    """
    (s, v) = (case['s'], case['v'])
    return s[0] * v[1] - s[1] * v[0]

def u_at(case: dict, t: Fraction) -> Fraction:
    """
    Return the horizontal dot product of relative position and velocity at time
    ``t`` (``uAt`` in Lean).
    """
    return h_b(case) + h_a(case) * t

def q_d(case: dict, t: Fraction) -> Fraction:
    """
    Return the squared horizontal separation at time ``t`` minus DTHR squared
    (``qD`` in Lean), which is nonpositive inside the DTHR circle.
    """
    return h_a(case) * t * t + 2 * h_b(case) * t + h_ss(case) - case['p']['dthr'] ** 2

def q_tau(case: dict, t: Fraction) -> Fraction:
    """
    Return the quadratic ``qD + TTHR u`` (``qTau`` in Lean), which is
    nonpositive where a converging modified tau is at most TTHR.
    """
    return q_d(case, t) + case['p']['tthr'] * u_at(case, t)

def r_test(case: dict, t: Fraction) -> bool:
    """
    Return whether ``t`` is at or after the smaller root of :obj:`q_tau`,
    without computing the root (``RTest`` in Lean): either the quadratic is
    nonpositive at ``t``, or ``t`` lies at or after its vertex.
    """
    return q_tau(case, t) <= 0 or 0 <= 2 * u_at(case, t) + case['p']['tthr'] * h_a(case)

def x_test(case: dict, t: Fraction) -> bool:
    """
    Return whether ``t`` is at or before the exit from the DTHR circle, without
    computing the root (``XTest`` in Lean): either ``t`` lies inside the
    circle, or at or before the time of closest approach.
    """
    return q_d(case, t) <= 0 or u_at(case, t) <= 0

def hmd_test(case: dict) -> bool:
    """
    Return whether the horizontal miss distance is at most DTHR (``HmdTest`` in
    Lean), for a nonzero relative horizontal velocity.
    """
    return h_cross(case) ** 2 <= case['p']['dthr'] ** 2 * h_a(case)

def v_lo(case: dict) -> Fraction:
    """
    Return the first time of the vertical violation set (``vLo`` in Lean), for a
    nonzero relative vertical speed (SEM-3).
    """
    (sz, vz, p) = (case['s'][2], case['v'][2], case['p'])
    act = max(p['zthr'], max(vz, -vz) * p['tcoa'])
    return (-act - sz) / vz if vz > 0 else (act - sz) / vz

def v_hi(case: dict) -> Fraction:
    """
    Return the last time of the vertical violation set (``vHi`` in Lean), for a
    nonzero relative vertical speed (SEM-3).
    """
    (sz, vz, p) = (case['s'][2], case['v'][2], case['p'])
    return (p['zthr'] - sz) / vz if vz > 0 else (-p['zthr'] - sz) / vz

def window_lo(case: dict, lo: Fraction) -> Fraction:
    """
    Return the start of the intersection of ``[lo, hi]`` with the vertical
    violation set (``winLo`` in Lean).
    """
    return lo if case['v'][2] == 0 else max(lo, v_lo(case))

def window_hi(case: dict, hi: Fraction) -> Fraction:
    """
    Return the end of the intersection of ``[lo, hi]`` with the vertical
    violation set (``winHi`` in Lean).
    """
    return hi if case['v'][2] == 0 else min(hi, v_hi(case))

def clear_test(case: dict, lo: Fraction, hi: Fraction) -> bool:
    """
    Return whether the test that is proved in Lean to imply that there is no
    violation at any time in ``[lo, hi]`` succeeds (``ClearTest`` in Lean).

    >>> case = oracle.encounter(([0, 0, 0], [100, 0, 0], [9000, 0, 0], [-100, 0, 0]),
    ...     (1000.0, 100.0, 35.0, 0.0))
    >>> clear_test(case, Fraction(0), Fraction(9)), clear_test(case, Fraction(0), Fraction(10))
    (True, False)
    """
    (p, sz, vz) = (case['p'], case['s'][2], case['v'][2])
    if hi < lo or (vz == 0 and (sz < -p['zthr'] or p['zthr'] < sz)):
        return True

    (start, end) = (window_lo(case, lo), window_hi(case, hi))
    if end < start:
        return True

    if h_a(case) == 0:
        return p['dthr'] ** 2 < h_ss(case)

    return not (hmd_test(case) and r_test(case, end) and x_test(case, start))

def point_test(case: dict, t: Fraction) -> bool:
    """
    Return whether the test that is proved in Lean to be equivalent to a
    violation at time ``t`` succeeds (``PointTest`` in Lean).
    """
    (p, sz, vz) = (case['p'], case['s'][2], case['v'][2])
    if h_a(case) == 0:
        horizontal = h_ss(case) <= p['dthr'] ** 2
    else:
        horizontal = hmd_test(case) and r_test(case, t) and x_test(case, t)

    vertical = -p['zthr'] <= sz <= p['zthr'] if vz == 0 else v_lo(case) <= t <= v_hi(case)
    return horizontal and vertical

def certify(case: dict, window: tuple, answer: tuple | None, hint: Fraction) -> str:
    """
    Return the verdict for an answer (``certify`` in Lean): ``answer`` is
    ``None`` for no conflict, or the reported interval ``(t_in, t_out)`` (an
    endpoint that is not finite is ``None``).
    """
    (b, t) = window
    if answer is not None:
        (t_in, t_out) = answer
        if t_in is None or t_out is None or t_out < t_in:
            return 'uncertified'

        (x, y) = (t_in + EPSILON, t_out - EPSILON)
        if y < x:
            x = y = (t_in + t_out) / 2

        certified = (
            clear_test(case, b, t_in - EPSILON) and clear_test(case, t_out + EPSILON, t) and
            point_test(case, x) and point_test(case, y)
        )
        return 'interval' if certified else 'uncertified'

    if clear_test(case, b, t):
        return 'empty'

    if clear_test(case, b, hint - EPSILON) and clear_test(case, hint + EPSILON, t):
        return 'short'

    return 'uncertified'

def _domain(values: list[Fraction | None]) -> bool:
    """
    Return whether the inputs lie in the domain of the model: all finite, valid
    thresholds (ENV-1), and ``0 <= B < T`` (ENV-2). The Lean checker applies
    the same test (``Input.valid``).
    """
    if any(value is None for value in values):
        return False

    (b, t, dthr, zthr, tthr, tcoa) = values[12:]
    return dthr > 0 and zthr > 0 and tthr >= 0 and tcoa >= 0 and 0 <= b < t

def short_hint(expected: dict, default: str) -> str:
    """
    Return the (untrusted) hint for a ``short`` certificate as a decimal string:
    the start of the exact violation set if there is one (taken from the oracle
    record), and otherwise ``default``.
    """
    for column in ('exact_lo', 'lo'):
        if expected.get(column):
            return expected[column]

    return default

def evaluate(item: tuple) -> dict:
    """
    Return the verdict record for a test vector, given a tuple of the test
    vector, the oracle record, and the implementation's answer (dictionaries of
    strings). The record also contains the input row of the Lean checker.
    """
    (vector, expected, actual) = item
    values = [decode(vector[k]) for k in FIELDS]
    conflict = actual.get('conflict') == '1'
    clue = short_hint(expected, vector['B'])
    lean = {'id': vector['id']} | {k: bits(vector[k]) for k in FIELDS}
    lean.update(conflict=int(conflict), t_in=bits(actual.get('t_in', '')),
                t_out=bits(actual.get('t_out', '')), hint=bits(clue))
    if not _domain(values):
        return {'id': vector['id'], 'verdict': 'invalid', 'lean': lean}

    case = oracle.encounter((values[0:3], values[3:6], values[6:9], values[9:12]), values[14:18])
    answer = (decode(actual.get('t_in', '')), decode(actual.get('t_out', ''))) if conflict \
        else None
    guess = decode(clue)
    guess = values[12] if guess is None else guess
    verdict = certify(case, (values[12], values[13]), answer, guess)
    return {'id': vector['id'], 'verdict': verdict, 'lean': lean}

def consistent(record: dict, expected: dict, answer: dict) -> bool:
    """
    Return whether a verdict is consistent with the exact model (an independent
    empirical check of the soundness that is proved in Lean): the exact
    violation set must lie within the tolerance of a certified interval, be
    empty when certified empty, and be shorter than twice the tolerance when
    certified short.
    """
    slack = Fraction(1, 10 ** 12) # The exact endpoints are recorded with 21 significant digits.
    verdict = record['verdict']
    nonempty = bool(expected.get('exact_lo'))
    if verdict == 'interval':
        return nonempty and all(
            abs(decode(expected[e]) - decode(answer[a])) <= EPSILON + slack
            for (e, a) in (('exact_lo', 't_in'), ('exact_hi', 't_out'))
        )

    if verdict == 'empty':
        return not nonempty

    if verdict == 'short':
        length = decode(expected['exact_hi']) - decode(expected['exact_lo']) if nonempty else 0
        return length < 2 * EPSILON + slack

    return True

def run(vectors: str | pathlib.Path, oracle_path: str | pathlib.Path,
        answers: str | pathlib.Path, processes: int | None = None) -> list[dict]:
    """
    Certify every answer in the implementation's results file ``answers`` (in
    parallel) and return the verdict records, in corpus order.
    """
    (rows, expected, actual) = (read(vectors), read(oracle_path), read(answers))
    items = [(row, expected[key], actual[key]) for (key, row) in rows.items()]
    with multiprocessing.Pool(processes) as pool:
        return pool.map(evaluate, items, chunksize=200)

def write(directory: str | pathlib.Path, name: str, records: Iterable[dict]) -> tuple:
    """
    Write the verdicts (``certify-NAME.csv``) and the input of the Lean checker
    (``lean-NAME.csv``) to a directory and return the two paths.
    """
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records = list(records)
    paths = (directory / f'certify-{name}.csv', directory / f'lean-{name}.csv')
    with open(paths[0], 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(('id', 'verdict'))
        writer.writerows((record['id'], record['verdict']) for record in records)

    with open(paths[1], 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=LEAN_COLUMNS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(record['lean'] for record in records)

    return paths

def summarize(vectors: dict, expected: dict, answers: dict, records: Iterable[dict]) -> dict:
    """
    Return the verdict counts of an implementation, overall and split by
    whether the vector lies in the boundary band (ACC-1), is affected by the
    numerical conventions (NUM-1, NUM-2), or is graded; the categories of the
    uncertified answers; the number of verdicts that disagree with the exact
    model; and the identifiers of uncertified answers that are graded.
    """
    (counts, categories) = (collections.Counter(), collections.Counter())
    (inconsistent, outside) = (0, [])
    for record in records:
        (key, verdict) = (record['id'], record['verdict'])
        row = expected[key]
        counts[verdict] += 1
        if verdict == 'invalid':
            continue

        group = 'band' if row['conf_band'] else \
            'convention' if row['conv_gap'] not in ('0.0', '') else 'graded'
        counts[group + '_' + verdict] += 1
        if not consistent(record, row, answers[key]):
            inconsistent += 1

        if verdict == 'uncertified':
            categories[vectors[key]['cat'].partition(':')[0]] += 1
            if group == 'graded':
                outside.append({'id': key, 'cat': vectors[key]['cat']})

    return {
        'counts': {key: counts[key] for key in sorted(counts)},
        'uncertified_categories': {key: categories[key] for key in sorted(categories)},
        'inconsistent_with_exact_model': inconsistent,
        'uncertified_graded': outside
    }

def report(vectors: str | pathlib.Path, oracle_path: str | pathlib.Path, directory: str,
           implementations: dict) -> dict:
    """
    Certify the answers of every implementation (a dictionary that maps each
    name to the path of its results file), write the verdicts and the Lean
    inputs to ``directory``, and return the summary of every implementation.
    """
    (rows, expected) = (read(vectors), read(oracle_path))
    result = {'epsilon': str(EPSILON), 'implementations': {}}
    for (name, path) in implementations.items():
        records = run(vectors, oracle_path, path)
        write(directory, name, records)
        result['implementations'][name] = summarize(rows, expected, read(path), records)

    return result

def save(path: str | pathlib.Path, summary: dict) -> None:
    """
    Write a certification summary to a JSON file.
    """
    pathlib.Path(path).write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')

if __name__ == '__main__':
    doctest.testmod() # pragma: no cover
