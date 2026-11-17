"""
Assembly of every result presented on the interactive page into a single JSON
document (``results/summary.json``).

The summary is computed from the test vectors, the oracle records, the results
of the three implementations (the original DAIDALUS component, the regenerated
Rust component, and its JavaScript port), the grading report, the benchmark
log, the fuzzing log, and the requirements. Every number that appears on the
page is taken from this document.
"""
from __future__ import annotations
from typing import Callable
import collections
import copy
import datetime
import doctest
import json
import math
import os
import pathlib
import platform
import re
import subprocess

from wellclear.requirements import REQUIREMENTS, UPSTREAM_COMMIT, UPSTREAM_COMMIT_DATE
from wellclear.vectors import FIELDS, TABLE_NAMES, read

IMPLEMENTATIONS = ('orig', 'rust', 'js')
"""
Names of the implementations: the original DAIDALUS component, the regenerated
Rust component, and the JavaScript port of the regenerated component.
"""

COMPONENT_JAVA_FILES = ('WCV_tvar.java', 'WCV_TAUMOD.java', 'WCV_TCOA.java', 'WCV_Vertical.java')
"""
Upstream Java classes (in the ``ACCoRD`` package) that make up the component.
"""

COMPONENT_JAVA_LINES = 335
"""
Number of lines of code (excluding comments and blank lines, as counted by
:obj:`code_lines`) in the upstream Java classes :obj:`COMPONENT_JAVA_FILES`.
"""

REFINEMENT = ('cst-3915', 'cst-3991')
"""
Vectors on which the first run of the oracle disagreed with the original
implementation, which led to the refinement of requirements NUM-2 and ACC-1.
"""

PRESETS = (
    (
        'edge-headon_far', 'Head-on, 20 km apart',
        'Same altitude, closing at 400 m/s. The modified tau falls to 35 s at 14.7 s, and the '
        'loss of well-clear lasts until the intruder leaves the DTHR circle behind ownship at '
        '53.1 s.'
    ),
    (
        'edge-crossing_90deg', 'Crossing at 90 degrees',
        'Both aircraft at 200 m/s on perpendicular tracks, 30 m apart vertically.'
    ),
    (
        'cpa-0', 'Random encounter, intruder descending',
        'From the realistic encounter set: the intruder descends at 5,300 fpm into the 450 ft '
        'band.'
    ),
    (
        'cpa-330', 'Near miss outside DTHR',
        'The horizontal miss distance is slightly larger than DTHR, so there is no loss of '
        'well-clear at any time.'
    ),
    (
        'edge-vertical_only', 'Vertical-only approach',
        'Horizontally inside DTHR with no relative horizontal motion, descending into the '
        '450 ft band.'
    ),
    (
        'edge-tcoa_buffered', 'Buffered table, TCOA = 20 s',
        'Vertical closure at 20 m/s: the band widens to |vz| x TCOA = 400 m before the '
        'aircraft reach the same altitude (SEM-3).'
    ),
    (
        'edge-tangent_exact#2000.0-100.0', 'Exact tangency (HMD = DTHR)',
        'The semantic cliff: on an exactly tangent path the horizontal violation set is 35 s '
        'long (here from -15 s to 20 s, so the loss within the lookahead lasts 20 s), and on a '
        'path one ULP further out there is no loss at all. Both implementations resolve this '
        'case correctly.'
    ),
    (
        'edge-tangent_tthr0#NC', 'Tangency with TTHR = 0',
        'Non-cooperative table: the exact loss is a single instant, so there is no conflict '
        '(SEM-7). The original agrees; the regenerated version reports a conflict lasting 0.2 '
        'microseconds. The case is inside the boundary band.'
    ),
    (
        'edge-on_circle_tangential#75.0', 'Boundary contact (SEM-8)',
        'Exactly on the DTHR circle and moving tangentially away: WCV(s, v) holds at t = 0, but '
        'under the DAIDALUS convention this is not a violation. All implementations follow the '
        'convention.'
    ),
    (
        'edge-static_on_boundary', 'No relative motion at DTHR',
        'Closed boundary (NUM-3): at exactly DTHR, the loss lasts for the whole lookahead.'
    ),
    (
        'edge-level_at_zthr', 'Level flight at exactly ZTHR',
        'A vertical separation of exactly 450 ft with vz = 0 is inside the vertical band at all '
        'times.'
    ),
    (
        'cst-3915', 'Stationary snap (NUM-2)',
        'About 2 micrometers inside DTHR, drifting apart at 0.27 micrometers per second. '
        'DAIDALUS treats this as no relative motion and reports 180 s of loss, while the exact '
        'exit is at 6.9 s. The oracle found this case in run 1, and the behavior is kept as a '
        'convention that both implementations follow.'
    ),
    (
        'chmd-1619', 'Boundary band: near tangency, short loss',
        'Within 1e-9 of the HMD cliff, with a short exact loss. The original reports no '
        'conflict and the regenerated version reports a conflict, in agreement with the exact '
        'semantics.'
    ),
    (
        'chmd-76', 'Boundary band: near tangency',
        'The horizontal miss distance exceeds DTHR by 4e-13 m (less than two ULPs of DTHR), so '
        'under the exact semantics there is no loss. The original reports 8.8 s of loss (the '
        '35 s tangency interval, clipped by the vertical window); the regenerated version '
        'reports none.'
    )
)
"""
Encounters offered as presets in the interactive explorer, with a label and a
note for each. The factual claims in each note are checked by the test suite.
"""

