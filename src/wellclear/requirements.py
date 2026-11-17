"""
Requirements derived from the DAIDALUS well-clear detection component
(``WCV_TAUMOD`` together with ``WCV_TCOA``) at a pinned upstream commit.

Each requirement records the upstream source lines from which it was derived,
its relationship to the PVS specification published alongside DAIDALUS, and the
checks that verify it. This module is the single source of truth for the
requirements: the files ``derivation/requirements.json`` (consumed by the
results summary and the interactive page) and ``derivation/requirements.md``
(the human-readable version) are generated from it.

>>> len(REQUIREMENTS)
24
>>> [r['id'] for r in REQUIREMENTS if r['kind'] == 'improvement']
['IMP-1', 'IMP-2', 'IMP-3']
"""
from __future__ import annotations
from typing import Iterable
import doctest
import json
import pathlib

UPSTREAM_REPOSITORY = 'https://github.com/nasa/daidalus'
"""
Upstream repository from which the requirements were derived.
"""

UPSTREAM_COMMIT = '1c7b58e5525d5cca91cbbf4a8b7337a488243769'
"""
Upstream commit (dated 2025-05-06) at which the requirements were derived.
"""

UPSTREAM_COMMIT_DATE = '2025-05-06'
"""
Date of the upstream commit.
"""

JAVA_SOURCE_ROOT = 'Java/src/gov/nasa/larcfm/'
"""
Upstream directory relative to which Java source locations are expressed.
"""

KINDS = {
    'interface': 'Interface',
    'envelope': 'Operating Envelope',
    'semantic': 'Semantics',
    'numerical': 'Numerical Conventions',
    'accuracy': 'Accuracy Envelope',
    'performance': 'Performance',
    'improvement': 'Requested Improvements'
}
"""
Requirement kinds (in the order in which they are presented) and their titles.
"""

RELATIONSHIPS = {
    'agrees': 'same meaning as the PVS specification in exact real arithmetic',
    'convention': 'implementation convention that the PVS specification does not have',
    'assumption': 'precondition the PVS specification states but the code does not enforce',
    'n/a': 'outside the scope of the PVS specification'
}
"""
Possible relationships between a requirement and the PVS specification.
"""

METHODS = {
    'oracle': 'exact model',
    'diff': 'differential testing',
    'meta': 'metamorphic testing',
    'fuzz': 'fuzzing',
    'bench': 'benchmark',
    'inspect': 'inspection'
}
"""
Verification methods that may be associated with a requirement.
"""

