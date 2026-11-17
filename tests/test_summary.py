"""
Tests of the results summary, including the factual claims made in the notes
that accompany the explorer presets.
"""
import json
import math
import pathlib
from fractions import Fraction

import pytest

from wellclear import summary, vectors

ROOT = pathlib.Path(__file__).resolve().parent.parent
DAIDALUS = ROOT / 'build' / 'daidalus'

@pytest.fixture(name='document', scope='module')
def fixture_document():
    return json.loads((ROOT / 'results' / 'summary.json').read_text('utf-8'))

@pytest.fixture(name='presets', scope='module')
def fixture_presets(document):
    return {preset['id']: preset for preset in document['presets']}

def relative(preset):
    x = {k: Fraction(v) for (k, v) in preset['x'].items()}
    s = [x['so' + a] - x['si' + a] for a in 'xyz']
    v = [x['vo' + a] - x['vi' + a] for a in 'xyz']
    return (s, v)

def test_presets_are_described(document):
    assert [p['id'] for p in document['presets']] == [p[0] for p in summary.PRESETS]

def test_head_on_preset(presets):
    exact = presets['edge-headon_far']['exact']
    assert (round(exact['lo'], 1), round(exact['hi'], 1)) == (14.7, 53.1)

def test_descending_intruder_preset(presets):
    preset = presets['cpa-0']
    assert preset['x']['viz'] / vectors.FEET_PER_MINUTE == pytest.approx(-5300, abs=50)
    assert preset['x']['voz'] == 0 and preset['exact']['conflict']

def test_near_miss_preset(presets):
    (s, v) = relative(presets['cpa-330'])
    hmd_squared = (s[0] * v[1] - s[1] * v[0]) ** 2 / (v[0] ** 2 + v[1] ** 2)
    assert 1 < hmd_squared / Fraction(presets['cpa-330']['x']['DTHR']) ** 2 < 1.12 ** 2
    assert not presets['cpa-330']['exact']['conflict']

def test_buffered_preset(presets):
    preset = presets['edge-tcoa_buffered']
    (_, v) = relative(preset)
    assert abs(v[2]) * Fraction(preset['x']['TCOA']) == 400
    assert preset['exact']['lo'] == 10.0

def test_tangency_presets(presets):
    exact = presets['edge-tangent_exact#2000.0-100.0']['exact']
    assert (exact['conflict'], exact['lo'], exact['hi']) == (True, 0.0, 20.0)
    preset = presets['edge-tangent_tthr0#NC']
    assert preset['exact']['band'] and not preset['exact']['conflict']
    assert not preset['orig']['conflict'] and preset['rust']['conflict']
    assert preset['rust']['t_out'] - preset['rust']['t_in'] == pytest.approx(0.2e-6, abs=0.01e-6)

def test_stationary_snap_preset(presets, document):
    (s, v) = relative(presets['cst-3915'])
    inside = Fraction(presets['cst-3915']['x']['DTHR']) - float(s[0] ** 2 + s[1] ** 2) ** 0.5
    assert float(inside) == pytest.approx(2e-6, rel=0.2)
    assert float(v[0] ** 2 + v[1] ** 2) ** 0.5 == pytest.approx(0.27e-6, rel=0.05)
    refinement = {entry['id']: entry for entry in document['refinement']}['cst-3915']
    assert round(refinement['exact_exit'], 1) == 6.9 and refinement['daidalus_exit'] == 180.0

def test_band_presets(presets):
    preset = presets['chmd-1619']
    assert 'hmd' in preset['exact']['band'] and 'short' in preset['exact']['band']
    assert preset['exact']['conflict'] and preset['rust']['conflict']
    assert not preset['orig']['conflict']
    preset = presets['chmd-76']
    (s, v) = relative(preset)
    hmd_squared = (s[0] * v[1] - s[1] * v[0]) ** 2 / (v[0] ** 2 + v[1] ** 2)
    dthr = preset['x']['DTHR']
    excess = float(hmd_squared / Fraction(dthr) ** 2 - 1) / 2 * dthr # First-order excess (m).
    assert excess == pytest.approx(4e-13, abs=0.1e-13) and excess < 2 * math.ulp(dthr)
    assert preset['orig']['conflict'] and not preset['rust']['conflict']
    assert not preset['exact']['conflict']
    assert preset['orig']['t_out'] - preset['orig']['t_in'] == pytest.approx(8.8, abs=0.05)

def test_requirement_statuses(document):
    allowed = {'pass', 'observed', 'recorded', 'baseline', 'n/a'}
    for requirement in document['requirements']:
        assert {requirement['status']['orig'], requirement['status']['rust']} <= allowed

def test_logs_and_sources_are_current(document):
    library = (ROOT / 'rust' / 'src' / 'lib.rs').read_text('utf-8')
    assert document['meta']['code_size']['rust_lib_lines'] == summary.code_lines(library)
    log = (ROOT / 'results' / 'fuzz.txt').read_text('utf-8')
    assert document['fuzz'] == summary._fuzz(log) # pylint: disable=protected-access

@pytest.mark.skipif(not DAIDALUS.is_dir(), reason='DAIDALUS checkout not present')
def test_component_size():
    folder = DAIDALUS / 'Java' / 'src' / 'gov' / 'nasa' / 'larcfm' / 'ACCoRD'
    lines = sum(
        summary.code_lines((folder / name).read_text('utf-8'))
        for name in summary.COMPONENT_JAVA_FILES
    )
    assert lines == summary.COMPONENT_JAVA_LINES