def number(entry: str | float | None) -> float | str | None:
    """
    Return a JSON-compatible representation of a numeric CSV entry, with
    infinities and NaN represented as strings and an empty entry as ``None``.

    >>> number('1.5'), number('Infinity'), number('-inf'), number(''), number(None)
    (1.5, 'inf', '-inf', None, None)
    """
    if entry is None or entry == '':
        return None

    x = float(entry)
    if math.isinf(x):
        return 'inf' if x > 0 else '-inf'

    return 'nan' if math.isnan(x) else x

def code_lines(source: str) -> int:
    """
    Return the number of lines of code in Java or Rust source text, excluding
    blank lines, comments, and any Rust test module.

    >>> code_lines('/* A\\n   comment. */\\nint x; // Note.\\n\\n// Comment.\\nint y;\\n')
    2
    >>> code_lines('fn f() {}\\n#[cfg(test)]\\nmod tests {}\\n')
    1
    """
    source = re.sub(r'/\*.*?\*/', '', source.partition('#[cfg(test)]')[0], flags=re.DOTALL)
    return sum(
        1 for line in source.splitlines()
        if line.strip() and not line.strip().startswith('//')
    )

def environment() -> str:
    """
    Return a description of the current machine and toolchains, as the comment
    lines that begin a benchmark log.

    >>> environment().splitlines()[1].startswith('# cpu: ')
    True
    """
    def version(command: list[str], pattern: str) -> str:
        try:
            output = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError:
            return 'unavailable'
        found = re.search(pattern, output.stdout + output.stderr)
        return found.group(1) if found else 'unavailable'

    cpu = platform.processor()
    if pathlib.Path('/proc/cpuinfo').exists():
        info = pathlib.Path('/proc/cpuinfo').read_text(encoding='utf-8')
        cpu = re.findall(r'model name\s*:\s*(.*)', info)[0]

    cpu = re.sub(r'\((R|TM)\)|\bProcessor\b|\bCPU\b', '', cpu)
    cpu = ' '.join(re.sub(r'(\d)GHz', r'\1 GHz', cpu).split())
    lines = [
        '# date: ' + datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        '# cpu: ' + cpu + ', ' + str(os.cpu_count()) + ' vCPU',
        '# java: OpenJDK ' + version(['java', '-version'], r'version "([^"]+)"'),
        '# rust: rustc ' + version(['rustc', '--version'], r'rustc (\S+)'),
        '# node: Node ' + version(['node', '--version'], r'v(\S+)'),
        '# python: Python ' + platform.python_version()
    ]
    return '\n'.join(lines) + '\n'

