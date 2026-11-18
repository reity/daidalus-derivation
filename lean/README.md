# Lean Formalization

The derived requirements of the well-clear component stated in [Lean 4](https://lean-lang.org/) with [Mathlib](https://github.com/leanprover-community/mathlib4), machine-checked theorems about them, and a checker that certifies the answers of an implementation against them. This directory explores three ways of connecting an implementation to requirements stated in Lean:

1. certifying every answer of the implementation against the requirements (implemented);
2. translating the implementation into Lean and proving it correct (assessed, not attempted);
3. deriving the implementation from the requirements (the closed-form algorithm is derived and proved; generating the code is the next step).

The development compiles with Lean 4.35.0 and Mathlib `v4.35.0`, without `sorry`, and its main theorems depend only on the standard axioms `propext`, `Classical.choice`, and `Quot.sound` (see [`results/axioms.txt`](../results/axioms.txt)). For every answer of the three implementations, the Lean checker gives the same verdict as its executable twin, [`src/wellclear/certify.py`](../src/wellclear/certify.py). The [`lean`](../.github/workflows/lean.yml) workflow repeats these checks on every push.

## Requirements in Lean

The semantic requirements are stated over the real numbers in [`Wellclear/Spec.lean`](Wellclear/Spec.lean), following the text of [`derivation/requirements.md`](../derivation/requirements.md) literally (divisions included). The theorems are proved from these definitions.

| Requirement | Definitions                                                    | Theorems                                                         |
|-------------|----------------------------------------------------------------|------------------------------------------------------------------|
| ENV-1       | `Table.Valid`                                                  |                                                                  |
| SEM-1       | `rel`                                                          | `rel_add`: translating both aircraft does not change `rel`       |
| SEM-2       | `Horizontal`, `tcpa`, `hmd2`, `taumod`                         | `horizontal_along_iff`, `horizontal_along_iff_roots`             |
| SEM-3       | `Vertical`, `tcoa`                                             | `vertical_along_iff`                                             |
| SEM-4       | `WCV`, `WCVAt`                                                 | `pointTest_iff`                                                  |
| SEM-5       | `Clear`, `Lost`, `Within`                                      | `violations_ordConnected`, `violations_eq_Icc`                   |
| SEM-6       |                                                                | `wcv_swap`: exchanging ownship and intruder changes nothing      |
| SEM-7       | `Short`                                                        | `certify_short`                                                  |
| ACC-2       | `tolerance` (one microsecond), `Within`                        | `certify_interval`, `certify_empty`                              |

`violations_ordConnected` states that the times at which the well-clear violation holds form an interval, the fact that DAIDALUS relies on and that is proved in PVS as `WCV_taumod_interval_correct`. `violations_eq_Icc` gives that interval in closed form.

The numerical conventions (NUM-1 to NUM-4), the floating-point tolerance of SEM-7, and the definition of the violation flag (SEM-8) concern floating-point implementations and are not part of this exact semantics. The boundary band of ACC-1 is not formalized either: the checker does not need it, because it only certifies what it can prove.

## 1. Certifying Every Answer

[`Wellclear/Check.lean`](Wellclear/Check.lean) defines a checker, `certify`, that runs over the rational numbers. Every IEEE 754 double is a rational number, so the inputs and the answer of an implementation are represented exactly. The square roots of the closed-form solution are replaced by sign tests of quadratic polynomials ([`Wellclear/Tests.lean`](Wellclear/Tests.lean)), so the checker needs no approximation. It gives one of the following verdicts for each answer, and a soundness theorem states what each verdict guarantees over the real numbers.

| Verdict       | Answer      | Guarantee                                                                                                                                                                       | Theorem            |
|---------------|-------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------|
| `interval`    | conflict    | No violation within the window before `t_in - ε` or after `t_out + ε`, and a violation at every time of a nonempty interval whose endpoints lie within `ε` of `t_in` and `t_out` | `certify_interval` |
| `empty`       | no conflict | No violation at any time of the lookahead window                                                                                                                                | `certify_empty`    |
| `short`       | no conflict | Every violation within the window lies within `ε` of a hint (a near-instantaneous loss of well-clear, which SEM-7 suppresses)                                                    | `certify_short`    |
| `uncertified` | either      | None                                                                                                                                                                            |                    |

The tolerance `ε` is one microsecond (ACC-2). The theorems hold for every input, so they do not depend on how the implementation computed its answer, on the floating-point behavior of the machine that ran it, or on the hint (which is untrusted and taken from the exact model). The proofs rest on two facts proved in [`Wellclear/Interval.lean`](Wellclear/Interval.lean): the set of violation times is an interval, and the sign tests are equivalent to the requirements. The checker reads the bit patterns of the doubles and decodes them exactly ([`Main.lean`](Main.lean)); this decoding and the reading of the files are the only parts of the checker that are not covered by a theorem.

The Lean checker gives the verdicts below for the corpus of 58,983 test vectors, the same as its twin for every answer (see [`results/certify.json`](../results/certify.json)). The JavaScript port gives the same answers as the Rust implementation, bit for bit, and therefore receives the same verdicts.

| Verdict                                              | Original (Java) | Regenerated (Rust) |
|------------------------------------------------------|-----------------|--------------------|
| `interval`                                           | 10,212          | 10,260             |
| `empty`                                              | 48,588          | 48,585             |
| `short`                                              | 45              | 10                 |
| `uncertified`                                        | 75              | 65                 |
| Invalid input (outside ENV-1, ENV-2, and ENV-4)      | 63              | 63                 |
| Certified outside the boundary band and conventions  | 55,793 / 55,793 | 55,793 / 55,793    |

Every uncertified answer lies in the boundary band of ACC-1 or follows a numerical convention that deviates from the exact semantics by design (NUM-1 or NUM-2). For example, with a TTHR of zero, a trajectory that touches the DTHR circle is a violation at a single instant; the Rust implementation reports a conflict that lasts 0.2 microseconds and ends 0.1 microseconds after the touching point, and the checker leaves the answer uncertified because its midpoint is not a violation time. As an independent check of the soundness theorems, every certified verdict was compared with the exact model; none disagrees.

This approach is related to the *differential random testing* used to check production code against a Lean model in the development of AWS Cedar. In that approach, the model and the production code are run on the same random inputs and their outputs are compared. Here, each answer of the implementation is checked against the requirements themselves, and a verdict carries a proof rather than an agreement. The checker is small enough to run beside the implementation, as a monitor that accepts an answer only with a certificate.

## 2. Translating the Implementation into Lean

The Rust crate could be translated into Lean and proved correct directly. [hax](https://hax.cryspen.com/) (from version 0.4) and [Aeneas](https://github.com/AeneasVerif/aeneas) translate a subset of safe Rust into pure functional Lean code, and they have been used on integer and cryptographic code. Two questions decide whether this route applies to this crate, and neither could be settled without installing the tools.

* **Support for `f64`.** The Aeneas documentation lists its unsupported features without mentioning floating-point types, and the published uses verify integer code.
* **Floating-point reasoning.** Recent Lean releases give `Float` a logical model in terms of IEEE 754 bit patterns, including arithmetic and the square root, but the reference documentation states that this model is not meant to be the basis of a floating-point library. Error bounds would come from a library such as [Flean](https://github.com/MinusGix/flean) or [FloatSpec](https://reservoir.lean-lang.org/@Beneficial-AI-Foundation/FloatSpec) (a port of Flocq), both of which are early.

If both are resolved, a translation would give theorems about the Rust code itself, subject to trust in the translation. Until then, certification gives a guarantee for every answer that is actually computed.

## 3. Deriving the Implementation from the Requirements

[`Wellclear/Roots.lean`](Wellclear/Roots.lean) derives the algorithm of the regenerated implementation from the requirements over the real numbers. `horizontal_along_iff_roots` shows that the horizontal violation set is the interval from the smaller root of `qTau` (where the modified tau reaches TTHR) to the larger root of `qD` (the exit from the DTHR circle), and `violations_eq_Icc` intersects it with the vertical violation set and the lookahead window. `stableRoots_eq` shows that the numerically stable root formula of `roots` in [`rust/src/lib.rs`](../rust/src/lib.rs) computes these roots, and `stableRoots_tau` and `stableRoots_circle` apply it to the coefficients that `horizontal_set` uses.

The next steps are to write the algorithm once in Lean, generate the Rust and JavaScript code from it, and compare the generated code bit for bit with the current implementation by evaluating the Lean definition with `Float`. Proving that the generated code meets the requirements despite rounding would then need an error analysis. In the meantime, the rounding is covered answer by answer by the checker.

## Building

The toolchain is pinned in [`lean-toolchain`](lean-toolchain) (Lean 4.35.0), Mathlib is required at the matching release in [`lakefile.toml`](lakefile.toml), and the revisions of Mathlib and its dependencies are recorded in [`lake-manifest.json`](lake-manifest.json). With [elan](https://github.com/leanprover/elan) installed, the following commands fetch the packages and the compiled Mathlib library and then build the development, which checks every proof:
```shell
cd lean
lake exe cache get
lake build
```
The axioms on which the main theorems depend are listed by `lake env lean scripts/axioms.lean`. From the root of the repository, the command below runs the exact model and every implementation, compares the axioms with [`results/axioms.txt`](../results/axioms.txt), certifies the answers with the Lean checker (run by the Lean interpreter, `lake env lean --run Main.lean certify INPUT OUTPUT`), and compares its verdicts with those of the executable twin:
```shell
make lean
```

## Files

```
├── lake-manifest.json     Revisions of Mathlib and its dependencies.
├── lakefile.toml          Lake configuration (Mathlib dependency, library, and executable).
├── lean-toolchain         Pinned Lean version.
├── Main.lean              Command-line checker (certify INPUT OUTPUT).
├── Wellclear/
│   ├── Basic.lean         Vectors, thresholds, and the polynomial quantities (over any field).
│   ├── Spec.lean          Requirements over the real numbers.
│   ├── Tests.lean         Sign tests, and their transfer from the rationals to the reals.
│   ├── Interval.lean      Theorems: violation set, sign tests, and symmetry.
│   ├── Check.lean         Checker and its soundness theorems.
│   └── Roots.lean         Closed form and the stable root formula.
└── scripts/axioms.lean    Lists the axioms on which the main theorems depend.
```
