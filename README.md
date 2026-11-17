# daidalus-derivation

[![lint-test-cover](../../actions/workflows/lint-test-cover.yml/badge.svg)](../../actions/workflows/lint-test-cover.yml)
[![reproduce](../../actions/workflows/reproduce.yml/badge.svg)](../../actions/workflows/reproduce.yml)

Thin thread through the regeneration of a safety-critical software component: requirements derived from the well-clear detection component of [NASA DAIDALUS](https://github.com/nasa/daidalus), an exact executable model of those requirements, a new implementation of the component written in [Rust](https://www.rust-lang.org/) from the requirements (together with a JavaScript port), and a corpus of 58,983 test vectors on which the original and the regenerated implementations are graded against the model. The results are presented on an interactive page ([`index.html`](index.html)) that is published using GitHub Pages.

## Purpose

This repository tests one instance of a workflow for critical-systems software. Operating, semantic, and performance requirements are derived from an existing implementation; the requirements are encoded as an executable model; a new implementation that meets the same envelope while improving on the original (*e.g.*, in safety, performance, or architecture) is written from the requirements; and both implementations are checked against the model and against each other. The thread is deliberately narrow so that every step can be inspected and every number can be reproduced.

### Component

DO-365 defines when an unmanned aircraft is no longer *well clear* of another aircraft. DAIDALUS, NASA's reference implementation of the DO-365 detect-and-avoid logic, makes this decision in the classes `WCV_TAUMOD` (the horizontal condition, based on modified tau) and `WCV_TCOA` (the vertical condition). Given the positions and velocities of both aircraft, the component returns the time interval within a lookahead window during which they will not be well clear, assuming straight-line flight, together with a conflict flag and a flag indicating a current violation.

The component is a pure function of its inputs, it is small (335 lines of code in four Java classes), and it is safety-critical. The DAIDALUS repository also contains a [PVS](https://pvs.csl.sri.com/) specification with machine-checked proofs that the interval algorithm is exact in real arithmetic, which provides an answer key for the derived model that is independent of the code.

### Derivation

The 24 requirements in [`derivation/requirements.md`](derivation/requirements.md) were derived from the Java implementation at commit [`1c7b58e5`](https://github.com/nasa/daidalus/tree/1c7b58e5525d5cca91cbbf4a8b7337a488243769). Each requirement links to the upstream source lines from which it was derived, states its relationship to the PVS specification, and lists the checks that verify it. A requirement *agrees* with the specification if it has the same meaning in exact arithmetic; a *convention* is behavior that the code adds (tolerances and boundary handling) and that the specification does not have; and an *assumption* is a precondition that the specification states and that the code does not enforce. The requested improvements (IMP-1 to IMP-3) are not derived from the code; they define what *better* means for this thread.

| Requirement | Title                                                     | PVS        | Original | Regenerated |
|-------------|-----------------------------------------------------------|------------|----------|-------------|
| IF-1        | Inputs and outputs                                        | agrees     | pass     | pass        |
| ENV-1       | Threshold domain                                          | assumption | observed | pass        |
| ENV-2       | Lookahead domain                                          | agrees     | observed | pass        |
| ENV-3       | Operating ranges and threshold tables                     | n/a        | pass     | pass        |
| ENV-4       | Finite inputs                                             | assumption | observed | pass        |
| SEM-1       | Only relative state matters                               | agrees     | pass     | pass        |
| SEM-2       | Horizontal well-clear violation (modified tau)            | agrees     | pass     | pass        |
| SEM-3       | Vertical well-clear violation                             | agrees     | pass     | pass        |
| SEM-4       | Well-clear violation is horizontal and vertical violation | agrees     | pass     | pass        |
| SEM-5       | Detection interval is exact                               | agrees     | pass     | pass        |
| SEM-6       | Symmetry                                                  | agrees     | pass     | pass        |
| SEM-7       | Conflict flag suppresses near-instantaneous loss          | convention | pass     | pass        |
| SEM-8       | Violation flag is derived from detection on [0, 1]        | convention | pass     | pass        |
| NUM-1       | Level-flight snap                                         | convention | pass     | pass        |
| NUM-2       | Stationary-geometry snap                                  | convention | pass     | pass        |
| NUM-3       | Closed boundaries                                         | agrees     | pass     | pass        |
| NUM-4       | Tangency tolerance in the circle-exit root                | convention | pass     | pass        |
| ACC-1       | Semantic cliffs are a declared boundary band              | n/a        | recorded | recorded    |
| ACC-2       | Accuracy outside the band                                 | n/a        | pass     | pass        |
| PERF-1      | Constant time                                             | n/a        | pass     | pass        |
| PERF-2      | Throughput no worse than the original                     | n/a        | baseline | pass        |
| IMP-1       | Explicit errors instead of silent answers                 | n/a        | n/a      | pass        |
| IMP-2       | Memory-safe, panic-free                                   | n/a        | n/a      | pass        |
| IMP-3       | No heap allocation per call                               | n/a        | n/a      | pass        |

The status *observed* indicates that the original component does not enforce an envelope requirement (it sanitizes or silently computes on inputs outside the envelope), and *recorded* indicates that decisions are recorded rather than graded (see ACC-1 below).

### Exact Model

The model in [`src/wellclear/oracle.py`](src/wellclear/oracle.py) converts every input (an IEEE 754 double-precision value) exactly to a rational number and evaluates the requirements in exact arithmetic. Interval endpoints that involve square roots are computed with 90 significant decimal digits. The horizontal and vertical violation sets are computed in closed form from the definitions rather than from the DAIDALUS algorithm, and every interval is cross-checked against the definitional predicate at sample times (the property that is proved in PVS as `WCV_taumod_interval_correct`).

The conflict decision is discontinuous at semantic cliffs: when the horizontal miss distance equals DTHR, the exact violation interval jumps between a duration of TTHR and nothing. Requirement ACC-1 therefore declares a *boundary band* (inputs within a relative margin of `1e-9` of a cliff, or with an exact violation set shorter than `1e-6` seconds) within which any floating-point implementation may legitimately decide either way. Decisions inside the band are recorded but not graded.

### Test Vectors

The corpus in [`data/vectors.csv.gz`](data/vectors.csv.gz) is generated by [`src/wellclear/vectors.py`](src/wellclear/vectors.py) with a fixed seed. It consists of realistic encounters built from closest-point-of-approach geometry within the operating ranges (36,000), a uniform sweep of the operating envelope (12,000), encounters within a tiny relative margin of each semantic cliff (4,800), hand-built edge cases (120), symmetric and translated variants of realistic encounters (6,000), and invalid inputs (63). The corpus is committed because some categories depend on the platform's implementation of trigonometric and power functions; it is only expected to be regenerated bit for bit on Linux (x86-64, glibc 2.39) with CPython 3.13.

### Regenerated Implementation

The regenerated component in [`rust/src/lib.rs`](rust/src/lib.rs) was written from the requirements rather than translated from the Java code, and it uses a different algorithm: the horizontal violation set is computed in closed form over the whole time line and is intersected with the vertical violation set and the lookahead window, using numerically stable quadratic roots. It keeps the DAIDALUS numerical conventions (NUM-1 to NUM-4) so that it can replace the original without changing its answers, and it implements the requested improvements: invalid inputs are rejected with a typed error, the crate forbids unsafe code, and no heap allocation is performed. The JavaScript port in [`web/wellclear.js`](web/wellclear.js) performs the same IEEE 754 operations in the same order; it produced results identical to those of the Rust implementation on every vector, and it runs the explorer on the interactive page.

### Checks

The checker in [`src/wellclear/check.py`](src/wellclear/check.py) grades the original component (run through the harness in [`harness/DaidalusDriver.java`](harness/DaidalusDriver.java)), the Rust implementation, and the JavaScript port against the exact model on every vector, and it compares every pair of implementations. The table below summarizes the results; [`results/summary.json`](results/summary.json) contains every number shown on the interactive page.

| Check                                                     | Original (Java) | Regenerated (Rust) |
|-----------------------------------------------------------|-----------------|--------------------|
| Conflict decisions outside the boundary band              | 55,795 / 55,795 | 55,795 / 55,795    |
| Violation flags outside the boundary band                 | 55,795 / 55,795 | 55,795 / 55,795    |
| Interval endpoints within `1e-6` seconds of the model     | 8,655 / 8,655   | 8,655 / 8,655      |
| Worst endpoint error (seconds)                            | 8.0e-7          | 3.7e-7             |
| Symmetric variants with the same answer                   | 3,000 / 3,000   | 3,000 / 3,000      |
| Translated variants with the same answer                  | 3,000 / 3,000   | 3,000 / 3,000      |
| Boundary-band decisions that agree with the model         | 3,056 / 3,125   | 3,085 / 3,125      |
| Invalid inputs rejected with an error                     | 0 / 63          | 63 / 63            |
| Panics or malformed results in 20,000,000 fuzz iterations | not measured    | 0                  |
| Median time per detection call (nanoseconds)              | 125             | 38                 |
| Heap allocation per detection call (bytes)                | 217             | 0                  |

The exact model also corrected the derivation once. In the first run, it disagreed with the original component on 2 of 600 near-stationary encounters, which showed that the first version of NUM-2 described a numerical shortcut without stating its consequence. The requirement and the grading rule were refined (the history is recorded in the requirement), and the second run was clean.

## Repository Layout

```
├── index.html                  Interactive results page (published using GitHub Pages).
├── Makefile                    Reproduction of every result.
├── data/vectors.csv.gz         Corpus of 58,983 test vectors.
├── derivation/
│   ├── requirements.md         Derived requirements (generated).
│   └── requirements.json       Derived requirements in machine-readable form (generated).
├── harness/DaidalusDriver.java Harness around the unmodified DAIDALUS classes.
├── results/
│   ├── SHA256SUMS              Checksums of the corpus, the oracle records, and the results of each implementation.
│   ├── bench.txt               Benchmark log, including the machine and toolchains.
│   ├── fuzz.txt                Fuzzing log.
│   ├── grades.json             Grading report.
│   └── summary.json            Every number shown on the interactive page.
├── rust/
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs              Regenerated component.
│       └── main.rs             Harness for the regenerated component (run, bench, and fuzz).
├── scripts/fetch-daidalus.sh   Fetches DAIDALUS at the pinned commit.
├── src/wellclear/
│   ├── requirements.py         Derived requirements (the single source of truth).
│   ├── vectors.py              Test-vector generator.
│   ├── oracle.py               Exact model.
│   ├── check.py                Grading of implementations.
│   ├── summary.py              Assembly of the results summary.
│   └── page.py                 Assembly of the interactive page.
├── tests/                      Tests of the Python package and of the committed results.
└── web/
    ├── template.html           Template of the interactive page.
    ├── wellclear.js            JavaScript port of the regenerated component.
    ├── wellclear.test.js       Tests of the JavaScript port.
    └── run-vectors.js          Runs the JavaScript port on the corpus.
```

## Reproducing the Results

Reproduction requires [Python](https://www.python.org/) 3.10 or later, [Java](https://openjdk.org/) 19 or later (earlier versions format some floating-point values differently), [Node.js](https://nodejs.org/) 18 or later, a [Rust](https://www.rust-lang.org/tools/install) toolchain, [Git](https://git-scm.com/), and [GNU Make](https://www.gnu.org/software/make/). The Python package has no dependencies outside the standard library, so no installation is required to reproduce the results. The command below fetches DAIDALUS at the pinned commit into `build/daidalus`, compiles it together with the harness, runs the exact model and all three implementations on the corpus, and compares every output with the committed checksums and results (including the grading report, the fuzzing log, the summary, and the interactive page):
```shell
make verify
```
The corpus can be regenerated and compared with the committed corpus:
```shell
make corpus
```
The benchmark depends on the machine, so `make verify` does not repeat it. It can be run on the current machine, after which the summary and the page can be rebuilt:
```shell
make bench summary page
```
Each step can also be run on its own using the command-line interface of the package (see `python -m wellclear --help`):
```shell
PYTHONPATH=src python -m wellclear requirements derivation
PYTHONPATH=src python -m wellclear oracle build/vectors.csv build/oracle.csv
PYTHONPATH=src python -m wellclear check build/vectors.csv build/oracle.csv build/grades.json \
    orig=build/original.csv rust=build/rust.csv js=build/js.csv
```

## Package Installation and Usage

The Python package can be installed from a clone of this repository using [pip](https://pypi.org/project/pip/):
```shell
python -m pip install .
```
The exact model can be used directly. The example below evaluates a head-on encounter (closing at 400 meters per second from 20 kilometers at the same altitude) against the DO-365 DWC Phase I thresholds:
```python
>>> from wellclear import oracle, vectors
>>> state = ([0, 0, 3000], [200, 0, 0], [20000, 0, 3000], [-200, 0, 0])
>>> case = oracle.encounter(state, vectors.TABLES['P1'])
>>> (found, lo, hi, _) = oracle.detect(case, (0.0, 180.0))
>>> (found, round(float(lo), 6), round(float(hi), 6))
(True, 14.735206, 53.0558)
```
The regenerated component is a Rust library crate:
```rust
use wellclear::{detect, Encounter, Thresholds, Vec3};

let encounter = Encounter {
    so: Vec3::new(0.0, 0.0, 3000.0),
    vo: Vec3::new(200.0, 0.0, 0.0),
    si: Vec3::new(20000.0, 0.0, 3000.0),
    vi: Vec3::new(-200.0, 0.0, 0.0),
};
let detection = detect(&Thresholds::do365_dwc_phase_i(), &encounter, 0.0, 180.0)?;
assert!(detection.conflict());
```
Its JavaScript port can be used in a browser or with Node.js:
```javascript
const wellclear = require("./web/wellclear.js");
const thresholds = wellclear.thresholds(0.66 * 1852, 450 * 0.3048, 35, 0);
const encounter = { so: [0, 0, 3000], vo: [200, 0, 0], si: [20000, 0, 3000], vi: [-200, 0, 0] };
wellclear.detect(thresholds, encounter, 0, 180); // { t_in: 14.73520578109614, t_out: 53.0558 }
```

## Interactive Page

The page [`index.html`](index.html) is a single self-contained file (other than web fonts) that is generated from [`web/template.html`](web/template.html), [`results/summary.json`](results/summary.json), and [`web/wellclear.js`](web/wellclear.js) by `make page`. It is published using [GitHub Pages](https://docs.github.com/en/pages) from the root of the `main` branch; the file [`.nojekyll`](.nojekyll) disables Jekyll processing.

## Development

All development dependencies are specified in `pyproject.toml`. The `project.optional-dependencies` object is used to [specify optional requirements](https://peps.python.org/pep-0621) for various development tasks:
```shell
python -m pip install ".[test,lint]"
```

### Testing and Conventions

All unit tests of the Python package (including the doctests in each module) are executed and their coverage is measured when using [pytest](https://docs.pytest.org) (see the `pyproject.toml` file for configuration details). The tests also check that every committed artifact (the generated requirements, the summary, and the page) is consistent with its sources, and that the factual claims in the notes of the explorer presets hold:
```shell
python -m pytest
```
The tests of the Rust crate (including its documentation tests) and of the JavaScript port can be executed using [Cargo](https://doc.rust-lang.org/cargo/) and the [Node.js test runner](https://nodejs.org/api/test.html):
```shell
cd rust && cargo test --release
node --test web/*.test.js
```
Style conventions are enforced using [Pylint](https://pylint.readthedocs.io), [rustfmt](https://github.com/rust-lang/rustfmt), and [Clippy](https://doc.rust-lang.org/clippy/):
```shell
python -m pylint src/wellclear
cd rust && cargo fmt --check && cargo clippy --all-targets -- -D warnings
```
The commands `make test` and `make lint` run all of the above.

### Contributions

In order to contribute to the source code, open an issue or submit a pull request on the [GitHub page](../..) for this repository.

### Versioning

The version number format for this repository and the changes to the repository associated with version number increments conform with [Semantic Versioning 2.0.0](https://semver.org/#semantic-versioning-200).

## Scope

This thread covers one small, stateless component. The requirements were derived and the Rust implementation was written in the same context, after reading the Java code, so it is not a clean-room regeneration. The exact model is checked against the PVS lemmas by sampling rather than by proof, and the Java timings come from a hand-written measurement loop rather than from [JMH](https://github.com/openjdk/jmh). The regenerated component is a research artifact and has not been certified for operational use. The interactive page lists the limitations and further work in more detail.

DAIDALUS is developed by NASA Langley Research Center and released under the [NASA Open Source Agreement](https://github.com/nasa/daidalus/tree/1c7b58e5525d5cca91cbbf4a8b7337a488243769/LICENSES). It is not redistributed in this repository: `scripts/fetch-daidalus.sh` fetches it at the pinned commit during the build. This repository is independent of NASA.
