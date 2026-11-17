"""
Tests of the derived requirements and of their generated renderings.
"""
import json
import pathlib
import re

import pytest

from wellclear import requirements

ROOT = pathlib.Path(__file__).resolve().parent.parent
DAIDALUS = ROOT / 'build' / 'daidalus'

def test_identifiers_are_unique_and_well_formed():
    identifiers = [r['id'] for r in requirements.REQUIREMENTS]
    assert len(identifiers) == len(set(identifiers)) == 24
    assert all(re.fullmatch(r'(IF|ENV|SEM|NUM|ACC|PERF|IMP)-\d', i) for i in identifiers)

def test_entries_use_known_vocabulary():
    for requirement in requirements.REQUIREMENTS:
        assert requirement['kind'] in requirements.KINDS
        assert requirement['rel'] in requirements.RELATIONSHIPS
        assert set(requirement['verify']) <= set(requirements.METHODS)
        assert requirement['code'] and requirement['text'] and requirement['title']

def test_generated_renderings_are_current():
    rendered = json.loads((ROOT / 'derivation' / 'requirements.json').read_text('utf-8'))
    assert rendered == list(requirements.REQUIREMENTS)
    markdown = (ROOT / 'derivation' / 'requirements.md').read_text('utf-8')
    assert markdown == requirements.markdown()

def test_fetch_script_uses_the_derivation_commit():
    script = (ROOT / 'scripts' / 'fetch-daidalus.sh').read_text('utf-8')
    assert 'COMMIT=' + requirements.UPSTREAM_COMMIT in script

def test_source_urls_point_at_the_pinned_commit():
    for requirement in requirements.REQUIREMENTS:
        for location in requirement['code']:
            url = requirements.source_url(location)
            assert url is None or requirements.UPSTREAM_COMMIT in url

@pytest.mark.skipif(not DAIDALUS.is_dir(), reason='DAIDALUS checkout not present')
def test_source_locations_exist_upstream():
    for requirement in requirements.REQUIREMENTS:
        for location in requirement['code']:
            if location.startswith('('):
                continue
            span = requirements.source_lines(location)
            if span is None:
                assert (DAIDALUS / location).is_file(), location
                continue
            (path, first, last) = span
            lines = (DAIDALUS / path).read_text('utf-8').splitlines()
            assert 1 <= first <= last <= len(lines), location