REQUIREMENTS = (
    {
        'id': 'IF-1', 'kind': 'interface',
        'title': 'Inputs and outputs',
        'text':
            'Inputs: ownship and intruder position/velocity (so, vo, si, vi) as 3-vectors in '
            'a local Euclidean frame (m, m/s); lookahead bounds B, T (s); thresholds DTHR, '
            'ZTHR (m), TTHR, TCOA (s). Outputs: detection interval [t_in, t_out] within '
            '[B, T], or the empty encoding (+inf, -inf); a conflict flag; a violation flag.',
        'code': [
            'ACCoRD/WCV_tvar.java:128-130',
            'ACCoRD/ConflictData.java:45-46',
            'ACCoRD/Detection3D.java:39-62'
        ],
        'pvs': 'WCV.WCV_interval, WCV.WCV_detection', 'rel': 'agrees',
        'verify': ['inspect', 'diff']
    },
    {
        'id': 'ENV-1', 'kind': 'envelope',
        'title': 'Threshold domain',
        'text':
            'DTHR, ZTHR > 0 and TTHR, TCOA >= 0. The code does not reject other values: every '
            'setter and the 4-argument constructor silently replace a threshold by its '
            'absolute value, and zero is accepted.',
        'code': ['ACCoRD/WCVTable.java:52-56', 'ACCoRD/WCVTable.java:197-246'],
        'pvs': 'theory parameters WCV[TTHR,TCOA:nnreal, DTHR,ZTHR:posreal]',
        'rel': 'assumption',
        'verify': ['inspect', 'fuzz']
    },
    {
        'id': 'ENV-2', 'kind': 'envelope',
        'title': 'Lookahead domain',
        'text':
            'Interval detection assumes 0 <= B < T. B almost equal to T is an instantaneous '
            'check evaluated on [B, B+1]; B > T returns no conflict.',
        'code': ['ACCoRD/WCV_tvar.java:139', 'ACCoRD/Detection3D.java:53-61'],
        'pvs': 'WCV.WCV_detection (B=T, B>T cases)', 'rel': 'agrees',
        'verify': ['inspect', 'diff']
    },
    {
        'id': 'ENV-3', 'kind': 'envelope',
        'title': 'Operating ranges and threshold tables',
        'text':
            'Horizontal speed 10-700 kt, vertical speed +/-6000 fpm, altitude 100-50,000 ft, '
            'lookahead 180 s. Threshold tables in use: DO-365 DWC Phase I (0.66 nmi / 450 ft '
            '/ 35 s / 0 s), Phase I preventive (700 ft), Phase II (1500 ft / 450 ft / 0 s), '
            'non-cooperative (2200 ft / 450 ft / 0 s), buffered DWC and preventive (1.0 nmi / '
            '450 or 750 ft / 35 s / TCOA 20 s).',
        'code': ['Configurations/DO_365B_no_SUM.conf', 'ACCoRD/WCVTable.java:101-137'],
        'pvs': 'n/a', 'rel': 'n/a',
        'verify': ['oracle', 'diff']
    },
    {
        'id': 'ENV-4', 'kind': 'envelope',
        'title': 'Finite inputs',
        'text':
            'Positions, velocities, thresholds and lookahead are assumed finite. Nothing in '
            'the component checks this; behavior on NaN or infinity is unspecified and is '
            'measured by the fuzz check.',
        'code': ['(absence of any check)'],
        'pvs': 'reals only', 'rel': 'assumption',
        'verify': ['fuzz']
    },
    {
        'id': 'SEM-1', 'kind': 'semantic',
        'title': 'Only relative state matters',
        'text':
            'All outputs depend only on s = so - si and v = vo - vi (translating both '
            'aircraft, or adding the same velocity to both, changes nothing).',
        'code': ['ACCoRD/WCV_tvar.java:144-151'],
        'pvs': 'WCV(s, v) is stated on relative vectors', 'rel': 'agrees',
        'verify': ['meta', 'oracle']
    },
    {
        'id': 'SEM-2', 'kind': 'semantic',
        'title': 'Horizontal well-clear violation (modified tau)',
        'text':
            '|s_h|^2 <= D^2, or (HMD^2 <= D^2 and 0 <= taumod <= TTHR), where HMD^2 = '
            '|s_h + tcpa*v_h|^2, tcpa = -(s_h.v_h)/|v_h|^2 (0 if v_h = 0), and taumod = '
            '(D^2 - |s_h|^2)/(s_h.v_h) if s_h.v_h < 0, else -1.',
        'code': [
            'ACCoRD/WCV_tvar.java:116-123',
            'ACCoRD/WCV_TAUMOD.java:86-93',
            'ACCoRD/Horizontal.java:65-81'
        ],
        'pvs': 'horizontal_WCV.horizontal_WCV, horizontal_WCV_taumod.taumod, '
               'tcas_tau.tau_mod_def',
        'rel': 'agrees',
        'verify': ['oracle', 'diff']
    },
    {
        'id': 'SEM-3', 'kind': 'semantic',
        'title': 'Vertical well-clear violation',
        'text': '|sz| <= ZTHR, or 0 <= tcoa <= TCOA where tcoa = -sz/vz if sz*vz < 0, else -1.',
        'code': ['ACCoRD/WCV_TCOA.java:18-22'],
        'pvs': 'vertical_WCV.vertical_WCV, timevars.tcoa', 'rel': 'agrees',
        'verify': ['oracle', 'diff']
    },
    {
        'id': 'SEM-4', 'kind': 'semantic',
        'title': 'Well-clear violation is horizontal and vertical violation',
        'text':
            'WCV(s, v) holds if and only if the horizontal (SEM-2) and vertical (SEM-3) '
            'conditions both hold.',
        'code': ['ACCoRD/WCV_tvar.java:153-170'],
        'pvs': 'WCV.WCV', 'rel': 'agrees',
        'verify': ['oracle']
    },
    {
        'id': 'SEM-5', 'kind': 'semantic',
        'title': 'Detection interval is exact',
        'text':
            'For 0 <= B < T and every t in [B, T]: WCV(s + t*v, v) holds if and only if '
            't_in <= t <= t_out. The endpoints are themselves violation times (closed '
            'interval).',
        'code': [
            'ACCoRD/WCV_tvar.java:140-170',
            'ACCoRD/WCV_TAUMOD.java:95-124',
            'ACCoRD/WCV_TCOA.java:25-46'
        ],
        'pvs': 'WCV_taumod.WCV_taumod_interval_correct (proved in PVS for real arithmetic)',
        'rel': 'agrees',
        'verify': ['oracle', 'diff']
    },
    {
        'id': 'SEM-6', 'kind': 'semantic',
        'title': 'Symmetry',
        'text': 'Exchanging ownship and intruder does not change any output.',
        'code': ['(consequence of SEM-2/3: both are invariant under (s, v) -> (-s, -v))'],
        'pvs': 'WCV_taumod.WCV_taumod_symmetric', 'rel': 'agrees',
        'verify': ['meta']
    },
    {
        'id': 'SEM-7', 'kind': 'semantic',
        'title': 'Conflict flag suppresses near-instantaneous loss',
        'text':
            'conflict <=> t_in < t_out and t_in, t_out are not almost-equal (within 16348 '
            'ULPs, or both within 1e-13 of zero). The PVS detection function reports a '
            'conflict even when the violation set is a single instant; the code deliberately '
            'does not.',
        'code': ['Util/LossData.java:44-45', 'Util/Util.java:226-267'],
        'pvs': 'differs from WCV.WCV_detection at single-instant contacts',
        'rel': 'convention',
        'verify': ['oracle', 'diff']
    },
    {
        'id': 'SEM-8', 'kind': 'semantic',
        'title': 'Violation flag is derived from detection on [0, 1]',
        'text':
            'violation <=> detection on [0, 1] reports a conflict whose t_in is almost 0. '
            'Consequence: a state that touches the well-clear boundary only at t = 0 (for '
            'example exactly at DTHR and moving away) is not a violation, although WCV(s, v) '
            'holds at that instant.',
        'code': ['ACCoRD/Detection3D.java:39-41', 'ACCoRD/Detection3D.java:53-57'],
        'pvs': 'differs from WCV(s, v) on the boundary set', 'rel': 'convention',
        'verify': ['oracle', 'diff']
    },
    {
        'id': 'NUM-1', 'kind': 'numerical',
        'title': 'Level-flight snap',
        'text': 'A relative vertical speed with |vz| < 1e-13 m/s is treated as exactly zero.',
        'code': [
            'ACCoRD/WCV_TCOA.java:20',
            'ACCoRD/WCV_TCOA.java:28-30',
            'Util/Util.java:232-241'
        ],
        'pvs': 'PVS uses vz = 0 exactly', 'rel': 'convention',
        'verify': ['diff', 'oracle']
    },
    {
        'id': 'NUM-2', 'kind': 'numerical',
        'title': 'Stationary-geometry snap',
        'text':
            'If |v_h|^2 < 1e-13 m^2/s^2 and |s_h| <= DTHR at the start of the vertical '
            'window, relative horizontal motion is treated as zero and the horizontal '
            'condition holds for the whole window. Consequence: when |s_h| is within about '
            'sqrt(1e-13)*T (6e-5 m for T = 180 s) of DTHR and the aircraft drift apart, the '
            'reported exit time can be later than the exact one by up to the whole lookahead. '
            'Preserved as a convention for drop-in equivalence.',
        'code': ['ACCoRD/WCV_TAUMOD.java:104-108', 'ACCoRD/WCV_tvar.java:158-166'],
        'pvs': 'PVS uses a = 0 exactly', 'rel': 'convention',
        'verify': ['diff', 'oracle'],
        'history':
            'Refined after oracle run 1: the first version stated the snap but not its '
            'consequence; the exact oracle found 2 of 600 near-stationary vectors where '
            'DAIDALUS reported 180 s of violation against an exact exit at 6.9 s and 175 s.'
    },
    {
        'id': 'NUM-3', 'kind': 'numerical',
        'title': 'Closed boundaries',
        'text':
            'Every threshold comparison is <=, so boundary points are inside the well-clear '
            'violation volume.',
        'code': ['ACCoRD/WCV_tvar.java:117-121', 'ACCoRD/WCV_TCOA.java:19'],
        'pvs': 'same (<= throughout)', 'rel': 'agrees',
        'verify': ['oracle', 'diff']
    },
    {
        'id': 'NUM-4', 'kind': 'numerical',
        'title': 'Tangency tolerance in the circle-exit root',
        'text':
            'When the circle-exit discriminant is within 16348 ULPs of zero it is treated as '
            'zero (tangent) instead of producing NaN.',
        'code': ['ACCoRD/Horizontal.java:129-134', 'Util/Util.java:421-433'],
        'pvs': 'PVS root is exact', 'rel': 'convention',
        'verify': ['diff']
    },
    {
        'id': 'ACC-1', 'kind': 'accuracy',
        'title': 'Semantic cliffs are a declared boundary band',
        'text':
            'The conflict decision is discontinuous at HMD = DTHR (the horizontal interval '
            'jumps from length TTHR to empty), at |s_h| = DTHR with zero relative horizontal '
            'velocity, and at |sz| = ZTHR in level flight. Inputs within relative margin 1e-9 '
            'of a cliff, or whose exact violation set is shorter than 1e-6 s (or misses by '
            'less than 1e-6 s), or that sit on a 1e-13 snap threshold (NUM-1/NUM-2), are '
            'boundary-band: any answer is accepted but recorded. Outside the band, answers '
            'are graded against the exact semantics with the NUM-1/NUM-2 conventions applied.',
        'code': ['(derived by analysis of SEM-2/3; not stated in code or PVS)'],
        'pvs': 'n/a (exact reals have no rounding)', 'rel': 'n/a',
        'verify': ['oracle'],
        'history':
            'Refined after oracle run 1: grading now applies the NUM-1/NUM-2 conventions, and '
            'the pure exact semantics is kept alongside so the convention gap is reported '
            'rather than hidden.'
    },
    {
        'id': 'ACC-2', 'kind': 'accuracy',
        'title': 'Accuracy outside the band',
        'text':
            'Outside the boundary band, conflict and violation decisions equal the exact '
            'semantics (SEM-2..8) and interval endpoints are within 1e-6 s of the exact '
            'endpoints.',
        'code': ['(acceptance criterion chosen for this thread)'],
        'pvs': 'n/a', 'rel': 'n/a',
        'verify': ['oracle']
    },
    {
        'id': 'PERF-1', 'kind': 'performance',
        'title': 'Constant time',
        'text':
            'Closed-form evaluation: no loops or iteration; cost per call is independent of '
            'the inputs.',
        'code': ['ACCoRD/WCV_TAUMOD.java:95-124', 'ACCoRD/WCV_TCOA.java:25-46'],
        'pvs': 'n/a', 'rel': 'n/a',
        'verify': ['inspect', 'bench']
    },
    {
        'id': 'PERF-2', 'kind': 'performance',
        'title': 'Throughput no worse than the original',
        'text':
            'Single-thread calls per second on the same vectors must be at least the '
            "original's.",
        'code': ['(measured baseline)'],
        'pvs': 'n/a', 'rel': 'n/a',
        'verify': ['bench']
    },
    {
        'id': 'IMP-1', 'kind': 'improvement',
        'title': 'Explicit errors instead of silent answers',
        'text':
            'Reject non-finite inputs, out-of-domain thresholds and malformed lookahead with '
            'an explicit error (the original sanitizes or silently computes; see ENV-1, '
            'ENV-4).',
        'code': ['(requested improvement; not derived)'],
        'pvs': 'n/a', 'rel': 'n/a',
        'verify': ['fuzz']
    },
    {
        'id': 'IMP-2', 'kind': 'improvement',
        'title': 'Memory-safe, panic-free',
        'text': 'No unsafe code; no panic for any input bit pattern.',
        'code': ['(requested improvement; not derived)'],
        'pvs': 'n/a', 'rel': 'n/a',
        'verify': ['fuzz', 'inspect']
    },
    {
        'id': 'IMP-3', 'kind': 'improvement',
        'title': 'No heap allocation per call',
        'text':
            'The hot path allocates nothing (the original allocates vector and interval '
            'objects on every call).',
        'code': ['(requested improvement; not derived)'],
        'pvs': 'n/a', 'rel': 'n/a',
        'verify': ['bench']
    }
)
"""
Derived requirements, in presentation order. Source locations are relative to
the upstream directory :obj:`JAVA_SOURCE_ROOT` unless they begin with
``Configurations/`` (relative to the upstream repository root); entries in
parentheses describe a requirement that has no single source location.
"""

