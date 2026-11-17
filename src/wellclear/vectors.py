"""
Generator for the corpus of test vectors on which every implementation is run
and graded.

Each test vector is an encounter (ownship and intruder position and velocity),
a lookahead window, and a table of well-clear thresholds. The corpus contains
the categories listed below; all values are written as shortest round-trip
decimal representations of IEEE 754 double-precision values.

* ``cpa``: realistic encounters built from closest-point-of-approach geometry
  within the operating ranges (ENV-3).
* ``uniform``: a uniform sweep of the operating envelope (mostly no conflict).
* ``cliff_hmd``: horizontal miss distance within a relative margin between
  ``1e-15`` and ``1e-5`` of DTHR (ACC-1).
* ``cliff_level``: level flight with a vertical separation within a relative
  margin between ``1e-15`` and ``1e-5`` of ZTHR (ACC-1, NUM-1).
* ``cliff_static``: zero or tiny relative horizontal speed at a horizontal
  separation near DTHR (ACC-1, NUM-2).
* ``edge:*``: hand-built cases (tangency, boundary contact, snaps, TCOA and
  lookahead corner cases).
* ``sym`` and ``shift``: metamorphic variants of ``cpa`` vectors (SEM-6, SEM-1).
* ``robust:*``: non-finite and out-of-domain inputs (ENV-1, ENV-4, IMP-1).

The generator is deterministic for a given platform. Some categories rely on
the platform's implementations of :obj:`math.sin`, :obj:`math.cos`, and
:obj:`math.pow` (and on the CPython implementation of :obj:`math.hypot`), so
the canonical corpus is committed to the repository. The regeneration check is
only expected to reproduce it bit for bit on the platform on which it was
generated: Linux (x86-64, glibc 2.39) with CPython 3.13.

>>> corpus = rows()
>>> len(corpus)
58983
>>> corpus[0]['id'], corpus[0]['cat'], corpus[0]['table']
('cpa-0', 'cpa', 'P1')
"""
from __future__ import annotations
from typing import Callable, Iterable, Sequence
import collections
import csv
import doctest
import math
import pathlib
import random

KNOT = 1852.0 / 3600.0
"""
One knot in meters per second.
"""

FEET_PER_MINUTE = 0.3048 / 60.0
"""
One foot per minute in meters per second.
"""

FOOT = 0.3048
"""
One foot in meters.
"""

NAUTICAL_MILE = 1852.0
"""
One nautical mile in meters.
"""

TABLES = {
    'P1': (0.66 * NAUTICAL_MILE, 450 * FOOT, 35.0, 0.0),
    'P1P': (0.66 * NAUTICAL_MILE, 700 * FOOT, 35.0, 0.0),
    'P2': (1500 * FOOT, 450 * FOOT, 0.0, 0.0),
    'NC': (2200 * FOOT, 450 * FOOT, 0.0, 0.0),
    'BUF': (1.0 * NAUTICAL_MILE, 450 * FOOT, 35.0, 20.0),
    'BUFP': (1.0 * NAUTICAL_MILE, 750 * FOOT, 35.0, 20.0)
}
"""
Threshold tables (DTHR, ZTHR, TTHR, TCOA) in SI units, computed exactly as the
upstream ``WCVTable`` class computes them (value times unit factor): DO-365 DWC
Phase I (the DAIDALUS default), Phase I preventive, Phase II, non-cooperative,
buffered DWC, and buffered preventive (ENV-3).
"""

TABLE_NAMES = {
    'P1': 'DO-365 DWC Phase I',
    'P1P': 'Phase I preventive',
    'P2': 'Phase II',
    'NC': 'Non-cooperative',
    'BUF': 'Buffered DWC',
    'BUFP': 'Buffered preventive'
}
"""
Descriptive names of the threshold tables.
"""