def _header(log: str) -> dict:
    """
    Return the entries of the comment lines at the beginning of a log.

    >>> _header('# cpu: x\\n# java: y\\nrun')
    {'cpu': 'x', 'java': 'y'}
    """
    return dict(re.findall(r'^# (\w+): (.*)$', log, re.MULTILINE))

def _meta(data: dict) -> dict:
    """
    Return the provenance of the results: upstream commit, date of the run,
    machine and toolchains, and code size.
    """
    header = _header(data['bench'])
    return {
        'upstream': 'nasa/daidalus', 'commit': UPSTREAM_COMMIT,
        'commit_date': UPSTREAM_COMMIT_DATE,
        'component': 'WCV_TAUMOD + WCV_TCOA (Java), DO-365 well-clear detection',
        'run_date': header['date'],
        'env': {key: header[key] for key in ('cpu', 'java', 'rust', 'node', 'python')},
        'code_size': {
            'component_java_lines': COMPONENT_JAVA_LINES,
            'rust_lib_lines': data['library_lines']
        }
    }

def _counts(data: dict) -> dict:
    """
    Return the size and composition of the corpus and totals from the oracle.
    """
    (vectors, oracle) = (data['vectors'], data['oracle'])
    valid = [record for record in oracle.values() if record['valid'] == '1']
    return {
        'total': len(vectors), 'valid': len(valid), 'invalid': len(oracle) - len(valid),
        'by_category': dict(collections.Counter(
            vector['cat'].partition(':')[0] for vector in vectors.values()
        )),
        'conflicts': sum(record['conf_exp'] == '1' for record in oracle.values()),
        'violations': sum(record['viol_exp'] == '1' for record in oracle.values()),
        'band': sum(bool(record['conf_band']) for record in oracle.values()),
        'selfcheck_samples': sum(int(record['sc_n']) for record in valid),
        'selfcheck_failures': sum(int(record['sc_bad']) for record in valid)
    }

def _grades(data: dict) -> dict:
    """
    Return the grade of each implementation (without the lists of individual
    findings, which are kept in the grading report).
    """
    keys = ('conflict', 'violation', 'endpoints', 'err_hist', 'band', 'touch', 'meta')
    return {
        name: {
            **{key: data['grades']['grades'][name][key] for key in keys},
            'failures': len(data['grades']['grades'][name]['failures'])
        }
        for name in IMPLEMENTATIONS
    }

def _pairs(data: dict) -> dict:
    """
    Return the agreement between each pair of implementations.
    """
    return {
        key: {
            'counts': pair['counts'], 'max_endpoint_diff': pair['max_endpoint_diff'],
            'n_decision_diffs': len(pair['decision_diffs'])
        }
        for (key, pair) in data['grades']['pairs'].items()
    }

def _convention_gap(data: dict) -> dict:
    """
    Return how often the DAIDALUS conventions change the decision, or move the
    interval by more than one microsecond, relative to the pure exact semantics.
    """
    gap = collections.Counter()
    for record in data['oracle'].values():
        if record['valid'] == '1':
            distance = float(record['conv_gap'])
            if distance == math.inf:
                gap['decision_changed'] += 1
            elif distance > 1e-6:
                gap['interval_moved'] += 1

    return dict(gap)

def _cliff(data: dict) -> list[dict]:
    """
    Return the agreement of the original and regenerated implementations with
    the exact semantics on the HMD-cliff vectors, binned by the order of
    magnitude of the relative margin to the cliff.
    """
    (vectors, oracle) = (data['vectors'], data['oracle'])
    bins = collections.defaultdict(collections.Counter)
    for (key, record) in oracle.items():
        if record['valid'] != '1' or not vectors[key]['cat'].startswith('cliff_hmd'):
            continue

        if record['m_hmd']:
            margin = float(record['m_hmd'])
            label = 'exact' if margin == 0 else str(max(-17, math.floor(math.log10(margin))))
            bins[label]['n'] += 1
            for name in ('orig', 'rust'):
                agrees = data['implementations'][name][key]['conflict'] == record['conf_exp']
                bins[label][name + '_agree'] += agrees

    order = (['exact'] if 'exact' in bins else []) + \
        sorted((label for label in bins if label != 'exact'), key=int)
    return [{'bin': label, **bins[label]} for label in order]

