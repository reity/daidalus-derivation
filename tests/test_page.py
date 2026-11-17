"""
Tests that the committed interactive page is current.
"""
import pathlib

from wellclear import page

ROOT = pathlib.Path(__file__).resolve().parent.parent

def test_page_is_current():
    (template, summary, script) = (
        (ROOT / path).read_text('utf-8')
        for path in ('web/template.html', 'results/summary.json', 'web/wellclear.js')
    )
    assert (ROOT / 'index.html').read_text('utf-8') == page.build(template, summary, script)

def test_page_is_self_contained():
    html = (ROOT / 'index.html').read_text('utf-8')
    assert page.SUMMARY_PLACEHOLDER not in html and page.SCRIPT_PLACEHOLDER not in html
    assert '<script src=' not in html