FIELDS = (
    'sox', 'soy', 'soz', 'vox', 'voy', 'voz', 'six', 'siy', 'siz', 'vix', 'viy', 'viz',
    'B', 'T', 'DTHR', 'ZTHR', 'TTHR', 'TCOA'
)
"""
Numeric columns of a test vector: ownship position and velocity, intruder
position and velocity, lookahead window, and thresholds.
"""

COLUMNS = ('id', 'cat', 'table', 'base') + FIELDS
"""
All columns of a test vector (identifier, category, threshold table name,
identifier of the base vector for metamorphic variants, and numeric columns).
"""

SEED = 20261117
"""
Seed of the pseudorandom generator used for all randomized categories.
"""

def row(meta: Sequence[str], state: Sequence[Sequence[float]], window, thresholds) -> dict:
    """
    Return a test vector as a dictionary of strings, given its identifier,
    category, table name, and base identifier (``meta``), the encounter state
    ``(so, vo, si, vi)``, the lookahead window ``(B, T)``, and the thresholds
    ``(DTHR, ZTHR, TTHR, TCOA)``.

    >>> vector = row(
    ...     ('edge-x', 'edge:x', 'P1', ''),
    ...     ([0, 0, 1], [1, 0, 0], [5, 0, 1], [-1, 0, 0]), (0, 180), TABLES['P1']
    ... )
    >>> vector['soz'], vector['vix'], vector['T'], vector['DTHR']
    ('1.0', '-1.0', '180.0', '1222.3200000000002')
    """
    values = [*state[0], *state[1], *state[2], *state[3], *window, *thresholds]
    vector = dict(zip(('id', 'cat', 'table', 'base'), meta))
    vector.update({k: repr(float(x)) for (k, x) in zip(FIELDS, values)})
    return vector

def velocity(rng: random.Random, level_probability: float = 0.3) -> list[float]:
    """
    Return a random velocity within the operating ranges (ENV-3): ground speed
    between 10 and 700 knots, any track, and either level flight (with the
    supplied probability) or a vertical speed of up to 6000 feet per minute.

    >>> v = velocity(random.Random(1))
    >>> 10 * KNOT <= math.hypot(v[0], v[1]) <= 700 * KNOT
    True
    """
    (speed, track) = (rng.uniform(10, 700) * KNOT, rng.uniform(0, 2 * math.pi))
    climb = 0.0 if rng.random() < level_probability else rng.uniform(-6000, 6000) * FEET_PER_MINUTE
    return [speed * math.sin(track), speed * math.cos(track), climb]

def ownship_position(rng: random.Random) -> list[float]:
    """
    Return a random ownship position within 50 kilometers of the origin and at an
    altitude between 100 and 50,000 feet.

    >>> p = ownship_position(random.Random(1))
    >>> max(abs(p[0]), abs(p[1])) <= 5e4 and 100 * FOOT <= p[2] <= 50000 * FOOT
    True
    """
    return [rng.uniform(-5e4, 5e4), rng.uniform(-5e4, 5e4), rng.uniform(100, 50000) * FOOT]

def lookahead(rng: random.Random) -> tuple[float, float]:
    """
    Return a random lookahead window: the standard ``[0, 180]`` window in 45% of
    cases, a window starting at zero with a shorter end in 30% of cases, and a
    window starting after zero in the remaining cases.

    >>> (b, t) = lookahead(random.Random(1))
    >>> 0 <= b < t
    True
    """
    r = rng.random()
    if r < 0.45:
        return (0.0, 180.0)

    if r < 0.75:
        return (0.0, rng.choice([25.0, 45.0, 55.0, 75.0, rng.uniform(1, 180)]))

    b = rng.uniform(0, 60)
    return (b, b + rng.uniform(1, 180))