def source_url(location: str) -> str | None:
    """
    Return the upstream URL (at the pinned commit) of a source location of the
    form ``path`` or ``path:line`` or ``path:first-last``, or ``None`` if the
    entry does not refer to a source location.

    >>> source_url('ACCoRD/WCV_TCOA.java:18-22').endswith(
    ...     '/Java/src/gov/nasa/larcfm/ACCoRD/WCV_TCOA.java#L18-L22'
    ... )
    True
    >>> source_url('ACCoRD/WCV_tvar.java:139').endswith('WCV_tvar.java#L139')
    True
    >>> source_url('Configurations/DO_365B_no_SUM.conf').endswith(
    ...     '/1c7b58e5525d5cca91cbbf4a8b7337a488243769/Configurations/DO_365B_no_SUM.conf'
    ... )
    True
    >>> source_url('(measured baseline)') is None
    True
    """
    if location.startswith('('):
        return None

    (path, _, lines) = location.partition(':')
    if not path.startswith('Configurations/'):
        path = JAVA_SOURCE_ROOT + path

    url = UPSTREAM_REPOSITORY + '/blob/' + UPSTREAM_COMMIT + '/' + path
    if lines:
        (first, _, last) = lines.partition('-')
        url += '#L' + first + ('-L' + last if last else '')

    return url

