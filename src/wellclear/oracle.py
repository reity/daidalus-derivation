"""
Executable model (oracle) of the derived requirements, evaluated in exact
arithmetic.

Inputs are IEEE 754 double-precision values. They are converted exactly to
rationals (:obj:`fractions.Fraction`) and predicates are evaluated exactly.
Interval endpoints that involve a square root are computed using decimals with
:obj:`PRECISION` significant digits.

The model has two layers.

* The *meaning* layer (SEM-1 to SEM-6) consists of the definitional predicate
  :obj:`condition_at`, the closed-form violation sets :obj:`horizontal_set` and
  :obj:`vertical_set` (derived from the definitions rather than from the
  DAIDALUS algorithm), and the detection interval computed by :obj:`detect`.
  The :obj:`selfcheck` function cross-checks each interval against the
  definitional predicate at sample times (the property that is proved in PVS as
  ``WCV_taumod_interval_correct``).
* The *convention* layer (SEM-7, SEM-8, NUM-1, NUM-2, ACC-1, and ACC-2)
  determines the expected conflict and violation flags under the DAIDALUS
  conventions and identifies the boundary band of inputs on which any
  floating-point implementation may legitimately decide either way.

The example below evaluates a head-on encounter (closing at 400 meters per
second from 20 kilometers at the same altitude) against the DO-365 DWC Phase I
thresholds. The loss of well-clear begins when the modified tau falls to 35
seconds and ends when the intruder leaves the DTHR circle behind ownship.

>>> table = (0.66 * 1852, 450 * 0.3048, 35.0, 0.0)
>>> case = encounter(([0, 0, 3000], [200, 0, 0], [20000, 0, 3000], [-200, 0, 0]), table)
>>> (found, lo, hi, _) = detect(case, (0.0, 180.0))
>>> (found, round(float(lo), 6), round(float(hi), 6))
(True, 14.735206, 53.0558)
"""
from __future__ import annotations
from typing import Callable, Iterable
import csv
import decimal
from decimal import Decimal
import doctest
from fractions import Fraction
import functools
import math
import multiprocessing
import pathlib
import random
import zlib

from wellclear.vectors import FIELDS

PRECISION = 90
"""
Number of significant decimal digits used for interval endpoints.
"""

INFINITY = Decimal('Infinity')
"""
Positive infinity (an unbounded interval endpoint).
"""

TIE = Decimal('1e-70')
"""
Interval endpoints closer than this are treated as equal.
"""

RHO = Fraction(1, 10 ** 9)
"""
Relative margin around a semantic cliff within which an input belongs to the
boundary band (ACC-1).
"""

EPS_LEN = Decimal('1e-6')
"""
Length (in seconds) below which an exact violation set is short, and gap below
which an exact miss is near (ACC-1).
"""

SNAP = Fraction(1, 10 ** 13)
"""
Threshold of the DAIDALUS ``Util.almost_equals(x, 0)`` comparison (NUM-1, NUM-2).
"""

SNAP_V = Fraction(1, 10 ** 12)
"""
Relative motion below which cliff margins for static and level geometry are
computed.
"""

COLUMNS = (
    'id', 'valid', 'why', 'nonempty', 'lo', 'hi', 'conf_exp', 'conf_band', 'viol_exp',
    'viol_band', 'wcv_now', 'touch_only', 'sc_n', 'sc_bad', 'exact_conf', 'exact_lo',
    'exact_hi', 'conv_gap', 'm_hmd', 'm_level', 'm_static', 'hmd_ratio'
)
"""
Columns of an oracle record (see :obj:`evaluate`).
"""

def _precise(function: Callable) -> Callable:
    """
    Decorator for functions that must evaluate decimal arithmetic with
    :obj:`PRECISION` significant digits regardless of the caller's context.
    """
    @functools.wraps(function)
    def precise(*args, **kwargs):
        with decimal.localcontext() as context:
            context.prec = PRECISION
            return function(*args, **kwargs)

    return precise