def _normal(v: Sequence[float]) -> tuple[float, float]:
    """
    Return the horizontal unit vector perpendicular to a velocity (or a fixed
    unit vector if the velocity has no horizontal component).

    >>> _normal([0.0, 2.0, 0.0]), _normal([0.0, 0.0, 1.0])
    ((-1.0, 0.0), (1.0, 0.0))
    """
    n = math.hypot(v[0], v[1])
    return (-v[1] / n, v[0] / n) if n > 0 else (1.0, 0.0)

def from_cpa(rng: random.Random, geometry: Sequence[float], vo, vi) -> tuple[list, list]:
    """
    Return ownship and intruder positions such that the encounter with the
    supplied velocities has, at time ``tcpa``, a horizontal closest point of
    approach at distance ``hmd`` and a vertical separation ``zc``, where
    ``geometry`` is ``(hmd, tcpa, zc)``.

    >>> (vo, vi) = ([100.0, 0.0, 0.0], [-100.0, 0.0, 0.0])
    >>> (so, si) = from_cpa(random.Random(1), (500.0, 20.0, 0.0), vo, vi)
    >>> s = [so[i] - si[i] + 20.0 * (vo[i] - vi[i]) for i in range(3)]
    >>> round(math.hypot(s[0], s[1]), 6)
    500.0
    """
    (hmd, tcpa, zc) = geometry
    v = [vo[i] - vi[i] for i in range(3)]
    u = _normal(v)
    sign = rng.choice([-1.0, 1.0])
    s = [sign * hmd * u[0] - tcpa * v[0], sign * hmd * u[1] - tcpa * v[1], zc - tcpa * v[2]]
    so = ownship_position(rng)
    si = [so[i] - s[i] for i in range(3)]
    return (so, si)

def tiny_relative(rng: random.Random) -> float:
    """
    Return a random relative perturbation with a magnitude between ``1e-15`` and
    ``1e-5`` (log-uniformly distributed) and a random sign.

    >>> 1e-15 <= abs(tiny_relative(random.Random(1))) <= 1e-5
    True
    """
    return rng.choice([-1.0, 1.0]) * 10 ** rng.uniform(-15, -5)

def cpa(rng: random.Random, count: int) -> Iterable[dict]:
    """
    Yield ``count`` realistic encounters per threshold table, built from
    closest-point-of-approach geometry.

    >>> vectors = list(cpa(random.Random(1), 2))
    >>> [v['id'] for v in vectors[:3]], len(vectors)
    (['cpa-0', 'cpa-1', 'cpa-2'], 12)
    """
    k = 0
    for (table, thresholds) in TABLES.items():
        (dthr, zthr, _, _) = thresholds
        for _ in range(count):
            (vo, vi) = (velocity(rng), velocity(rng))
            hmd = 0.0 if rng.random() < 0.08 else dthr * rng.uniform(0, 2)
            tcpa = rng.uniform(-40, 220)
            zc = rng.uniform(-3 * zthr, 3 * zthr)
            (so, si) = from_cpa(rng, (hmd, tcpa, zc), vo, vi)
            window = lookahead(rng)
            yield row(('cpa-' + str(k), 'cpa', table, ''), (so, vo, si, vi), window, thresholds)
            k += 1

def uniform(rng: random.Random, count: int) -> Iterable[dict]:
    """
    Yield ``count`` encounters per threshold table drawn uniformly from the
    operating envelope (intruder within 20 nautical miles and 5,000 feet).

    >>> [v['id'] for v in uniform(random.Random(1), 1)]
    ['uni-0', 'uni-1', 'uni-2', 'uni-3', 'uni-4', 'uni-5']
    """
    k = 0
    for (table, thresholds) in TABLES.items():
        for _ in range(count):
            so = ownship_position(rng)
            si = [
                so[0] + rng.uniform(-37040, 37040),
                so[1] + rng.uniform(-37040, 37040),
                so[2] + rng.uniform(-1524, 1524)
            ]
            window = lookahead(rng)
            (vo, vi) = (velocity(rng), velocity(rng))
            yield row(('uni-' + str(k), 'uniform', table, ''), (so, vo, si, vi), window, thresholds)
            k += 1