def source_lines(location: str) -> tuple[str, int, int] | None:
    """
    Return the upstream path (relative to the repository root) and the first and
    last line of a source location, or ``None`` if the entry does not specify
    a line range.

    >>> source_lines('ACCoRD/WCV_TCOA.java:18-22')
    ('Java/src/gov/nasa/larcfm/ACCoRD/WCV_TCOA.java', 18, 22)
    >>> source_lines('Util/LossData.java:44')
    ('Java/src/gov/nasa/larcfm/Util/LossData.java', 44, 44)
    >>> source_lines('Configurations/DO_365B_no_SUM.conf') is None
    True
    """
    (path, _, lines) = location.partition(':')
    if location.startswith('(') or not lines:
        return None

    (first, _, last) = lines.partition('-')
    return (JAVA_SOURCE_ROOT + path, int(first), int(last or first))

def _markdown_entry(requirement: dict) -> list[str]:
    """
    Return the lines of the Markdown rendering of a single requirement.
    """
    locations = []
    for location in requirement['code']:
        url = source_url(location)
        locations.append(location if url is None else '[`' + location + '`](' + url + ')')

    lines = [
        '### ' + requirement['id'] + ': ' + requirement['title'],
        '',
        requirement['text'],
        '',
        '* Derived from: ' + ', '.join(locations) + '.',
        '* PVS: ' + requirement['pvs'] + ' (' + RELATIONSHIPS[requirement['rel']] + ').',
        '* Verified by: ' + ', '.join(METHODS[m] for m in requirement['verify']) + '.'
    ]
    if 'history' in requirement:
        lines.append('* History: ' + requirement['history'])

    return lines + ['']

