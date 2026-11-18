import Wellclear.Spec

/-!
# Sign tests

Decision procedures for the requirements that use only field operations and comparisons, so that
they can be evaluated exactly over the rational numbers. The square roots of the closed-form
solution are replaced by sign tests of quadratic polynomials: `RTest t` holds exactly when `t` is
at or after the smaller root of `qTau`, and `XTest t` exactly when `t` is at or before the exit
from the DTHR circle (the larger root of `qD`).

`Wellclear.Interval` proves that `PointTest` is equivalent to a violation (`WCVAt`) and that
`ClearTest` implies that there is no violation in an interval (`Clear`). The last section of this
file shows that the tests give the same answer over the rationals and over the reals, which is
how the rational computation of the checker is transferred to the real-number requirements.
-/

namespace Wellclear

section Tests

variable {K : Type*} [Field K] [LinearOrder K]

/-- `t` is at or after the smaller root of `qTau`: either `qTau t ≤ 0`, or `t` is at or after the
vertex of `qTau`. -/
def RTest (p : Table K) (s v : Vec3 K) (t : K) : Prop :=
  qTau p s v t ≤ 0 ∨ 0 ≤ 2 * uAt s v t + p.tthr * hA v

/-- `t` is at or before the exit from the DTHR circle: either `qD t ≤ 0` (inside the circle), or
`t` is at or before the time of closest approach. -/
def XTest (p : Table K) (s v : Vec3 K) (t : K) : Prop :=
  qD p s v t ≤ 0 ∨ uAt s v t ≤ 0

/-- The horizontal miss distance is at most DTHR (for a nonzero relative horizontal speed). -/
def HmdTest (p : Table K) (s v : Vec3 K) : Prop :=
  hCross s v ^ 2 ≤ p.dthr ^ 2 * hA v

/-- The extent of the vertical violation set on the converging side, `max ZTHR (|vz| TCOA)`. -/
def act (p : Table K) (v : Vec3 K) : K := max p.zthr (max v.z (-v.z) * p.tcoa)

/-- The first time of the vertical violation set (for a nonzero vertical speed). -/
def vLo (p : Table K) (s v : Vec3 K) : K :=
  if 0 < v.z then (-act p v - s.z) / v.z else (act p v - s.z) / v.z

/-- The last time of the vertical violation set (for a nonzero vertical speed). -/
def vHi (p : Table K) (s v : Vec3 K) : K :=
  if 0 < v.z then (p.zthr - s.z) / v.z else (-p.zthr - s.z) / v.z

/-- The start of the intersection of `[lo, hi]` with the vertical violation set. -/
def winLo (p : Table K) (s v : Vec3 K) (lo : K) : K :=
  if v.z = 0 then lo else max lo (vLo p s v)

/-- The end of the intersection of `[lo, hi]` with the vertical violation set. -/
def winHi (p : Table K) (s v : Vec3 K) (hi : K) : K :=
  if v.z = 0 then hi else min hi (vHi p s v)

/-- A test that implies that there is no violation in `[lo, hi]` (`clear_of_clearTest`): the
interval is empty, or misses the vertical violation set, or misses the horizontal one. The
horizontal violation set is an interval from the smaller root of `qTau` to the exit from the
DTHR circle, so it misses `[winLo, winHi]` if `winHi` is before the root or `winLo` after the
exit. -/
def ClearTest (p : Table K) (s v : Vec3 K) (lo hi : K) : Prop :=
  hi < lo ∨ (v.z = 0 ∧ (s.z < -p.zthr ∨ p.zthr < s.z)) ∨ winHi p s v hi < winLo p s v lo ∨
    (hA v = 0 ∧ p.dthr ^ 2 < hSS s) ∨
    (hA v ≠ 0 ∧ ¬ (HmdTest p s v ∧ RTest p s v (winHi p s v hi) ∧ XTest p s v (winLo p s v lo)))

/-- A test that is equivalent to a violation at time `t` (`pointTest_iff`). -/
def PointTest (p : Table K) (s v : Vec3 K) (t : K) : Prop :=
  (hA v = 0 ∧ hSS s ≤ p.dthr ^ 2 ∨ hA v ≠ 0 ∧ HmdTest p s v ∧ RTest p s v t ∧ XTest p s v t) ∧
    (v.z = 0 ∧ -p.zthr ≤ s.z ∧ s.z ≤ p.zthr ∨ v.z ≠ 0 ∧ vLo p s v ≤ t ∧ t ≤ vHi p s v)

instance (p : Table K) (s v : Vec3 K) (lo hi : K) : Decidable (ClearTest p s v lo hi) := by
  unfold ClearTest HmdTest RTest XTest; infer_instance

instance (p : Table K) (s v : Vec3 K) (t : K) : Decidable (PointTest p s v t) := by
  unfold PointTest HmdTest RTest XTest; infer_instance

end Tests

section Cast

/-- The real vector with the same (rational) components. -/
noncomputable def Vec3.toReal (v : Vec3 ℚ) : Vec3 ℝ := ⟨v.x, v.y, v.z⟩

/-- The real threshold table with the same (rational) thresholds. -/
noncomputable def Table.toReal (p : Table ℚ) : Table ℝ := ⟨p.dthr, p.zthr, p.tthr, p.tcoa⟩

