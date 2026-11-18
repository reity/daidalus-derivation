import Wellclear.Interval

/-!
# Closed form

The closed form that the regenerated implementation computes, derived from the requirements.

* `horizontal_along_iff_roots`: when the horizontal miss distance is at most DTHR, the horizontal
  violation set along the trajectory (SEM-2) is `[rIn, tOut]`, from the smaller root of `qTau`
  (where the modified tau reaches TTHR) to the larger root of `qD` (the exit from the DTHR
  circle);
* `violations_eq_Icc`: the detection interval within the lookahead window (SEM-5) is
  `[max B (max vLo rIn), min T (min vHi tOut)]`;
* `stableRoots_eq`: the numerically stable root formula of `roots` in `rust/src/lib.rs` (and of
  its JavaScript port) computes the textbook roots, so that `stableRoots_tau` and
  `stableRoots_circle` give `rIn` and `tOut` from the same coefficients as `horizontal_set`.

Together with `vertical_along_iff`, these theorems derive the algorithm of the regenerated
implementation from the requirements, over the real numbers. The floating-point rounding of the
implementation is outside their scope; it is covered by the certificate checker
(`Wellclear.Check`), which checks the floating-point answers one by one.
-/

noncomputable section

namespace Wellclear

/-- Half the linear coefficient of `qTau` as a polynomial in `t`. -/
def hbTau (p : Table ℝ) (s v : Vec3 ℝ) : ℝ := hB s v + p.tthr * hA v / 2

/-- The constant coefficient of `qTau` as a polynomial in `t`. -/
def cTau (p : Table ℝ) (s v : Vec3 ℝ) : ℝ := hSS s - p.dthr ^ 2 + p.tthr * hB s v

/-- The quarter discriminant of `qD`. -/
def discD (p : Table ℝ) (s v : Vec3 ℝ) : ℝ := hB s v ^ 2 - hA v * (hSS s - p.dthr ^ 2)

/-- The quarter discriminant of `qTau`. -/
def discTau (p : Table ℝ) (s v : Vec3 ℝ) : ℝ := hbTau p s v ^ 2 - hA v * cTau p s v

/-- The first time at which a converging modified tau is at most TTHR: the smaller root of
`qTau`. -/
def rIn (p : Table ℝ) (s v : Vec3 ℝ) : ℝ := (-hbTau p s v - Real.sqrt (discTau p s v)) / hA v

/-- The exit time from the DTHR circle: the larger root of `qD`. -/
def tOut (p : Table ℝ) (s v : Vec3 ℝ) : ℝ := (-hB s v + Real.sqrt (discD p s v)) / hA v

theorem discD_eq (p : Table ℝ) (s v : Vec3 ℝ) :
    discD p s v = p.dthr ^ 2 * hA v - hCross s v ^ 2 := by
  simp only [discD, hB, hA, hSS, hCross]; ring

theorem discTau_eq (p : Table ℝ) (s v : Vec3 ℝ) :
    discTau p s v = discD p s v + (p.tthr * hA v / 2) ^ 2 := by
  simp only [discTau, discD, hbTau, cTau]; ring

theorem hA_mul_qTau (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) :
    hA v * qTau p s v t = (hA v * t + hbTau p s v) ^ 2 - discTau p s v := by
  simp only [qTau, qD, uAt, discTau, hbTau, cTau]; ring

theorem hA_mul_qD' (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) :
    hA v * qD p s v t = (hA v * t + hB s v) ^ 2 - discD p s v := by
  simp only [qD, discD]; ring

/-- `RTest t` holds exactly when `t` is at or after the smaller root of `qTau`. -/
theorem rTest_iff (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) (hA0 : 0 < hA v)
    (hd : 0 ≤ discTau p s v) : RTest p s v t ↔ rIn p s v ≤ t := by
  have hI := hA_mul_qTau p s v t
  have hsq := Real.sq_sqrt hd
  have hs := Real.sqrt_nonneg (discTau p s v)
  have hR : 2 * uAt s v t + p.tthr * hA v = 2 * (hA v * t + hbTau p s v) := by
    simp only [uAt, hbTau]; ring
  have hr : rIn p s v ≤ t ↔ -Real.sqrt (discTau p s v) ≤ hA v * t + hbTau p s v := by
    unfold rIn
    rw [div_le_iff_pos_den hA0]
    constructor <;> intro h <;> linarith
  rw [hr]
  unfold RTest
  rw [hR]
  constructor
  · rintro (h | h)
    · by_contra hlt
      push Not at hlt
      have h1 : 0 < -(hA v * t + hbTau p s v) - Real.sqrt (discTau p s v) := by linarith
      have h2 : 0 < -(hA v * t + hbTau p s v) + Real.sqrt (discTau p s v) := by linarith
      nlinarith [mul_pos h1 h2, mul_nonneg hA0.le (neg_nonneg.mpr h)]
    · linarith
  · intro h
    by_cases h0 : 0 ≤ hA v * t + hbTau p s v
    · right; linarith
    · left
      push Not at h0
      have h3 : (hA v * t + hbTau p s v) ^ 2 ≤ discTau p s v := by
        nlinarith [mul_nonneg (show 0 ≤ hA v * t + hbTau p s v + Real.sqrt (discTau p s v) by
            linarith) (show 0 ≤ -(hA v * t + hbTau p s v) + Real.sqrt (discTau p s v) by linarith)]
      by_contra hq
      push Not at hq
      nlinarith [mul_pos hA0 hq]

