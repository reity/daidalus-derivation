import Wellclear.Interval

/-!
# Certificate checker

An executable checker for the answers of an implementation, and its soundness theorems.

The checker runs over the rational numbers: every IEEE 754 double is a rational number, so the
inputs and the answer of an implementation are represented exactly. It decides which guarantee an
answer carries with respect to the requirements over the real numbers:

* `certify_interval`: a certified conflict answer satisfies `Within` (SEM-5 within the endpoint
  tolerance of ACC-2);
* `certify_empty`: a certified no-conflict answer means that there is no violation within the
  lookahead window;
* `certify_short`: a no-conflict answer certified as short means that every violation within the
  window lies within the tolerance of the (untrusted) hint, so that the answer suppresses at most a
  near-instantaneous loss of well-clear (SEM-7).

By the definition of `certify`, `.interval` is only returned for a conflict answer with finite
endpoints, and `.empty` and `.short` only for a no-conflict answer, so the three theorems cover
every verdict that the checker gives. They hold for every input and do not depend on how the
implementation computed its answer: an implementation is checked one answer at a time, against the
requirements themselves.
-/

namespace Wellclear

/-- The endpoint tolerance of ACC-2: one microsecond. -/
def tolerance : ℚ := 1 / 1000000

theorem tolerance_pos : 0 < tolerance := by
  unfold tolerance; norm_num

/-- An implementation's answer for one test vector. -/
inductive Answer where
  /-- A conflict reported on `[tin, tout]`; `none` stands for an endpoint that is not finite. -/
  | conflict (tin tout : Option ℚ)
  /-- No conflict. -/
  | clear

/-- The guarantee that the checker establishes for an answer. -/
inductive Verdict where
  /-- A conflict answer that satisfies `Within` with the tolerance of ACC-2. -/
  | interval
  /-- A no-conflict answer, and there is no violation within the lookahead window. -/
  | empty
  /-- A no-conflict answer that satisfies `Short` with the tolerance of ACC-2. -/
  | short
  /-- No guarantee could be established. -/
  | uncertified
  /-- The input lies outside the domain of the requirements (ENV-1, ENV-2, ENV-4). -/
  | invalid
  deriving DecidableEq

/-- The name of a verdict, as written in the verdict files. -/
def Verdict.name : Verdict → String
  | .interval => "interval"
  | .empty => "empty"
  | .short => "short"
  | .uncertified => "uncertified"
  | .invalid => "invalid"

/-- The start of the inner interval at which a violation is checked for a reported conflict. -/
def innerLo (tin tout : ℚ) : ℚ :=
  if tout - tolerance < tin + tolerance then (tin + tout) / 2 else tin + tolerance

/-- The end of the inner interval at which a violation is checked for a reported conflict. -/
def innerHi (tin tout : ℚ) : ℚ :=
  if tout - tolerance < tin + tolerance then (tin + tout) / 2 else tout - tolerance

/-- The checker, for the relative position `s` and velocity `v`, the lookahead window `[B, T]`,
an answer, and a hint (used only for no-conflict answers). -/
def certify (p : Table ℚ) (s v : Vec3 ℚ) (B T : ℚ) : Answer → ℚ → Verdict
  | .conflict (some tin) (some tout), _ =>
    if tout < tin then .uncertified
    else if ClearTest p s v B (tin - tolerance) ∧ ClearTest p s v (tout + tolerance) T ∧
        PointTest p s v (innerLo tin tout) ∧ PointTest p s v (innerHi tin tout) then .interval
    else .uncertified
  | .conflict _ _, _ => .uncertified
  | .clear, hint =>
    if ClearTest p s v B T then .empty
    else if ClearTest p s v B (hint - tolerance) ∧ ClearTest p s v (hint + tolerance) T then .short
    else .uncertified

theorem innerLo_bounds {tin tout : ℚ} (h : tin ≤ tout) :
    tin - tolerance ≤ innerLo tin tout ∧ innerLo tin tout ≤ tin + tolerance := by
  have := tolerance_pos
  unfold innerLo
  split_ifs with h' <;> constructor <;> linarith

theorem innerHi_bounds {tin tout : ℚ} (h : tin ≤ tout) :
    tout - tolerance ≤ innerHi tin tout ∧ innerHi tin tout ≤ tout + tolerance := by
  have := tolerance_pos
  unfold innerHi
  split_ifs with h' <;> constructor <;> linarith

theorem innerLo_le_innerHi (tin tout : ℚ) : innerLo tin tout ≤ innerHi tin tout := by
  unfold innerLo innerHi
  split_ifs with h' <;> (try push Not at h') <;> linarith