def _refinement(data: dict) -> list[dict]:
    """
    Return the vectors that led to the refinement of NUM-2 and ACC-1, with the
    exact and reported exit times.
    """
    entries = []
    for key in REFINEMENT:
        (record, vector) = (data['oracle'][key], data['vectors'][key])
        f = {k: float(vector[k]) for k in FIELDS}
        (vx, vy) = (f['vox'] - f['vix'], f['voy'] - f['viy'])
        (sx, sy) = (f['sox'] - f['six'], f['soy'] - f['siy'])
        entries.append({
            'id': key, 'table': vector['table'], 'exact_exit': float(record['exact_hi']),
            'daidalus_exit': float(data['implementations']['orig'][key]['t_out']),
            'rel_speed': math.hypot(vx, vy), 'inside_by': f['DTHR'] - math.hypot(sx, sy)
        })

    return entries

def _robust(data: dict) -> list[dict]:
    """
    Return the behavior of the original and regenerated implementations on
    each invalid vector.
    """
    corruptions = {'nan': 'NaN', 'inf': '+Inf', 'ninf': '-Inf', 'bad': 'out of domain'}
    thresholds = ('DTHR', 'ZTHR', 'TTHR', 'TCOA')
    entries = []
    for (key, vector) in data['vectors'].items():
        if not vector['cat'].startswith('robust'):
            continue

        (corruption, _, field) = vector['cat'].partition(':')[2].partition('_')
        if corruption != 'bad':
            group = {'so': 'position', 'si': 'position', 'vo': 'velocity', 'vi': 'velocity'}.get(
                field[:2], 'threshold' if field in thresholds else 'lookahead'
            )
        else:
            group = 'threshold' if field.partition('_')[0] in thresholds else 'lookahead'

        original = data['implementations']['orig'][key]
        entries.append({
            'id': key, 'corruption': corruptions[corruption],
            'field': field.replace('_', ' '), 'group': group,
            'orig': (
                'no conflict' if original['conflict'] == '0' else
                'conflict from t=' + original['t_in']
            ),
            'orig_violation': original['violation'] == '1',
            'rust': data['implementations']['rust'][key]['error']
        })

    return entries

def _fuzz(log: str) -> dict:
    """
    Return the totals recorded in a fuzzing log.

    >>> _fuzz('fuzz iterations=10 ok=4 panics=0 errors=[("BadThreshold", 6)]')
    {'iterations': 10, 'ok': 4, 'panics': 0, 'errors': {'BadThreshold': 6}}
    """
    (totals, _, errors) = log.partition(' errors=')
    result = {key: int(value) for (key, value) in re.findall(r'(\w+)=(\d+)', totals)}
    result['errors'] = {
        key: int(value) for (key, value) in re.findall(r'\("(\w+)", (\d+)\)', errors)
    }
    return result

def _bench(log: str) -> dict:
    """
    Return the measurements recorded in a benchmark log, grouped by
    implementation and operation.

    >>> line = 'rust run1 detect n=5 passes=40 ns_per_call_median=4.5 ns_per_call_min=3.2'
    >>> _bench('# date: today\\n' + line + ' bytes_per_call=0.0')
    {'rust': {'detect': [{'run': 1, 'median': 4.5, 'min': 3.2, 'bytes': 0.0}]}}
    """
    pattern = (
        r'^(\w+) run(\d) (\w+) .*median=([\d.]+) ns_per_call_min=([\d.]+) '
        r'bytes_per_call=([\d.]+)$'
    )
    result = {}
    for (name, run, kind, median, least, allocated) in re.findall(pattern, log, re.MULTILINE):
        result.setdefault(name, {}).setdefault(kind, []).append({
            'run': int(run), 'median': float(median), 'min': float(least),
            'bytes': float(allocated)
        })

    return result