def _cliff_hmd(rng: random.Random, table: str) -> tuple:
    """
    Return the state of an encounter whose horizontal miss distance is at, or
    within a tiny relative margin of, DTHR.
    """
    (dthr, zthr, _, _) = TABLES[table]
    (vo, vi) = (velocity(rng, 0.5), velocity(rng, 0.5))
    delta = 0.0 if rng.random() < 0.1 else tiny_relative(rng)
    tcpa = rng.uniform(5, 150)
    zc = rng.uniform(-zthr / 2, zthr / 2)
    (so, si) = from_cpa(rng, (dthr * (1 + delta), tcpa, zc), vo, vi)
    return (so, vo, si, vi)

def _cliff_level(rng: random.Random, table: str) -> tuple:
    """
    Return the state of a level encounter whose vertical separation is at, or
    within a tiny relative margin of, ZTHR.
    """
    (dthr, zthr, _, _) = TABLES[table]
    (vo, vi) = (velocity(rng, 0.0), velocity(rng, 0.0))
    vi[2] = vo[2] # Relative vertical speed is exactly zero.
    hmd = dthr * rng.uniform(0, 0.5)
    tcpa = rng.uniform(5, 150)
    (so, si) = from_cpa(rng, (hmd, tcpa, 0.0), vo, vi)
    z = zthr * (1 + (0.0 if rng.random() < 0.15 else tiny_relative(rng)))
    if rng.random() < 0.5: # Exact vertical separation (intruder at altitude zero).
        (so[2], si[2]) = (z, 0.0)
    else:
        si[2] = so[2] - rng.choice([-1, 1]) * z

    return (so, vo, si, vi)

def _cliff_static(rng: random.Random, table: str) -> tuple:
    """
    Return the state of an encounter with zero or tiny relative horizontal
    velocity at a horizontal separation at, or near, DTHR.
    """
    (dthr, zthr, _, _) = TABLES[table]
    vo = velocity(rng, 1.0)
    vi = list(vo)
    if rng.random() < 0.3: # Tiny relative motion.
        angle = rng.uniform(0, 2 * math.pi)
        speed = 10 ** rng.uniform(-14, -6)
        vi[0] += speed * math.cos(angle)
        vi[1] += speed * math.sin(angle)

    r = dthr * (1 + (0.0 if rng.random() < 0.15 else tiny_relative(rng)))
    angle = rng.uniform(0, 2 * math.pi)
    so = ownship_position(rng)
    si = [
        so[0] - r * math.cos(angle),
        so[1] - r * math.sin(angle),
        so[2] - rng.uniform(-zthr, zthr) / 2
    ]
    if rng.random() < 0.3: # Exact horizontal separation along an axis.
        (so[0], so[1], si[0], si[1]) = (r, 0.0, 0.0, 0.0)

    return (so, vo, si, vi)

def cliffs(rng: random.Random, counts: Sequence[int]) -> Iterable[dict]:
    """
    Yield encounters at or near the semantic cliffs (ACC-1) for every threshold
    table, where ``counts`` specifies the number of vectors per table in each of
    the categories ``cliff_hmd``, ``cliff_level``, and ``cliff_static``.

    >>> [v['id'] for v in cliffs(random.Random(1), (1, 1, 1))][:4]
    ['chmd-0', 'clev-1', 'cst-2', 'chmd-3']
    """
    generators = (
        ('chmd-', 'cliff_hmd', _cliff_hmd),
        ('clev-', 'cliff_level', _cliff_level),
        ('cst-', 'cliff_static', _cliff_static)
    )
    k = 0
    for (table, thresholds) in TABLES.items():
        for ((prefix, category, generator), count) in zip(generators, counts):
            for _ in range(count):
                meta = (prefix + str(k), category, table, '')
                yield row(meta, generator(rng, table), (0.0, 180.0), thresholds)
                k += 1