def dec(x: float | Fraction | Decimal) -> Decimal:
    """
    Return a decimal representation of a number (exact for decimals and floats
    up to the precision of the current decimal context).

    >>> dec(0.5), dec(Fraction(3, 4))
    (Decimal('0.5'), Decimal('0.75'))
    """
    if isinstance(x, Decimal):
        return x

    if isinstance(x, float):
        x = Fraction(x)

    return Decimal(x.numerator) / Decimal(x.denominator)

def thresholds(dthr: float, zthr: float, tthr: float, tcoa: float) -> dict:
    """
    Return a dictionary of exact rational thresholds.

    >>> thresholds(1.5, 2, 35, 0)['dthr']
    Fraction(3, 2)
    """
    return {'dthr': Fraction(dthr), 'zthr': Fraction(zthr), 'tthr': Fraction(tthr),
            'tcoa': Fraction(tcoa)}

def encounter(state: Iterable, table: Iterable[float]) -> dict:
    """
    Return the exact relative state of an encounter, where ``state`` consists
    of the ownship position and velocity followed by the intruder position and
    velocity, and ``table`` consists of the thresholds DTHR, ZTHR, TTHR, and
    TCOA. Only the relative position and velocity are retained (SEM-1).

    >>> case = encounter(([1, 2, 3], [0, 0, 0], [0.5, 0, 0], [0, 0, -1]), (1, 1, 0, 0))
    >>> [str(x) for x in case['s'] + case['v']]
    ['1/2', '2', '3', '0', '0', '1']
    """
    (so, vo, si, vi) = state
    return {
        's': tuple(Fraction(so[i]) - Fraction(si[i]) for i in range(3)),
        'v': tuple(Fraction(vo[i]) - Fraction(vi[i]) for i in range(3)),
        'p': thresholds(*table)
    }

def horizontal_condition(s: tuple, v: tuple, p: dict) -> bool:
    """
    Return whether the horizontal well-clear violation condition (SEM-2) holds
    for the horizontal relative position ``s`` and velocity ``v``, evaluated
    exactly as stated (without algebraic shortcuts).

    >>> p = thresholds(1000, 100, 35, 0)
    >>> horizontal_condition((Fraction(5000), 0), (Fraction(-200), 0), p)
    True
    >>> horizontal_condition((Fraction(9000), 0), (Fraction(-200), 0), p)
    False
    """
    d2 = p['dthr'] * p['dthr']
    ss = s[0] * s[0] + s[1] * s[1]
    if ss <= d2:
        return True

    sv = s[0] * v[0] + s[1] * v[1]
    vv = v[0] * v[0] + v[1] * v[1]
    tcpa = -sv / vv if vv != 0 else Fraction(0)
    (cx, cy) = (s[0] + tcpa * v[0], s[1] + tcpa * v[1])
    if cx * cx + cy * cy > d2:
        return False

    taumod = (d2 - ss) / sv if sv < 0 else Fraction(-1)
    return 0 <= taumod <= p['tthr']

def vertical_condition(sz: Fraction, vz: Fraction, p: dict) -> bool:
    """
    Return whether the vertical well-clear violation condition (SEM-3) holds
    for the vertical relative position ``sz`` and velocity ``vz``.

    >>> p = thresholds(1000, 100, 35, 20)
    >>> vertical_condition(Fraction(400), Fraction(-20), p)
    True
    >>> vertical_condition(Fraction(400), Fraction(20), p)
    False
    """
    if abs(sz) <= p['zthr']:
        return True

    tcoa = -sz / vz if sz * vz < 0 else Fraction(-1)
    return 0 <= tcoa <= p['tcoa']

def condition_at(case: dict, t: Fraction) -> bool:
    """
    Return whether the well-clear violation predicate (SEM-4) holds at time
    ``t`` along the linear projection of the encounter.

    >>> table = (1000.0, 100.0, 35.0, 0.0)
    >>> case = encounter(([0, 0, 0], [100, 0, 0], [9000, 0, 0], [-100, 0, 0]), table)
    >>> condition_at(case, Fraction(0)), condition_at(case, Fraction(20))
    (False, True)
    """
    (s, v, p) = (case['s'], case['v'], case['p'])
    (x, y, z) = (s[i] + t * v[i] for i in range(3))
    return horizontal_condition((x, y), v[:2], p) and vertical_condition(z, v[2], p)