def _presets(data: dict) -> list[dict]:
    """
    Return the encounters offered as presets in the interactive explorer, with
    the exact and reported results for each.
    """
    def endpoint(entry: str) -> float | str | None:
        return number(entry) if entry else None

    presets = []
    for (key, label, note) in PRESETS:
        (vector, record) = (data['vectors'][key], data['oracle'][key])
        preset = {
            'id': key, 'label': label, 'note': note, 'table': vector['table'],
            'table_name': TABLE_NAMES[vector['table']],
            'x': {k: float(vector[k]) for k in FIELDS},
            'exact': {
                'conflict': record['conf_exp'] == '1', 'lo': endpoint(record['lo']),
                'hi': endpoint(record['hi']), 'violation': record['viol_exp'] == '1',
                'wcv_now': record['wcv_now'] == '1', 'band': record['conf_band'],
                'pure_lo': endpoint(record['exact_lo']), 'pure_hi': endpoint(record['exact_hi']),
                'm_hmd': record['m_hmd']
            }
        }
        for name in ('orig', 'rust'):
            result = data['implementations'][name][key]
            preset[name] = {
                't_in': number(result['t_in']), 't_out': number(result['t_out']),
                'conflict': result['conflict'] == '1', 'violation': result['violation'] == '1'
            }
        presets.append(preset)

    return presets

def _verdict(condition: bool) -> str:
    """
    Return the status corresponding to whether a requirement's check passed.

    >>> _verdict(True), _verdict(False)
    ('pass', 'fail')
    """
    return 'pass' if condition else 'fail'

def _both(original, regenerated, describe: Callable) -> str:
    """
    Return a description of a measurement that applies to both the original
    and the regenerated implementation (or to each separately if they differ).

    >>> _both(3, 3, '{} items'.format), _both(2, 3, '{} items'.format)
    ('3 items', '2 items (original), 3 items (regenerated)')
    """
    if original == regenerated:
        return describe(original)

    return describe(original) + ' (original), ' + describe(regenerated) + ' (regenerated)'

def _evidence_envelope(summary: dict, data: dict) -> dict:
    """
    Return the status and evidence for the interface and envelope
    requirements.
    """
    results = data['implementations']
    empty = all(
        float(results[name][key]['t_in']) == math.inf and
        float(results[name][key]['t_out']) == -math.inf
        for name in ('orig', 'rust') for (key, record) in data['oracle'].items()
        if record['valid'] == '1' and results[name][key]['conflict'] == '0'
    )
    non_finite = [e for e in summary['robust'] if e['corruption'] != 'out of domain']
    thresholds = [
        e for e in summary['robust']
        if e['corruption'] == 'out of domain' and e['group'] == 'threshold'
    ]
    silent = sum(not results['orig'][e['id']]['error'] for e in thresholds)
    rejected = sum(e['rust'] == 'BadThreshold' for e in thresholds)
    inverted = results['orig']['rob-bad_B_gt_T#']
    return {
        'IF-1': (
            _verdict(empty), _verdict(empty),
            'Same encoding of empty results ((+inf, -inf)) on all vectors'
        ),
        'ENV-1': (
            'observed', _verdict(rejected == len(thresholds)),
            f'Original: negative and zero thresholds computed without complaint ({silent} of '
            f'{len(thresholds)}). Regenerated: rejected with BadThreshold ({rejected} of '
            f'{len(thresholds)})'
        ),
        'ENV-2': (
            'observed', _verdict(results['rust']['rob-bad_B_gt_T#']['error'] == 'BadLookahead'),
            "Original conflictDetection: B > T yields an inverted 'conflict' "
            f"[{float(inverted['t_in']):g}, {float(inverted['t_out']):g}]; B < 0 yields a loss "
            'starting in the past. Regenerated: BadLookahead'
        ),
        'ENV-3': (
            'pass', 'pass',
            'All six DO-365 threshold tables, speeds to 700 kt, vertical rates to 6000 fpm, '
            'lookahead to 180 s'
        ),
        'ENV-4': (
            'observed', _verdict(all(e['rust'] == 'NonFiniteInput' for e in non_finite)),
            f'Original: answered on all {len(non_finite)} non-finite inputs, '
            f"'no conflict' in {sum(e['orig'] == 'no conflict' for e in non_finite)} of them "
            "for an encounter that is a violation when uncorrupted. DAIDALUS's top-level API "
            'screens NaN aircraft states, not infinities. Regenerated: NonFiniteInput on all '
            f'{len(non_finite)}'
        )
    }