def _tangency(dthr: float, z0: float) -> list[tuple]:
    """
    Return the name and state of each tangency edge case: an intruder at rest
    and an ownship moving parallel to the y-axis at a horizontal miss distance
    equal to DTHR or one unit in the last place inside or outside it.
    """
    cases = []
    for y0 in (500.0, 1000.0, 2000.0, 5000.0, 10000.0, 20000.0):
        for w in (50.0, 100.0, 150.5, 200.0, 257.3):
            for (name, x0) in (
                ('tangent_exact', dthr),
                ('tangent_ulp_in', math.nextafter(dthr, 0)),
                ('tangent_ulp_out', math.nextafter(dthr, math.inf))
            ):
                state = ([x0, y0, z0], [0, -w, 0], [0, 0, z0], [0, 0, 0])
                cases.append((name + '#' + str(y0) + '-' + str(w), state))

    return cases

def _boundary(dthr: float, z0: float) -> list[tuple]:
    """
    Return the name and state of each edge case that starts exactly on, or very
    near, the DTHR circle.
    """
    cases = []
    for w in (1.0, 75.0, 300.0):
        for (name, vx, vy) in (('tangential', 0, w), ('converging', -w, 0), ('diverging', w, 0)):
            state = ([dthr, 0, z0], [vx, vy, 0], [0, 0, z0], [0, 0, 0])
            cases.append(('on_circle_' + name + '#' + str(w), state))

    for (name, x0, y0) in (
        ('static_inside', 100, 200),
        ('static_on_boundary', dthr, 0),
        ('static_outside', dthr * 1.0000001, 0)
    ):
        cases.append((name, ([x0, y0, z0], [150, 0, 0], [0, 0, z0], [150, 0, 0])))

    return cases

def _vertical(zthr: float) -> list[tuple]:
    """
    Return the name and state of each edge case that exercises the vertical
    band boundary and the level-flight snap (NUM-1).
    """
    cases = []
    for (name, z, vz) in (
        ('level_at_zthr', zthr, 0),
        ('level_above_zthr', math.nextafter(zthr, math.inf), 0),
        ('tiny_vz_snapped', zthr + 1e-12, -5e-14),
        ('tiny_vz_unsnapped', zthr + 1e-11, -2e-13)
    ):
        cases.append((name, ([0, 0, z], [100, 0, vz], [3000, 0, 0.0], [-100, 0, 0])))

    return cases