@_precise
def horizontal_set(s: tuple, v: tuple, p: dict) -> tuple[Decimal, Decimal] | None:
    """
    Return the exact set of times (over the whole real line) at which the
    horizontal condition (SEM-2) holds at ``s + t * v`` as a pair of endpoints,
    or ``None`` if the set is empty.

    The horizontal miss distance (HMD) is constant along the line. If it
    exceeds DTHR, the set is empty. Otherwise, the set is the union of the time
    spent inside the DTHR circle, ``[t1, t2]``, and the converging part in which
    the modified tau is at most TTHR. The latter begins at ``r1``, the smaller
    root of ``|s(t)|^2 + TTHR s(t).v - DTHR^2 = 0``, and ``r1 <= t1``. Hence the
    set is ``[r1, t2]``.

    >>> p = thresholds(1000, 100, 35, 0)
    >>> [round(float(t), 6) for t in horizontal_set((Fraction(-9000), 0), (Fraction(200), 0), p)]
    [9.299725, 50.0]
    """
    d2 = p['dthr'] * p['dthr']
    a = v[0] * v[0] + v[1] * v[1]
    ss = s[0] * s[0] + s[1] * s[1]
    if a == 0:
        return (-INFINITY, INFINITY) if ss <= d2 else None

    cross = s[0] * v[1] - s[1] * v[0]
    if cross * cross > d2 * a: # The squared HMD (cross^2 / a) exceeds DTHR^2.
        return None

    sv = s[0] * v[0] + s[1] * v[1]
    disc_c = d2 * a - cross * cross # Equal to sv^2 - a (ss - DTHR^2) >= 0.
    t2 = (-dec(sv) + dec(disc_c).sqrt()) / dec(a)
    b = 2 * sv + p['tthr'] * a
    c = ss + p['tthr'] * sv - d2
    disc_t = b * b - 4 * a * c # Equal to 4 disc_c + TTHR^2 a^2 >= 0.
    r1 = (-dec(b) - dec(disc_t).sqrt()) / (2 * dec(a))
    return (r1, t2)

@_precise
def vertical_set(sz: Fraction, vz: Fraction, p: dict) -> tuple[Decimal, Decimal] | None:
    """
    Return the exact set of times (over the whole real line) at which the
    vertical condition (SEM-3) holds at ``sz + t * vz`` as a pair of
    endpoints, or ``None`` if the set is empty. The converging side of the band
    extends to ``|vz| * TCOA``.

    >>> p = thresholds(1000, 100, 35, 20)
    >>> [float(t) for t in vertical_set(Fraction(600), Fraction(-20), p)]
    [10.0, 35.0]
    """
    if vz == 0:
        return (-INFINITY, INFINITY) if abs(sz) <= p['zthr'] else None

    act = max(p['zthr'], abs(vz) * p['tcoa'])
    if vz > 0: # The vertical separation must lie in [-act, ZTHR].
        return (dec((-act - sz) / vz), dec((p['zthr'] - sz) / vz))

    # The vertical separation must lie in [-ZTHR, act].
    return (dec((act - sz) / vz), dec((-p['zthr'] - sz) / vz))