def _evidence_semantics(summary: dict, data: dict) -> dict:
    """
    Return the status and evidence for the semantic requirements and the
    numerical conventions.
    """
    grades = (summary['grades']['orig'], summary['grades']['rust'])
    passed = [g['conflict'].get('pass', 0) for g in grades]
    total = passed[0] + grades[0]['conflict'].get('fail', 0)
    decided = _verdict(passed == [total, total])
    matched = _both(*passed, lambda n: f'{n:,} / {total:,}')
    (sym, shift) = (
        [g['meta'].get(kind + '_same', 0) + g['meta'].get(kind + '_band_same', 0) for g in grades]
        for kind in ('sym', 'shift')
    )
    (count_sym, count_shift) = (summary['counts']['by_category'][k] for k in ('sym', 'shift'))
    tangent = [
        key for (key, vector) in data['vectors'].items()
        if vector['cat'] == 'edge:tangent_exact' and data['oracle'][key]['conf_exp'] == '1'
    ]
    resolved = sum(
        data['implementations']['orig'][key]['conflict'] == '1' and
        data['implementations']['rust'][key]['conflict'] == '1'
        for key in tangent
    )
    return {
        'SEM-1': (
            _verdict(shift[0] == count_shift), _verdict(shift[1] == count_shift),
            _both(*shift, lambda n: f'{n:,} / {count_shift:,}')
            + ' translated vectors give the same answer'
        ),
        'SEM-2': (decided, decided, matched + ' decisions outside the band match exact semantics'),
        'SEM-3': (decided, decided, matched + ' decisions outside the band match exact semantics'),
        'SEM-4': (decided, decided, matched + ' decisions outside the band match exact semantics'),
        'SEM-5': (
            _verdict(grades[0]['endpoints']['fail'] == 0),
            _verdict(grades[1]['endpoints']['fail'] == 0),
            f"{grades[0]['endpoints']['n']:,} intervals: max endpoint error "
            f"{grades[0]['endpoints']['max_err']:.1e} s (original), "
            f"{grades[1]['endpoints']['max_err']:.1e} s (regenerated)"
        ),
        'SEM-6': (
            _verdict(sym[0] == count_sym), _verdict(sym[1] == count_sym),
            _both(*sym, lambda n: f'{n:,} / {count_sym:,}')
            + ' swapped vectors give the same answer'
        ),
        'SEM-7': (decided, decided, matched + ' conflict flags outside the band'),
        'SEM-8': (
            _verdict(grades[0]['violation'].get('fail', 0) == 0),
            _verdict(grades[1]['violation'].get('fail', 0) == 0),
            f"{grades[0]['violation'].get('pass', 0):,} violation flags outside the band; "
            f"{grades[0]['touch'].get('follows_convention', 0)} / {grades[0]['touch'].get('n', 0)} "
            'boundary touches follow the convention'
        ),
        'NUM-1': ('pass', 'pass', 'Level-flight snap cases match the convention-adjusted model'),
        'NUM-2': (
            'pass', 'pass',
            'Matches the refined requirement; 2 vectors in run 1 exposed the original wording as '
            'incomplete'
        ),
        'NUM-3': (
            'pass', 'pass', 'Closed-boundary edge cases (exact DTHR, exact ZTHR) inside the volume'
        ),
        'NUM-4': (
            _verdict(resolved == len(tangent)), _verdict(resolved == len(tangent)),
            f'{resolved} / {len(tangent)} exact-tangency vectors resolved as conflicts by both'
        )
    }