def edges() -> list[dict]:
    """
    Return the hand-built edge cases. These do not depend on the pseudorandom
    generator or on the platform's mathematical library.

    >>> vectors = edges()
    >>> len(vectors)
    120
    >>> vectors[0]['id'], vectors[0]['cat']
    ('edge-headon_now', 'edge:headon_now')
    """
    (dthr, zthr, _, _) = TABLES['P1']
    z0 = 3000.0
    headon = ([0, 0, z0], [100, 0, 0], [500, 0, z0], [-100, 0, 0])
    full = (0.0, 180.0)

    # Each case is a name, a state, a lookahead window, and a threshold table.
    cases = [
        ('headon_now', headon, full, 'P1'),
        ('headon_far', ([0, 0, z0], [200, 0, 0], [20000, 0, z0], [-200, 0, 0]), full, 'P1')
    ]
    cases.extend((name, state, full, 'P1') for (name, state) in _tangency(dthr, z0))
    cases.extend( # With TTHR = 0, tangency is a single instant.
        (
            'tangent_tthr0#' + table,
            ([TABLES[table][0], 2000.0, z0], [0, -100.0, 0], [0, 0, z0], [0, 0, 0]),
            full, table
        )
        for table in ('P2', 'NC')
    )
    cases.extend((name, state, full, 'P1') for (name, state) in _boundary(dthr, z0))
    cases.extend((name, state, full, 'P1') for (name, state) in _vertical(zthr))
    cases.extend([
        ('vertical_only', ([100, 0, 1000], [150, 0, -5.08], [0, 0, 0], [150, 0, 0]), full, 'P1'),
        ('tcoa_buffered', ([0, 0, 600], [100, 0, -20.0], [500, 0, 0], [100, 0, 0]), full, 'BUF'),
        (
            'tcoa_buffered_diverging',
            ([0, 0, 600], [100, 0, 20.0], [500, 0, 0], [100, 0, 0]), full, 'BUF'
        ),
        ('short_lookahead', headon, (10.0, 10.000000001), 'P1'),
        ('lookahead_after_exit', headon, (100.0, 180.0), 'P1'),
        ('diverging_inside', ([0, 0, z0], [-300, 0, 0], [800, 0, z0], [300, 0, 0]), full, 'P1'),
        (
            'out_of_envelope_speed',
            ([0, 0, z0], [1500, 0, 0], [200000, 0, z0], [-1500, 0, 0]), full, 'P1'
        ),
        ('far_away', ([0, 0, z0], [100, 0, 0], [1e6, 1e6, z0], [-100, 0, 0]), full, 'P1'),
        (
            'large_coords',
            ([4e6, 4e6, z0], [100, 0, 0], [4e6 + 6000, 4e6 + 900, z0 + 50], [-120, 0, 0]),
            full, 'P1'
        ),
        (
            'crossing_90deg',
            ([0, -8000, z0], [0, 200, 0], [-8000, 0, z0 + 30], [200, 0, -1]), full, 'P1'
        )
    ])
    return [
        row(('edge-' + name, 'edge:' + name.partition('#')[0], table, ''), state, w, TABLES[table])
        for (name, state, w, table) in cases
    ]

def metamorphic(vectors: Iterable[dict], count: int) -> Iterable[dict]:
    """
    Yield ``count`` symmetric variants (ownship and intruder exchanged, SEM-6)
    and then ``count`` shifted variants (common translation and common velocity
    added, SEM-1) of the ``cpa`` vectors among the supplied vectors.

    >>> base = list(cpa(random.Random(1), 1))
    >>> [v['id'] for v in metamorphic(base, 1)]
    ['cpa-0:sym', 'cpa-1:shift']
    """
    originals = [vector for vector in vectors if vector['cat'] == 'cpa']
    rng = random.Random(7)
    for vector in originals[:count]:
        f = [float(vector[k]) for k in FIELDS]
        state = (f[6:9], f[9:12], f[0:3], f[3:6])
        meta = (vector['id'] + ':sym', 'sym', vector['table'], vector['id'])
        yield row(meta, state, f[12:14], f[14:18])

    for vector in originals[count:2 * count]:
        f = [float(vector[k]) for k in FIELDS]
        d = [rng.uniform(-1e5, 1e5), rng.uniform(-1e5, 1e5), rng.uniform(-1e3, 1e3)]
        w = [rng.uniform(-200, 200), rng.uniform(-200, 200), rng.uniform(-10, 10)]
        so = [f[i] + d[i] for i in range(3)]
        vo = [f[3 + i] + w[i] for i in range(3)]
        si = [f[6 + i] + d[i] for i in range(3)]
        vi = [f[9 + i] + w[i] for i in range(3)]
        meta = (vector['id'] + ':shift', 'shift', vector['table'], vector['id'])
        yield row(meta, (so, vo, si, vi), f[12:14], f[14:18])

