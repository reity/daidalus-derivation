"""
Tests of the exact model on hand-checked encounters and on samples of the
committed corpus.
"""
import csv
import gzip
import math
import pathlib
import random
from fractions import Fraction

import pytest

from wellclear import oracle, vectors

ROOT = pathlib.Path(__file__).resolve().parent.parent
PHASE_I = vectors.TABLES['P1']

@pytest.fixture(name='corpus', scope='module')
def fixture_corpus():
    with gzip.open(ROOT / 'data' / 'vectors.csv.gz', 'rt', encoding='utf-8', newline='') as file:
        return {row['id']: row for row in csv.DictReader(file)}

def vector(state, window=(0.0, 180.0), table=PHASE_I, identifier='test'):
    return vectors.row((identifier, 'test', 'P1', ''), state, window, table)

def test_head_on_interval_matches_closed_form():
    # Range r(t) = 20000 - 400 t; the modified tau is at most 35 once r^2 - 14000 r - D^2 <= 0.
    (dthr, _, _, _) = PHASE_I
    record = oracle.evaluate(vector(([0, 0, 3000], [200, 0, 0], [20000, 0, 3000], [-200, 0, 0])))
    entry = (20000 - (7000 + math.sqrt(7000 ** 2 + dthr ** 2))) / 400
    assert record['conf_exp'] == 1 and record['viol_exp'] == 0 and record['sc_bad'] == 0
    assert float(record['lo']) == pytest.approx(entry, abs=1e-12)
    assert float(record['hi']) == pytest.approx((20000 + dthr) / 400, abs=1e-12)

def test_exact_tangency_is_on_the_cliff():
    (dthr, _, _, _) = PHASE_I
    state = ([dthr, 2000.0, 3000.0], [0, -100.0, 0], [0, 0, 3000.0], [0, 0, 0])
    record = oracle.evaluate(vector(state))
    assert (record['conf_exp'], record['lo'], float(record['hi'])) == (1, f'{0:.20e}', 20.0)
    assert record['conf_band'] == 'hmd' and record['m_hmd'] == '0.000e+00'
    outside = ([math.nextafter(dthr, math.inf), 2000.0, 3000.0],) + state[1:]
    assert oracle.evaluate(vector(outside))['conf_exp'] == 0

def test_boundary_contact_is_not_a_violation():
    (dthr, _, _, _) = PHASE_I
    record = oracle.evaluate(vector(([dthr, 0, 3000], [0, 75, 0], [0, 0, 3000], [0, 0, 0])))
    assert (record['wcv_now'], record['viol_exp'], record['touch_only']) == (1, 0, 1)

def test_level_flight_snap():
    zthr = PHASE_I[1]
    snapped = ([0, 0, zthr + 1e-12], [100, 0, -5e-14], [3000, 0, 0.0], [-100, 0, 0])
    unsnapped = ([0, 0, zthr + 1e-11], [100, 0, -2e-13], [3000, 0, 0.0], [-100, 0, 0])
    # Under the pure semantics, a vertical speed of -5e-14 m/s closes the remaining 1e-12 m
    # after about 20 s, while the horizontal loss lasts until 21.1 s. The level-flight snap
    # (NUM-1) treats the vertical speed as zero, so the convention changes the decision.
    record = oracle.evaluate(vector(snapped))
    assert (record['exact_conf'], record['conf_exp'], record['conv_gap']) == (1, 0, 'inf')
    assert float(record['exact_lo']) == pytest.approx(19.9, abs=0.1)
    # At -2e-13 m/s (above the snap threshold), the band is reached only after 50 s.
    record = oracle.evaluate(vector(unsnapped))
    assert (record['exact_conf'], record['conf_exp']) == (0, 0)

def test_stationary_snap_refinement(corpus):
    # The vector that led to the refinement of NUM-2: the convention extends the loss to the
    # end of the lookahead, while the exact exit is at 6.9 seconds.
    record = oracle.evaluate(corpus['cst-3915'])
    assert (float(record['lo']), float(record['hi'])) == (0.0, 180.0)
    assert float(record['exact_hi']) == pytest.approx(6.9, abs=0.05)
    assert record['conv_gap'] != '0.0'

def test_symmetry_and_translation(corpus):
    rng = random.Random(0)
    keys = [k for k in corpus if corpus[k]['cat'] in ('sym', 'shift')]
    for key in rng.sample(keys, 40):
        variant = oracle.evaluate(corpus[key])
        base = oracle.evaluate(corpus[corpus[key]['base']])
        assert variant['conf_exp'] == base['conf_exp']
        assert variant['viol_exp'] == base['viol_exp']
        if corpus[key]['cat'] == 'sym': # Exchanging the aircraft negates s and v exactly.
            assert (variant['lo'], variant['hi']) == (base['lo'], base['hi'])

def test_selfcheck_on_corpus_sample(corpus):
    rng = random.Random(1)
    for key in rng.sample(sorted(corpus), 300):
        record = oracle.evaluate(corpus[key])
        if record['valid']:
            assert record['sc_bad'] == 0, key

def test_invalid_vectors(corpus):
    assert oracle.evaluate(corpus['rob-inf_vix#'])['why'] == 'non-finite input'
    assert oracle.evaluate(corpus['rob-bad_DTHR_zero#'])['why'] == 'outside ENV-1/ENV-2 domain'
    assert oracle.evaluate(corpus['rob-bad_B_eq_T#'])['valid'] == 0

def test_sets_agree_with_definitional_predicate():
    rng = random.Random(2)
    p = oracle.thresholds(*PHASE_I)
    for _ in range(200):
        s = (Fraction(rng.uniform(-9000, 9000)), Fraction(rng.uniform(-9000, 9000)))
        v = (Fraction(rng.uniform(-300, 300)), Fraction(rng.uniform(-300, 300)))
        interval = oracle.horizontal_set(s, v, p)
        for t in (Fraction(rng.randrange(-200, 200)), Fraction(rng.randrange(0, 400), 7)):
            x = (s[0] + t * v[0], s[1] + t * v[1])
            inside = interval is not None and interval[0] <= oracle.dec(t) <= interval[1]
            assert oracle.horizontal_condition(x, v, p) == inside