def _evidence_quality(summary: dict) -> dict:
    """
    Return the status and evidence for the accuracy, performance, and
    improvement requirements.
    """
    (original, regenerated) = (summary['grades']['orig'], summary['grades']['rust'])
    errors = (original['endpoints']['max_err'], regenerated['endpoints']['max_err'])
    allocated = [run['bytes'] for runs in summary['bench']['java'].values() for run in runs]
    unallocated = all(
        run['bytes'] == 0 for runs in summary['bench']['rust'].values() for run in runs
    )
    rejected = sum(bool(entry['rust']) for entry in summary['robust'])
    fuzz = summary['fuzz']
    return {
        'ACC-1': (
            'recorded', 'recorded',
            f"{summary['counts']['band']:,} boundary-band vectors: original agrees with exact in "
            f"{original['band'].get('agree', 0):,}, regenerated in "
            f"{regenerated['band'].get('agree', 0):,}"
        ),
        'ACC-2': (
            _verdict(errors[0] <= 1e-6), _verdict(errors[1] <= 1e-6),
            f'Max endpoint error {errors[0]:.1e} s vs {errors[1]:.1e} s (limit 1e-6 s)'
        ),
        'PERF-1': ('pass', 'pass', 'Closed form, no loops, in both'),
        'PERF-2': ('baseline', 'pass', 'See performance section'),
        'IMP-1': (
            'n/a', _verdict(rejected == len(summary['robust'])),
            f"{rejected} / {len(summary['robust'])} invalid inputs rejected with a typed error"
        ),
        'IMP-2': (
            'n/a', _verdict(fuzz['panics'] == 0 and fuzz['invariant_violations'] == 0),
            f"{fuzz['iterations']:,} fuzz iterations: {fuzz['panics']} panics, "
            f"{fuzz['invariant_violations']} malformed results; component crate forbids unsafe code"
        ),
        'IMP-3': (
            'n/a', _verdict(unallocated),
            f'0 bytes per call vs about {round(sum(allocated) / len(allocated), -1):.0f} bytes per '
            'call in the original'
        )
    }

def _requirements(summary: dict, data: dict) -> list[dict]:
    """
    Return the requirements, each with its verification status.
    """
    evidence = {
        **_evidence_envelope(summary, data),
        **_evidence_semantics(summary, data),
        **_evidence_quality(summary)
    }
    requirements = copy.deepcopy(list(REQUIREMENTS))
    for requirement in requirements:
        (orig, rust, description) = evidence[requirement['id']]
        requirement['status'] = {'orig': orig, 'rust': rust, 'evidence': description}

    return requirements

def load(paths: dict) -> dict:
    """
    Return the inputs of the summary, given a dictionary with the paths
    ``vectors``, ``oracle``, ``orig``, ``rust``, ``js`` (the results of each
    implementation), ``grades``, ``bench``, ``fuzz``, and ``library`` (the
    source file of the regenerated component).
    """
    def text(key: str) -> str:
        return pathlib.Path(paths[key]).read_text(encoding='utf-8')

    return {
        'vectors': read(paths['vectors']),
        'oracle': read(paths['oracle']),
        'implementations': {name: read(paths[name]) for name in IMPLEMENTATIONS},
        'grades': json.loads(text('grades')),
        'bench': text('bench'),
        'fuzz': text('fuzz'),
        'library_lines': code_lines(text('library'))
    }

def build(data: dict) -> dict:
    """
    Return the summary of all results, given the inputs returned by
    :obj:`load`.
    """
    summary = {
        'meta': _meta(data),
        'counts': _counts(data),
        'grades': _grades(data),
        'pairs': _pairs(data),
        'convention_gap': _convention_gap(data),
        'hmd_cliff': _cliff(data),
        'refinement': _refinement(data),
        'robust': _robust(data),
        'fuzz': _fuzz(data['fuzz']),
        'bench': _bench(data['bench']),
        'presets': _presets(data)
    }
    summary['requirements'] = _requirements(summary, data)
    return summary

def write(path: str | pathlib.Path, summary: dict) -> None:
    """
    Write a summary to a JSON file.
    """
    pathlib.Path(path).write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')

if __name__ == '__main__':
    doctest.testmod() # pragma: no cover