def markdown(requirements: Iterable[dict] = REQUIREMENTS) -> str:
    """
    Return a Markdown document that presents the supplied requirements grouped
    by kind.

    >>> document = markdown()
    >>> document.splitlines()[0]
    '# Derived Requirements'
    >>> all('### ' + r['id'] + ': ' in document for r in REQUIREMENTS)
    True
    >>> '## Requested Improvements' in document
    True
    """
    requirements = list(requirements)
    commit = '[`' + UPSTREAM_COMMIT[:8] + '`](' + UPSTREAM_REPOSITORY + '/tree/' + \
        UPSTREAM_COMMIT + ')'
    lines = [
        '# Derived Requirements',
        '',
        'Requirements derived from the well-clear detection component (`WCV_TAUMOD` together '
        'with `WCV_TCOA`) of [DAIDALUS](' + UPSTREAM_REPOSITORY + ') at commit ' + commit +
        ' (' + UPSTREAM_COMMIT_DATE + '), Java implementation. Each source location links to '
        'the upstream lines from which the requirement was derived. PVS names refer to the '
        'theories in the upstream `PVS/WellClear` and `PVS/TCASII` directories.',
        '',
        'This document is generated by `python -m wellclear requirements` from '
        '`src/wellclear/requirements.py`. Edit that module rather than this document.',
        '',
        'Notation: s = so - si and v = vo - vi are the relative position and velocity, the '
        'subscript h denotes the horizontal components (x, y), and D = DTHR. All quantities '
        'are in SI units.',
        ''
    ]
    for (kind, title) in KINDS.items():
        lines.extend(['## ' + title, ''])
        for requirement in requirements:
            if requirement['kind'] == kind:
                lines.extend(_markdown_entry(requirement))

    return '\n'.join(lines).rstrip('\n') + '\n'

def write(directory: str | pathlib.Path) -> list[pathlib.Path]:
    """
    Write the JSON and Markdown renderings of the requirements into the
    supplied directory and return the paths of the files written.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as directory:
    ...     [path.name for path in write(directory)]
    ['requirements.json', 'requirements.md']
    """
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / 'requirements.json', directory / 'requirements.md']
    paths[0].write_text(json.dumps(list(REQUIREMENTS), indent=2) + '\n', encoding='utf-8')
    paths[1].write_text(markdown(), encoding='utf-8')
    return paths

if __name__ == '__main__':
    doctest.testmod() # pragma: no cover
