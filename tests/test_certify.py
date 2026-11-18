"""
Tests of the executable twin of the Lean certificate checker: the sign tests
against the literal requirements, the verdicts on hand-checked encounters, the
input file of the Lean checker, and the committed certification summary.
"""
import csv
import gzip
import json
import pathlib
import random
import struct
from fractions import Fraction

import pytest

from wellclear import certify, oracle

ROOT = pathlib.Path(__file__).resolve().parent.parent
WINDOW = (Fraction(0), Fraction(180))

def encounter(state, table=(1000.0, 100.0, 35.0, 0.0)):
    return oracle.encounter(state, table)

def literal(case, t):
    (s, v, p) = (case['s'], case['v'], case['p'])
    x = [s[i] + t * v[i] for i in range(3)]
    return oracle.horizontal_condition(x[:2], v[:2], p) and \
        oracle.vertical_condition(x[2], v[2], p)

def random_case(rng):
    def number(scale):
        return Fraction(0) if rng.random() < 0.1 else \
            Fraction(rng.randint(-1000, 1000), rng.randint(1, 50)) * scale

    table = oracle.thresholds(rng.choice([1, 2, 3.5, 10]), rng.choice([1, 2, 5]),
                              rng.choice([0, 1, 3.5, 35]), rng.choice([0, 1, 20]))
    v = (number(Fraction(1, 100)), number(Fraction(1, 100)), number(Fraction(1, 100)))
    s = (number(Fraction(1, 20)), number(Fraction(1, 20)), number(Fraction(1, 50)))
    if rng.random() < 0.1 and v[0] != 0: # An exact tangency of the DTHR circle.
        (s, v) = ((s[0], table['dthr'] * rng.choice([1, -1]), s[2]), (v[0], Fraction(0), v[2]))
    return {'s': s, 'v': v, 'p': table}

def test_point_test_is_the_literal_requirement():
    # The sign tests are equivalent to SEM-2 to SEM-4 (pointTest_iff in Lean).
    rng = random.Random(3)
    for _ in range(5000):
        case = random_case(rng)
        t = Fraction(rng.randint(-1000, 1000), rng.randint(1, 20))
        assert certify.point_test(case, t) == literal(case, t)

def test_clear_test_is_sound():
    # A successful test of an interval excludes a violation at every time of the interval
    # (clear_of_clearTest in Lean); sampled at the endpoints and at random times.
    rng = random.Random(4)
    (tested, cleared) = (0, 0)
    for _ in range(3000):
        case = random_case(rng)
        (lo, hi) = sorted(Fraction(rng.randint(-500, 500), rng.randint(1, 10)) for _ in range(2))
        tested += 1
        if certify.clear_test(case, lo, hi):
            cleared += 1
            times = [lo, hi] + [
                lo + (hi - lo) * Fraction(rng.randint(0, 100), 100) for _ in range(5)
            ]
            assert not any(literal(case, t) for t in times)

    assert 0 < cleared < tested

def test_head_on_verdicts():
    case = encounter(([0, 0, 0], [100, 0, 0], [9000, 0, 0], [-100, 0, 0]))
    # The exact interval is [9.2997252767987..., 50].
    assert certify.certify(case, WINDOW, (Fraction('9.2997256'), Fraction(50)), 0) == 'interval'
    assert certify.certify(case, WINDOW, (Fraction('9.299727'), Fraction(50)), 0) == 'uncertified'
    assert certify.certify(case, WINDOW, (Fraction(9), Fraction(51)), 0) == 'uncertified'
    assert certify.certify(case, WINDOW, (Fraction(50), Fraction(9)), 0) == 'uncertified'
    assert certify.certify(case, WINDOW, (None, Fraction(50)), 0) == 'uncertified'
    assert certify.certify(case, WINDOW, None, Fraction(0)) == 'uncertified'
    assert certify.certify(case, (Fraction(0), Fraction(9)), None, Fraction(0)) == 'empty'

def test_single_instant_verdicts():
    # With TTHR = 0, a tangency of the DTHR circle is a violation at the single time 50.
    case = encounter(([5000, 1000, 0], [-100, 0, 0], [0, 0, 0], [0, 0, 0]), (1000.0, 100.0, 0, 0))
    assert [t for t in (Fraction(49), Fraction(50), Fraction(51)) if literal(case, t)] == [50]
    assert certify.certify(case, WINDOW, None, Fraction(50)) == 'short'
    assert certify.certify(case, WINDOW, None, Fraction(40)) == 'uncertified'
    reported = (Fraction('49.9999999'), Fraction('50.0000001'))
    assert certify.certify(case, WINDOW, reported, Fraction(0)) == 'interval'
    assert certify.certify(case, WINDOW, (reported[0], reported[1] + 1), 0) == 'uncertified'

def test_level_and_stationary_verdicts():
    # Level flight at 50 m of vertical separation with no relative horizontal motion.
    inside = encounter(([0, 500, 50], [0, 0, 0], [0, 0, 0], [0, 0, 0]))
    assert certify.certify(inside, WINDOW, (Fraction(0), Fraction(180)), 0) == 'interval'
    outside = encounter(([0, 500, 150], [0, 0, 0], [0, 0, 0], [0, 0, 0]))
    assert certify.certify(outside, WINDOW, None, Fraction(0)) == 'empty'

def test_lean_input_and_domain():
    assert certify.bits('0.1') == struct.pack('>d', 0.1).hex()
    assert certify.LEAN_COLUMNS[0] == 'id' and certify.LEAN_COLUMNS[-4:] == \
        ('conflict', 't_in', 't_out', 'hint')
    with gzip.open(ROOT / 'data' / 'vectors.csv.gz', 'rt', encoding='utf-8', newline='') as file:
        rows = {row['id']: row for row in csv.DictReader(file)}

    record = certify.evaluate((rows['rob-inf_vix#'], {}, {'conflict': '0'}))
    assert record['verdict'] == 'invalid' and record['lean']['vix'] == '7ff0000000000000'
    record = certify.evaluate((rows['cpa-0'], {'exact_lo': ''}, {'conflict': '0'}))
    assert record['verdict'] == 'uncertified' and record['lean']['hint'] == certify.bits('0.0')

def test_consistency_check_detects_disagreement():
    expected = {'exact_lo': '1.0', 'exact_hi': '2.0'}
    answer = {'t_in': '1.0000005', 't_out': '2.0'}
    assert certify.consistent({'verdict': 'interval'}, expected, answer)
    assert not certify.consistent({'verdict': 'interval'}, expected, dict(answer, t_in='1.1'))
    assert not certify.consistent({'verdict': 'empty'}, expected, answer)
    assert certify.consistent({'verdict': 'short'}, {'exact_lo': '1.0', 'exact_hi': '1.000001'}, {})

@pytest.fixture(name='document', scope='module')
def fixture_document():
    return json.loads((ROOT / 'results' / 'certify.json').read_text('utf-8'))

def test_committed_summary(document):
    grades = json.loads((ROOT / 'results' / 'grades.json').read_text('utf-8'))['grades']
    assert document['epsilon'] == str(certify.EPSILON)
    for (name, record) in document['implementations'].items():
        counts = record['counts']
        assert sum(counts[v] for v in certify.VERDICTS) == 58983
        band = sum(counts.get('band_' + v, 0) for v in certify.VERDICTS)
        assert band == grades[name]['band']['n']
        assert counts.get('graded_uncertified', 0) == 0 and not record['uncertified_graded']
        assert record['inconsistent_with_exact_model'] == 0
        assert counts['invalid'] == 63

    assert document['implementations']['rust'] == document['implementations']['js']