@_precise
def detect(case: dict, window: tuple[float, float], conventions: bool = False) -> tuple:
    """
    Return the exact detection interval (SEM-5) of an encounter within the
    lookahead window ``(B, T)`` as a tuple ``(nonempty, lo, hi, gap)``, where
    ``gap`` is the distance by which a nonempty interval was missed (defined
    only when both the horizontal and vertical sets are nonempty).

    If ``conventions`` is ``True``, the DAIDALUS numerical conventions are
    applied before the exact evaluation: a relative vertical speed below
    ``1e-13`` is treated as zero (NUM-1), and if the squared relative
    horizontal speed is below ``1e-13`` and the aircraft are horizontally
    within DTHR at the start of the vertical window, the horizontal condition
    holds for the whole window (NUM-2).

    >>> table = (1000.0, 100.0, 35.0, 0.0)
    >>> state = ([0, 0, 0], [100, 0, 0], [9000, 0, 0], [-100, 0, 0])
    >>> (found, lo, hi, gap) = detect(encounter(state, table), (0.0, 30.0))
    >>> (found, round(float(lo), 6), float(hi), gap)
    (True, 9.299725, 30.0, Decimal('0'))
    """
    (s, v, p) = (case['s'], case['v'], case['p'])
    vz = Fraction(0) if conventions and abs(v[2]) < SNAP else v[2]
    vs = vertical_set(s[2], vz, p)
    hs = horizontal_set(s[:2], v[:2], p)
    if conventions and vs is not None and v[0] * v[0] + v[1] * v[1] < SNAP:
        tv = Fraction(str(max(dec(window[0]), vs[0]))) if vs[0] != -INFINITY else \
            Fraction(window[0])
        (x, y) = (s[0] + tv * v[0], s[1] + tv * v[1])
        if x * x + y * y <= p['dthr'] * p['dthr']:
            hs = (-INFINITY, INFINITY)

    if hs is None or vs is None:
        return (False, None, None, None)

    lo = max(dec(window[0]), hs[0], vs[0])
    hi = min(dec(window[1]), hs[1], vs[1])
    if lo <= hi + TIE:
        return (True, lo, max(lo, hi), Decimal(0))

    return (False, None, None, lo - hi)

def margins(case: dict) -> dict[str, Fraction]:
    """
    Return the relative distances of an encounter from each reachable semantic
    cliff (ACC-1): the horizontal miss distance from DTHR (``hmd``), the
    horizontal separation from DTHR when there is no relative horizontal
    motion (``static``), the vertical separation from ZTHR in level flight
    (``level``), and the relative motion from a snap threshold
    (``snap-threshold``).

    >>> table = (1000.0, 100.0, 35.0, 0.0)
    >>> margins(encounter(([0, 1000, 0], [100, 0, 0], [9000, 0, 0], [-100, 0, 0]), table))
    {'hmd': Fraction(0, 1), 'level': Fraction(1, 1)}
    """
    (s, v, p) = (case['s'], case['v'], case['p'])
    d2 = p['dthr'] * p['dthr']
    a = v[0] * v[0] + v[1] * v[1]
    ss = s[0] * s[0] + s[1] * s[1]
    result = {}
    if a != 0:
        cross = s[0] * v[1] - s[1] * v[0]
        result['hmd'] = abs(cross * cross / a - d2) / d2

    if a < SNAP_V:
        result['static'] = abs(ss - d2) / d2

    if abs(v[2]) < SNAP_V:
        result['level'] = abs(abs(s[2]) - p['zthr']) / p['zthr']

    if a != 0 and abs(a - SNAP) / SNAP < 1:
        result['snap-threshold'] = abs(a - SNAP) / SNAP

    if v[2] != 0 and abs(abs(v[2]) - SNAP) / SNAP < 1:
        result['snap-threshold'] = min(
            result.get('snap-threshold', 1),
            abs(abs(v[2]) - SNAP) / SNAP
        )

    return result

@_precise
def band_reasons(margin: dict, detection: tuple) -> list[str]:
    """
    Return the reasons (if any) for which an encounter with the supplied cliff
    margins and exact detection result belongs to the boundary band (ACC-1).

    >>> band_reasons({'hmd': Fraction(1, 10 ** 12)}, (False, None, None, None))
    ['hmd']
    >>> band_reasons({}, (True, Decimal('1'), Decimal('1.0000001'), Decimal(0)))
    ['short']
    """
    (nonempty, lo, hi, gap) = detection
    reasons = [key for (key, value) in margin.items() if value < RHO]
    if nonempty and hi - lo < EPS_LEN:
        reasons.append('short')

    if not nonempty and gap is not None and gap < EPS_LEN:
        reasons.append('near-miss')

    return reasons

