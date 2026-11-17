"""
Command-line interface for each step of the thin thread. Run
``python -m wellclear --help`` for a list of the available commands.
"""
from __future__ import annotations
from typing import Sequence
import argparse
import sys

from wellclear import requirements, vectors, oracle, check, summary, page

def _requirements(arguments: argparse.Namespace) -> None:
    """
    Write the JSON and Markdown renderings of the derived requirements.
    """
    for path in requirements.write(arguments.directory):
        print('wrote ' + str(path))

def _vectors(arguments: argparse.Namespace) -> None:
    """
    Generate the corpus of test vectors.
    """
    corpus = vectors.rows()
    vectors.write(arguments.output, corpus)
    print(f'wrote {len(corpus):,} vectors to {arguments.output}: {vectors.categories(corpus)}')

def _oracle(arguments: argparse.Namespace) -> None:
    """
    Evaluate the exact model on every test vector.
    """
    records = oracle.run(arguments.vectors, arguments.output, arguments.processes)
    valid = [record for record in records if record['valid']]
    print(
        f'wrote {len(records):,} oracle records to {arguments.output}: '
        f'{len(valid):,} in the domain, '
        f"{sum(record['sc_n'] for record in valid):,} self-check samples, "
        f"{sum(record['sc_bad'] for record in valid):,} self-check failures"
    )

def _check(arguments: argparse.Namespace) -> None:
    """
    Grade the implementations against the exact model and against each other.
    """
    implementations = dict(entry.split('=', 1) for entry in arguments.implementations)
    report = check.run(arguments.vectors, arguments.oracle, implementations)
    check.write(arguments.output, report)
    for (name, grade) in report['grades'].items():
        print(
            f"{name}: conflict {dict(grade['conflict'])}, violation {dict(grade['violation'])}, "
            f"endpoints {grade['endpoints']}, band {grade['band'].get('agree', 0)} agree and "
            f"{grade['band'].get('differ', 0)} differ, failures {len(grade['failures'])}"
        )

    for (pair, comparison) in report['pairs'].items():
        print(
            f"{pair}: {dict(comparison['counts'])}, "
            f"maximum endpoint difference {comparison['max_endpoint_diff']}"
        )

def _environment(_: argparse.Namespace) -> None:
    """
    Print a description of the machine and toolchains.
    """
    print(summary.environment(), end='')

def _summary(arguments: argparse.Namespace) -> None:
    """
    Assemble the results summary.
    """
    inputs = summary.load(vars(arguments))
    summary.write(arguments.output, summary.build(inputs))
    print('wrote ' + arguments.output)

def _page(arguments: argparse.Namespace) -> None:
    """
    Build the interactive results page.
    """
    size = page.write(arguments.output, arguments.template, arguments.summary, arguments.script)
    print(f'wrote {arguments.output} ({size:,} bytes)')

def parser() -> argparse.ArgumentParser:
    """
    Return the parser for the command-line arguments.

    >>> parser().parse_args(['oracle', 'v.csv', 'o.csv']).processes is None
    True
    """
    root = argparse.ArgumentParser(prog='wellclear', description=__doc__.partition('.')[0] + '.')
    commands = root.add_subparsers(dest='command', required=True)

    command = commands.add_parser('requirements', help='write the derived requirements')
    command.add_argument('directory', nargs='?', default='derivation')
    command.set_defaults(handler=_requirements)

    command = commands.add_parser('vectors', help='generate the corpus of test vectors')
    command.add_argument('output')
    command.set_defaults(handler=_vectors)

    command = commands.add_parser('oracle', help='evaluate the exact model on the corpus')
    command.add_argument('vectors')
    command.add_argument('output')
    command.add_argument('--processes', type=int, default=None)
    command.set_defaults(handler=_oracle)

    command = commands.add_parser('check', help='grade the implementations')
    command.add_argument('vectors')
    command.add_argument('oracle')
    command.add_argument('output')
    command.add_argument('implementations', nargs='+', metavar='NAME=PATH')
    command.set_defaults(handler=_check)

    command = commands.add_parser('environment', help='describe the machine and toolchains')
    command.set_defaults(handler=_environment)

    command = commands.add_parser('summary', help='assemble the results summary')
    command.add_argument('output')
    for (name, default) in (
        ('vectors', 'build/vectors.csv'), ('oracle', 'build/oracle.csv'),
        ('orig', 'build/original.csv'), ('rust', 'build/rust.csv'), ('js', 'build/js.csv'),
        ('grades', 'results/grades.json'), ('bench', 'results/bench.txt'),
        ('fuzz', 'results/fuzz.txt'), ('library', 'rust/src/lib.rs')
    ):
        command.add_argument('--' + name, default=default)
    command.set_defaults(handler=_summary)

    command = commands.add_parser('page', help='build the interactive results page')
    command.add_argument('output')
    command.add_argument('--template', default='web/template.html')
    command.add_argument('--summary', default='results/summary.json')
    command.add_argument('--script', default='web/wellclear.js')
    command.set_defaults(handler=_page)

    return root

def main(arguments: Sequence[str] | None = None) -> None:
    """
    Run the command specified by the command-line arguments.
    """
    namespace = parser().parse_args(arguments)
    namespace.handler(namespace)

if __name__ == '__main__':
    sys.exit(main())