/-- `XTest t` holds exactly when `t` is at or before the exit from the DTHR circle. -/
theorem xTest_iff (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) (hA0 : 0 < hA v)
    (hd : 0 ≤ discD p s v) : XTest p s v t ↔ t ≤ tOut p s v := by
  have hI := hA_mul_qD' p s v t
  have hsq := Real.sq_sqrt hd
  have hs := Real.sqrt_nonneg (discD p s v)
  have hu : uAt s v t = hA v * t + hB s v := by
    simp only [uAt]; ring
  have hr : t ≤ tOut p s v ↔ hA v * t + hB s v ≤ Real.sqrt (discD p s v) := by
    unfold tOut
    rw [le_div_iff_pos_den hA0]
    constructor <;> intro h <;> linarith
  rw [hr]
  unfold XTest
  rw [hu]
  constructor
  · rintro (h | h)
    · by_contra hlt
      push Not at hlt
      have h1 : 0 < hA v * t + hB s v - Real.sqrt (discD p s v) := by linarith
      have h2 : 0 < hA v * t + hB s v + Real.sqrt (discD p s v) := by linarith
      nlinarith [mul_pos h1 h2, mul_nonneg hA0.le (neg_nonneg.mpr h)]
    · linarith
  · intro h
    by_cases h0 : hA v * t + hB s v ≤ 0
    · right; exact h0
    · left
      push Not at h0
      have h3 : (hA v * t + hB s v) ^ 2 ≤ discD p s v := by
        nlinarith [mul_nonneg (show 0 ≤ Real.sqrt (discD p s v) - (hA v * t + hB s v) by
            linarith) (show 0 ≤ Real.sqrt (discD p s v) + (hA v * t + hB s v) by linarith)]
      by_contra hq
      push Not at hq
      nlinarith [mul_pos hA0 hq]