/-- A certified conflict answer satisfies SEM-5 within the tolerance of ACC-2. -/
theorem certify_interval {p : Table ℚ} {s v : Vec3 ℚ} {B T hint tin tout : ℚ} (hp : p.Valid)
    (hc : certify p s v B T (.conflict (some tin) (some tout)) hint = .interval) :
    Within p.toReal s.toReal v.toReal B T tolerance tin tout := by
  simp only [certify] at hc
  by_cases h1 : tout < tin
  · rw [ite_eq_left h1] at hc; exact absurd hc (by decide)
  rw [ite_eq_right h1] at hc
  by_cases h2 : ClearTest p s v B (tin - tolerance) ∧ ClearTest p s v (tout + tolerance) T ∧
      PointTest p s v (innerLo tin tout) ∧ PointTest p s v (innerHi tin tout)
  swap
  · rw [ite_eq_right h2] at hc; exact absurd hc (by decide)
  obtain ⟨c1, c2, c3, c4⟩ := h2
  have hpR := valid_toReal hp
  have hle : tin ≤ tout := not_lt.mp h1
  have e1 := clear_of_clearTest _ _ _ _ _ hpR
    ((clearTest_toReal p s v B (tin - tolerance)).mpr c1)
  have e2 := clear_of_clearTest _ _ _ _ _ hpR
    ((clearTest_toReal p s v (tout + tolerance) T).mpr c2)
  have w3 := (pointTest_iff _ _ _ _ hpR).mp ((pointTest_toReal p s v (innerLo tin tout)).mpr c3)
  have w4 := (pointTest_iff _ _ _ _ hpR).mp ((pointTest_toReal p s v (innerHi tin tout)).mpr c4)
  push_cast at e1 e2
  obtain ⟨b1, b2⟩ := innerLo_bounds hle
  obtain ⟨b3, b4⟩ := innerHi_bounds hle
  have b5 := innerLo_le_innerHi tin tout
  refine ⟨e1, e2, innerLo tin tout, innerHi tin tout, ?_, ?_, ?_, ?_, ?_,
    lost_of_endpoints _ _ _ hpR w3 w4⟩
  · exact_mod_cast b1
  · exact_mod_cast b2
  · exact_mod_cast b3
  · exact_mod_cast b4
  · exact_mod_cast b5

/-- A no-conflict answer certified as empty: there is no violation within the window. -/
theorem certify_empty {p : Table ℚ} {s v : Vec3 ℚ} {B T hint : ℚ} (hp : p.Valid)
    (hc : certify p s v B T .clear hint = .empty) : Clear p.toReal s.toReal v.toReal B T := by
  simp only [certify] at hc
  by_cases h1 : ClearTest p s v B T
  · exact clear_of_clearTest _ _ _ _ _ (valid_toReal hp) ((clearTest_toReal p s v B T).mpr h1)
  rw [ite_eq_right h1] at hc
  by_cases h2 : ClearTest p s v B (hint - tolerance) ∧ ClearTest p s v (hint + tolerance) T
  · rw [ite_eq_left h2] at hc; exact absurd hc (by decide)
  · rw [ite_eq_right h2] at hc; exact absurd hc (by decide)

/-- A no-conflict answer certified as short: every violation within the window lies within the
tolerance of the hint. -/
theorem certify_short {p : Table ℚ} {s v : Vec3 ℚ} {B T hint : ℚ} (hp : p.Valid)
    (hc : certify p s v B T .clear hint = .short) :
    Short p.toReal s.toReal v.toReal B T tolerance hint := by
  simp only [certify] at hc
  by_cases h1 : ClearTest p s v B T
  · rw [ite_eq_left h1] at hc; exact absurd hc (by decide)
  rw [ite_eq_right h1] at hc
  by_cases h2 : ClearTest p s v B (hint - tolerance) ∧ ClearTest p s v (hint + tolerance) T
  swap
  · rw [ite_eq_right h2] at hc; exact absurd hc (by decide)
  obtain ⟨c1, c2⟩ := h2
  have hpR := valid_toReal hp
  have e1 := clear_of_clearTest _ _ _ _ _ hpR
    ((clearTest_toReal p s v B (hint - tolerance)).mpr c1)
  have e2 := clear_of_clearTest _ _ _ _ _ hpR
    ((clearTest_toReal p s v (hint + tolerance) T).mpr c2)
  push_cast at e1 e2
  exact ⟨e1, e2⟩

end Wellclear