@_precise
def selfcheck(case: dict, window: tuple, detection: tuple, rng: random.Random) -> tuple:
    """
    Compare the definitional predicate with membership in an exact detection
    interval at sample times within the lookahead window (both window endpoints,
    the midpoint, points one nanosecond on either side of each interval
    endpoint, and two random times). Return the number of samples and the
    number of disagreements.

    >>> table = (1000.0, 100.0, 35.0, 0.0)
    >>> case = encounter(([0, 0, 0], [100, 0, 0], [9000, 0, 0], [-100, 0, 0]), table)
    >>> selfcheck(case, (0.0, 30.0), detect(case, (0.0, 30.0)), random.Random(0))
    (8, 0)
    """
    (b, t) = (Fraction(window[0]), Fraction(window[1]))
    (nonempty, lo, hi, _) = detection
    times = [b, t, (b + t) / 2]
    if nonempty:
        for endpoint in (Fraction(str(lo)), Fraction(str(hi))):
            times += [endpoint - Fraction(1, 10 ** 9), endpoint + Fraction(1, 10 ** 9)]

    times += [b + (t - b) * Fraction(rng.randrange(1, 10 ** 6), 10 ** 6) for _ in range(2)]
    (samples, failures) = (0, 0)
    for time in times:
        if b <= time <= t:
            samples += 1
            member = nonempty and (lo - TIE <= dec(time) <= hi + TIE)
            if condition_at(case, time) != member:
                failures += 1

    return (samples, failures)

def _invalid(values: list[float]) -> str | None:
    """
    Return the reason for which a vector lies outside the domain of the model
    (ENV-1, ENV-2, ENV-4), or ``None`` if it lies inside the domain.
    """
    if not all(math.isfinite(x) for x in values):
        return 'non-finite input'

    (b, t, dthr, zthr, tthr, tcoa) = values[12:]
    thresholds_valid = dthr > 0 and zthr > 0 and tthr >= 0 and tcoa >= 0
    if not thresholds_valid or not 0 <= b < t:
        return 'outside ENV-1/ENV-2 domain'

    return None

def _conflict(detection: tuple) -> bool:
    """
    Return whether a detection result is a conflict, which requires a
    violation set of positive length (SEM-7).
    """
    return bool(detection[0] and detection[2] > detection[1])

def _endpoint(detection: tuple, index: int) -> str:
    """
    Return the formatted endpoint of a detection result (empty if there is no
    interval).
    """
    return f'{float(detection[index]):.20e}' if detection[0] else ''

def _gap(found: tuple, exact: tuple) -> float:
    """
    Return how far the conventions move the detection interval relative to the
    pure exact semantics (infinite if they change the conflict decision).
    """
    if _conflict(found) and _conflict(exact):
        return float(max(abs(found[1] - exact[1]), abs(found[2] - exact[2])))

    if _conflict(found) != _conflict(exact):
        return math.inf

    return 0.0

def _hmd_ratio(case: dict) -> str:
    """
    Return the ratio of the horizontal miss distance to DTHR as a string (empty
    if there is no relative horizontal motion).
    """
    (s, v) = (case['s'], case['v'])
    a = v[0] * v[0] + v[1] * v[1]
    if a == 0:
        return ''

    cross = s[0] * v[1] - s[1] * v[0]
    return repr(math.sqrt(float(cross * cross / a)) / float(case['p']['dthr']))