@[simp] theorem Vec3.toReal_x (v : Vec3 ℚ) : v.toReal.x = v.x := rfl
@[simp] theorem Vec3.toReal_y (v : Vec3 ℚ) : v.toReal.y = v.y := rfl
@[simp] theorem Vec3.toReal_z (v : Vec3 ℚ) : v.toReal.z = v.z := rfl
@[simp] theorem Table.toReal_dthr (p : Table ℚ) : p.toReal.dthr = p.dthr := rfl
@[simp] theorem Table.toReal_zthr (p : Table ℚ) : p.toReal.zthr = p.zthr := rfl
@[simp] theorem Table.toReal_tthr (p : Table ℚ) : p.toReal.tthr = p.tthr := rfl
@[simp] theorem Table.toReal_tcoa (p : Table ℚ) : p.toReal.tcoa = p.tcoa := rfl

@[simp] theorem hA_toReal (v : Vec3 ℚ) : hA v.toReal = ((hA v : ℚ) : ℝ) := by
  simp [hA]

@[simp] theorem hB_toReal (s v : Vec3 ℚ) : hB s.toReal v.toReal = ((hB s v : ℚ) : ℝ) := by
  simp [hB]

@[simp] theorem hSS_toReal (s : Vec3 ℚ) : hSS s.toReal = ((hSS s : ℚ) : ℝ) := by
  simp [hSS]

@[simp] theorem hCross_toReal (s v : Vec3 ℚ) :
    hCross s.toReal v.toReal = ((hCross s v : ℚ) : ℝ) := by
  simp [hCross]

@[simp] theorem uAt_toReal (s v : Vec3 ℚ) (t : ℚ) :
    uAt s.toReal v.toReal t = ((uAt s v t : ℚ) : ℝ) := by
  simp [uAt]

@[simp] theorem qD_toReal (p : Table ℚ) (s v : Vec3 ℚ) (t : ℚ) :
    qD p.toReal s.toReal v.toReal t = ((qD p s v t : ℚ) : ℝ) := by
  simp [qD]

@[simp] theorem qTau_toReal (p : Table ℚ) (s v : Vec3 ℚ) (t : ℚ) :
    qTau p.toReal s.toReal v.toReal t = ((qTau p s v t : ℚ) : ℝ) := by
  simp [qTau]

@[simp] theorem act_toReal (p : Table ℚ) (v : Vec3 ℚ) :
    act p.toReal v.toReal = ((act p v : ℚ) : ℝ) := by
  simp [act]

@[simp] theorem vLo_toReal (p : Table ℚ) (s v : Vec3 ℚ) :
    vLo p.toReal s.toReal v.toReal = ((vLo p s v : ℚ) : ℝ) := by
  by_cases h : 0 < v.z <;> simp [vLo, h]

@[simp] theorem vHi_toReal (p : Table ℚ) (s v : Vec3 ℚ) :
    vHi p.toReal s.toReal v.toReal = ((vHi p s v : ℚ) : ℝ) := by
  by_cases h : 0 < v.z <;> simp [vHi, h]

@[simp] theorem winLo_toReal (p : Table ℚ) (s v : Vec3 ℚ) (lo : ℚ) :
    winLo p.toReal s.toReal v.toReal lo = ((winLo p s v lo : ℚ) : ℝ) := by
  by_cases h : v.z = 0 <;> simp [winLo, h]

@[simp] theorem winHi_toReal (p : Table ℚ) (s v : Vec3 ℚ) (hi : ℚ) :
    winHi p.toReal s.toReal v.toReal hi = ((winHi p s v hi : ℚ) : ℝ) := by
  by_cases h : v.z = 0 <;> simp [winHi, h]

theorem rTest_toReal (p : Table ℚ) (s v : Vec3 ℚ) (t : ℚ) :
    RTest p.toReal s.toReal v.toReal t ↔ RTest p s v t := by
  simp only [RTest, qTau_toReal, uAt_toReal, hA_toReal, Table.toReal_tthr]
  norm_cast

theorem xTest_toReal (p : Table ℚ) (s v : Vec3 ℚ) (t : ℚ) :
    XTest p.toReal s.toReal v.toReal t ↔ XTest p s v t := by
  simp only [XTest, qD_toReal, uAt_toReal]
  norm_cast

theorem hmdTest_toReal (p : Table ℚ) (s v : Vec3 ℚ) :
    HmdTest p.toReal s.toReal v.toReal ↔ HmdTest p s v := by
  simp only [HmdTest, hCross_toReal, hA_toReal, Table.toReal_dthr]
  norm_cast

/-- The vacuity test, evaluated over the rationals, gives the same answer over the reals. -/
theorem clearTest_toReal (p : Table ℚ) (s v : Vec3 ℚ) (lo hi : ℚ) :
    ClearTest p.toReal s.toReal v.toReal lo hi ↔ ClearTest p s v lo hi := by
  simp only [ClearTest, winLo_toReal, winHi_toReal, rTest_toReal, xTest_toReal, hmdTest_toReal,
    hA_toReal, hSS_toReal, Vec3.toReal_z, Table.toReal_zthr, Table.toReal_dthr]
  norm_cast

/-- The violation test, evaluated over the rationals, gives the same answer over the reals. -/
theorem pointTest_toReal (p : Table ℚ) (s v : Vec3 ℚ) (t : ℚ) :
    PointTest p.toReal s.toReal v.toReal t ↔ PointTest p s v t := by
  simp only [PointTest, rTest_toReal, xTest_toReal, hmdTest_toReal, hA_toReal, hSS_toReal,
    vLo_toReal, vHi_toReal, Vec3.toReal_z, Table.toReal_zthr, Table.toReal_dthr]
  norm_cast

theorem valid_toReal {p : Table ℚ} (hp : p.Valid) : p.toReal.Valid := by
  obtain ⟨h1, h2, h3, h4⟩ := hp
  exact ⟨by simpa using h1, by simpa using h2, by simpa using h3, by simpa using h4⟩

end Cast

end Wellclear
