"""
Assembly of the standalone interactive results page (``index.html``) from its
template, the results summary, and the JavaScript port of the regenerated
component.

The page has no external dependencies other than web fonts: the summary is
embedded as a JSON document and the regenerated component is embedded as a
script, so the explorer runs the same code that was graded on the corpus.
"""
from __future__ import annotations
import doctest
import pathlib

SUMMARY_PLACEHOLDER = '/*__SUMMARY__*/'
"""
Placeholder in the template that is replaced by the results summary.
"""

SCRIPT_PLACEHOLDER = '/*__WELLCLEAR__*/'
"""
Placeholder in the template that is replaced by the JavaScript port of the
regenerated component.
"""

def build(template: str, summary: str, script: str) -> str:
    """
    Return the page obtained by embedding the summary (a JSON document) and the
    script into the template.

    >>> build('<script>/*__SUMMARY__*/</script><script>/*__WELLCLEAR__*/</script>', '{}\\n', 'f();')
    '<script>{}</script><script>f();</script>'

    The embedded text must not be able to close the element that contains it.

    >>> build('/*__SUMMARY__*/ /*__WELLCLEAR__*/', '"</script>"', '')
    Traceback (most recent call last):
      ...
    ValueError: embedded text must not contain a closing script tag
    """
    for (placeholder, text) in ((SUMMARY_PLACEHOLDER, summary), (SCRIPT_PLACEHOLDER, script)):
        if template.count(placeholder) != 1:
            raise ValueError('template must contain exactly one ' + placeholder)
        if '</script' in text.lower():
            raise ValueError('embedded text must not contain a closing script tag')

    return template \
        .replace(SUMMARY_PLACEHOLDER, summary.strip()) \
        .replace(SCRIPT_PLACEHOLDER, script.strip())

def write(target: str | pathlib.Path, template: str | pathlib.Path, summary, script) -> int:
    """
    Build the page from the template, summary, and script files and write it
    to the target path. Return the size of the page in bytes.
    """
    (template, summary, script) = (
        pathlib.Path(path).read_text(encoding='utf-8') for path in (template, summary, script)
    )
    page = build(template, summary, script)
    pathlib.Path(target).write_text(page, encoding='utf-8')
    return len(page.encode('utf-8'))

if __name__ == '__main__':
    doctest.testmod() # pragma: no cover