@_precise
def evaluate(row: dict) -> dict:
    """
    Return the oracle record for a test vector (a dictionary of strings with
    the columns :obj:`~wellclear.vectors.COLUMNS`). The record has the columns
    :obj:`COLUMNS`:

    * ``valid`` and ``why`` indicate whether the vector is in the domain of the
      model and, if not, why;
    * ``nonempty``, ``lo``, and ``hi`` describe the exact detection interval
      with the DAIDALUS conventions applied;
    * ``conf_exp``, ``viol_exp``, and ``wcv_now`` are the expected conflict
      flag (SEM-7), violation flag (SEM-8), and value of the definitional
      predicate at time zero, and ``touch_only`` indicates boundary contact at
      time zero that is not a violation;
    * ``conf_band`` and ``viol_band`` list the reasons (if any) for which the
      conflict and violation decisions lie in the boundary band (ACC-1);
    * ``sc_n`` and ``sc_bad`` are the number of self-check samples and
      disagreements;
    * ``exact_conf``, ``exact_lo``, and ``exact_hi`` describe the detection
      result under the pure exact semantics, and ``conv_gap`` is the distance
      between the two results; and
    * ``m_hmd``, ``m_level``, ``m_static``, and ``hmd_ratio`` are cliff margins
      and the ratio of the horizontal miss distance to DTHR.

    >>> vector = dict(zip(FIELDS, ['0', '0', '0', '100', '0', '0', '9000', '0', '0',
    ...     '-100', '0', '0', '0', '180', '1000', '100', '35', '0']), id='x')
    >>> record = evaluate(vector)
    >>> record['conf_exp'], record['hi'], record['viol_exp'], record['sc_bad']
    (1, '5.00000000000000000000e+01', 0, 0)
    >>> evaluate(dict(vector, B='nan'))['why']
    'non-finite input'
    """
    values = [float(row[k]) for k in FIELDS]
    reason = _invalid(values)
    if reason is not None:
        return {'id': row['id'], 'valid': 0, 'why': reason}

    case = encounter((values[0:3], values[3:6], values[6:9], values[9:12]), values[14:18])
    window = (values[12], values[13])
    exact = detect(case, window) # Pure semantics.
    found = detect(case, window, conventions=True) # Semantics with NUM-1 and NUM-2.
    margin = margins(case)

    # A violation is a conflict on [0, 1] that starts at 0 (SEM-8).
    now = detect(case, (0.0, 1.0), conventions=True)
    violation = bool(now[0] and now[1] == 0 and now[2] > 0)
    violation_band = band_reasons(margin, now)
    if now[0] and Decimal(0) < now[1] < EPS_LEN:
        violation_band.append('starts-near-0')

    current = condition_at(case, Fraction(0))
    (samples, failures) = selfcheck( # Checks the pure semantics.
        case, window, exact, random.Random(zlib.crc32(row['id'].encode()))
    )
    return {
        'id': row['id'], 'valid': 1, 'nonempty': int(found[0]),
        'lo': _endpoint(found, 1), 'hi': _endpoint(found, 2),
        'conf_exp': int(_conflict(found)), 'conf_band': ';'.join(band_reasons(margin, found)),
        'viol_exp': int(violation), 'viol_band': ';'.join(violation_band),
        'wcv_now': int(current), 'touch_only': int(current and not violation),
        'sc_n': samples, 'sc_bad': failures, 'exact_conf': int(_conflict(exact)),
        'exact_lo': _endpoint(exact, 1), 'exact_hi': _endpoint(exact, 2),
        'conv_gap': repr(_gap(found, exact)),
        'm_hmd': f"{float(margin['hmd']):.3e}" if 'hmd' in margin else '',
        'm_level': f"{float(margin['level']):.3e}" if 'level' in margin else '',
        'm_static': f"{float(margin['static']):.3e}" if 'static' in margin else '',
        'hmd_ratio': _hmd_ratio(case)
    }

def run(source: str | pathlib.Path, target: str | pathlib.Path, processes=None) -> list[dict]:
    """
    Evaluate every test vector in the CSV file ``source`` (in parallel, using
    the specified number of processes or one per processor by default), write
    the oracle records to the CSV file ``target``, and return the records.
    """
    with open(source, newline='', encoding='utf-8') as file:
        rows = list(csv.DictReader(file))

    with multiprocessing.Pool(processes) as pool:
        records = pool.map(evaluate, rows, chunksize=200)

    with open(target, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, restval='', lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)

    return records

if __name__ == '__main__':
    doctest.testmod() # pragma: no cover