/-- SEM-2 in closed form: when the horizontal miss distance is at most DTHR, the horizontal
violation set along the trajectory is `[rIn, tOut]`. -/
theorem horizontal_along_iff_roots (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) (hT : 0 ≤ p.tthr)
    (hA0 : 0 < hA v) (hm : HmdTest p s v) :
    Horizontal p (along s v t) v ↔ rIn p s v ≤ t ∧ t ≤ tOut p s v := by
  have hd : 0 ≤ discD p s v := by
    rw [discD_eq]; unfold HmdTest at hm; linarith
  have hd' : 0 ≤ discTau p s v := by
    rw [discTau_eq]; nlinarith [sq_nonneg (p.tthr * hA v / 2)]
  rw [horizontal_along_iff p s v t hT hA0, rTest_iff p s v t hA0 hd', xTest_iff p s v t hA0 hd]
  exact ⟨fun h => h.2, fun h => ⟨hm, h⟩⟩

/-- SEM-5 in closed form: for a relative motion that is neither level nor horizontally
stationary, and a miss distance of at most DTHR, the violation times within `[B, T]` form the
interval from `max B (max vLo rIn)` to `min T (min vHi tOut)`. -/
theorem violations_eq_Icc (p : Table ℝ) (s v : Vec3 ℝ) (hp : p.Valid) (hA0 : 0 < hA v)
    (hm : HmdTest p s v) (hz : v.z ≠ 0) (B T : ℝ) :
    {t | B ≤ t ∧ t ≤ T ∧ WCVAt p s v t} =
      Set.Icc (max B (max (vLo p s v) (rIn p s v))) (min T (min (vHi p s v) (tOut p s v))) := by
  obtain ⟨-, hZ, hT, -⟩ := hp
  ext t
  simp only [Set.mem_ofPred_eq, Set.mem_Icc, WCVAt, WCV, max_le_iff, le_min_iff]
  rw [horizontal_along_iff_roots p s v t hT hA0 hm, vertical_along_iff p s v t hZ hz]
  tauto

/-- The sign-dependent quantity `q = -(hb + sign(hb) sd)` of the stable root formula. -/
def stableQ (hb sd : ℝ) : ℝ := -(hb + if 0 ≤ hb then sd else -sd)

/-- The roots of `a t² + 2 hb t + c`, given `sd = √(hb² - a c)`, as computed by `roots` in
`rust/src/lib.rs`: `q / a` and `c / q` in increasing order, or `-hb / a` twice if `q = 0`. -/
def stableRoots (a hb c sd : ℝ) : ℝ × ℝ :=
  if stableQ hb sd = 0 then (-hb / a, -hb / a)
  else if stableQ hb sd / a ≤ c / stableQ hb sd then (stableQ hb sd / a, c / stableQ hb sd)
  else (c / stableQ hb sd, stableQ hb sd / a)

/-- The stable root formula computes the textbook roots `(-hb ∓ √(hb² - a c)) / a`. -/
theorem stableRoots_eq {a hb c : ℝ} (ha : 0 < a) (hd : 0 ≤ hb ^ 2 - a * c) :
    stableRoots a hb c (Real.sqrt (hb ^ 2 - a * c)) =
      ((-hb - Real.sqrt (hb ^ 2 - a * c)) / a, (-hb + Real.sqrt (hb ^ 2 - a * c)) / a) := by
  have hsq : Real.sqrt (hb ^ 2 - a * c) ^ 2 = hb ^ 2 - a * c := Real.sq_sqrt hd
  have hs : 0 ≤ Real.sqrt (hb ^ 2 - a * c) := Real.sqrt_nonneg _
  set r := Real.sqrt (hb ^ 2 - a * c) with hr
  have vieta : (-hb - r) * (-hb + r) = a * c := by
    nlinarith
  have ha'' : a ≠ 0 := ha.ne'
  have hdiv : ∀ x y : ℝ, x ≤ y → x / a ≤ y / a := fun x y h =>
    (div_le_iff_pos_den ha).mpr (by rw [div_mul_self_cancel _ ha.ne']; exact h)
  unfold stableRoots
  by_cases hb0 : 0 ≤ hb
  · have hq : stableQ hb r = -(hb + r) := by
      unfold stableQ; rw [ite_eq_left hb0]
    rw [hq]
    by_cases h0 : -(hb + r) = 0
    · rw [ite_eq_left h0]
      have h1 : hb = 0 := by linarith
      have h2 : r = 0 := by linarith
      rw [h1, h2]
      norm_num
    · rw [ite_eq_right h0]
      have e1 : -(hb + r) / a = (-hb - r) / a := by ring
      have e2 : c / -(hb + r) = (-hb + r) / a := by
        rw [div_eq_div_iff h0 ha'']; nlinarith
      have hle : (-hb - r) / a ≤ (-hb + r) / a := hdiv _ _ (by linarith)
      rw [e1, e2, ite_eq_left hle]
  · push Not at hb0
    have hq : stableQ hb r = -(hb + -r) := by
      unfold stableQ; rw [ite_eq_right (not_le.mpr hb0)]
    rw [hq]
    have h0 : -(hb + -r) ≠ 0 := by
      intro h; linarith
    rw [ite_eq_right h0]
    have e1 : -(hb + -r) / a = (-hb + r) / a := by ring
    have e2 : c / -(hb + -r) = (-hb - r) / a := by
      rw [div_eq_div_iff h0 ha'']; nlinarith
    rw [e1, e2]
    by_cases hr0 : r = 0
    · rw [hr0]
      simp
    · have hpos : 0 < r := lt_of_le_of_ne hs (Ne.symm hr0)
      have hlt : ¬ (-hb + r) / a ≤ (-hb - r) / a := by
        intro h
        have h' := (div_le_iff_pos_den ha).mp h
        rw [div_mul_self_cancel _ ha.ne'] at h'
        linarith
      rw [ite_eq_right hlt]

/-- Applied to `qTau`, with the coefficients of `horizontal_set` in `rust/src/lib.rs`, the stable
formula gives `rIn` as its smaller root. -/
theorem stableRoots_tau (p : Table ℝ) (s v : Vec3 ℝ) (hA0 : 0 < hA v)
    (hd : 0 ≤ discTau p s v) :
    (stableRoots (hA v) (hbTau p s v) (cTau p s v) (Real.sqrt (discTau p s v))).1 = rIn p s v := by
  unfold discTau at hd
  unfold rIn discTau
  rw [stableRoots_eq hA0 hd]

/-- Applied to `qD`, with the coefficients of `horizontal_set` in `rust/src/lib.rs`, the stable
formula gives `tOut` as its larger root. -/
theorem stableRoots_circle (p : Table ℝ) (s v : Vec3 ℝ) (hA0 : 0 < hA v)
    (hd : 0 ≤ discD p s v) :
    (stableRoots (hA v) (hB s v) (hSS s - p.dthr ^ 2) (Real.sqrt (discD p s v))).2 =
      tOut p s v := by
  unfold discD at hd
  unfold tOut discD
  rw [stableRoots_eq hA0 hd]

end Wellclear