def _corruptions() -> list[tuple[str, Callable]]:
    """
    Return the named corruptions that turn a valid vector into an invalid one.
    Each corruption is a function that modifies a mutable vector description in
    place.
    """
    corruptions = []

    def assign(key, index, value):
        """
        Return a corruption that assigns a value to an entry of a vector.
        """
        def corrupt(vector):
            """
            Assign the value to the entry.
            """
            vector[key][index] = value
        return corrupt

    slots = [(key, i) for key in ('so', 'vo', 'si', 'vi') for i in range(3)]
    for (bad, tag) in ((math.nan, 'nan'), (math.inf, 'inf'), (-math.inf, 'ninf')):
        for (key, i) in slots:
            corruptions.append((tag + '_' + key + 'xyz'[i], assign(key, i, bad)))
        for (j, name) in enumerate(('DTHR', 'ZTHR', 'TTHR', 'TCOA')):
            corruptions.append((tag + '_' + name, assign('P', j, bad)))
        corruptions.append((tag + '_B', assign('W', 0, bad)))
        corruptions.append((tag + '_T', assign('W', 1, bad)))

    (dthr, zthr, _, _) = TABLES['P1']
    for (j, name, value) in (
        (0, 'DTHR', -dthr), (0, 'DTHR', 0.0), (1, 'ZTHR', -zthr), (1, 'ZTHR', 0.0),
        (2, 'TTHR', -35.0), (3, 'TCOA', -20.0)
    ):
        suffix = 'neg' if value < 0 else 'zero'
        corruptions.append(('bad_' + name + '_' + suffix, assign('P', j, value)))

    corruptions.append(('bad_B_gt_T', assign('W', slice(0, 2), [50.0, 10.0])))
    corruptions.append(('bad_B_eq_T', assign('W', slice(0, 2), [10.0, 10.0])))
    corruptions.append(('bad_B_negative', assign('W', 0, -5.0)))
    return corruptions

def robust() -> list[dict]:
    """
    Return the invalid vectors: a valid encounter (a conflict 10.6 seconds away
    that is also a current violation) with one field made non-finite or out of
    domain.

    >>> vectors = robust()
    >>> len(vectors), vectors[0]['id'], vectors[0]['sox']
    (63, 'rob-nan_sox#', 'nan')
    """
    vectors = []
    for (name, corrupt) in _corruptions():
        vector = {
            'so': [0.0, 0.0, 3000.0], 'vo': [100.0, 0.0, 0.0],
            'si': [3000.0, 0.0, 3000.0], 'vi': [-100.0, 0.0, 0.0],
            'W': [0.0, 180.0], 'P': list(TABLES['P1'])
        }
        corrupt(vector)
        meta = ('rob-' + name + '#', 'robust:' + name, 'P1', '')
        state = (vector['so'], vector['vo'], vector['si'], vector['vi'])
        vectors.append(row(meta, state, vector['W'], vector['P']))

    return vectors

def rows(seed: int = SEED) -> list[dict]:
    """
    Return the complete corpus of test vectors (as dictionaries of strings).
    """
    rng = random.Random(seed)
    vectors = list(cpa(rng, 6000))
    vectors.extend(uniform(rng, 2000))
    vectors.extend(cliffs(rng, (500, 200, 100)))
    vectors.extend(edges())
    vectors.extend(metamorphic(vectors, 3000))
    vectors.extend(robust())
    return vectors

def categories(vectors: Iterable[dict]) -> dict[str, int]:
    """
    Return the number of vectors in each top-level category.

    >>> categories([{'cat': 'edge:a'}, {'cat': 'edge:b'}, {'cat': 'cpa'}])
    {'edge': 2, 'cpa': 1}
    """
    return dict(collections.Counter(vector['cat'].partition(':')[0] for vector in vectors))

def write(path: str | pathlib.Path, vectors: Iterable[dict]) -> None:
    """
    Write test vectors to a CSV file (with LF line endings).
    """
    with open(path, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(vectors)

def read(path: str | pathlib.Path) -> dict[str, dict]:
    """
    Return the rows of a CSV file as a dictionary that maps each row's ``id``
    column to the row.
    """
    with open(path, newline='', encoding='utf-8') as file:
        return {r['id']: r for r in csv.DictReader(file)}

if __name__ == '__main__':
    doctest.testmod() # pragma: no cover
