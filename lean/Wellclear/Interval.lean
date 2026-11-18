import Wellclear.Tests

/-!
# Structure of the violation set

Theorems about the requirements over the real numbers:

* `horizontal_along_iff` and `vertical_along_iff` restate the horizontal (SEM-2) and vertical
  (SEM-3) conditions along the trajectory as the sign tests of `Wellclear.Tests`;
* `pointTest_iff`: the sign test of a single time is equivalent to a violation (SEM-4);
* `violations_ordConnected`: the set of violation times is an interval, the structural fact behind
  SEM-5 (proved in PVS as `WCV_taumod_interval_correct`);
* `clear_of_clearTest`: the test of an interval is sound;
* `wcv_swap`: exchanging ownship and intruder does not change the violation predicate (SEM-6).

The proofs use only ring identities and linear arithmetic over products of hypotheses; there is
no square root in this file.
-/

namespace Wellclear

/-! ### Arithmetic helpers -/

theorem div_mul_self_cancel (a : ℝ) {c : ℝ} (hc : c ≠ 0) : a / c * c = a := by
  rw [div_mul_eq_mul_div, mul_div_assoc, div_self hc, mul_one]

theorem div_le_iff_pos_den {a c t : ℝ} (hc : 0 < c) : a / c ≤ t ↔ a ≤ t * c := by
  have e := div_mul_self_cancel a hc.ne'
  constructor
  · intro h; nlinarith [mul_nonneg (sub_nonneg.mpr h) hc.le]
  · intro h; by_contra h'; push Not at h'; nlinarith [mul_pos (sub_pos.mpr h') hc]

theorem le_div_iff_pos_den {a c t : ℝ} (hc : 0 < c) : t ≤ a / c ↔ t * c ≤ a := by
  have e := div_mul_self_cancel a hc.ne'
  constructor
  · intro h; nlinarith [mul_nonneg (sub_nonneg.mpr h) hc.le]
  · intro h; by_contra h'; push Not at h'; nlinarith [mul_pos (sub_pos.mpr h') hc]

theorem div_le_iff_neg_den {a c t : ℝ} (hc : c < 0) : a / c ≤ t ↔ t * c ≤ a := by
  have e := div_mul_self_cancel a hc.ne
  constructor
  · intro h; nlinarith [mul_nonneg (sub_nonneg.mpr h) (neg_nonneg.mpr hc.le)]
  · intro h; by_contra h'; push Not at h'; nlinarith [mul_pos (sub_pos.mpr h') (neg_pos.mpr hc)]

theorem le_div_iff_neg_den {a c t : ℝ} (hc : c < 0) : t ≤ a / c ↔ a ≤ t * c := by
  have e := div_mul_self_cancel a hc.ne
  constructor
  · intro h; nlinarith [mul_nonneg (sub_nonneg.mpr h) (neg_nonneg.mpr hc.le)]
  · intro h; by_contra h'; push Not at h'; nlinarith [mul_pos (sub_pos.mpr h') (neg_pos.mpr hc)]

theorem hA_nonneg (v : Vec3 ℝ) : 0 ≤ hA v :=
  add_nonneg (mul_self_nonneg v.x) (mul_self_nonneg v.y)

theorem hA_pos {v : Vec3 ℝ} (h : hA v ≠ 0) : 0 < hA v :=
  lt_of_le_of_ne (hA_nonneg v) (Ne.symm h)

theorem uAt_le (s v : Vec3 ℝ) {t t' : ℝ} (htt : t ≤ t') : uAt s v t ≤ uAt s v t' := by
  have e := uAt_sub s v t t'
  nlinarith [mul_nonneg (hA_nonneg v) (sub_nonneg.mpr htt)]

/-- `HMD² |v_h|² = (s_h × v_h)²` (Lagrange's identity). -/
theorem hmd2_mul (s v : Vec3 ℝ) (h : hA v ≠ 0) : hmd2 s v * hA v = hCross s v ^ 2 := by
  have e : tcpa s v * hA v = -hB s v := div_mul_self_cancel (-hB s v) h
  have expand : hmd2 s v * hA v =
      hSS s * hA v + 2 * hB s v * (tcpa s v * hA v) + (tcpa s v * hA v) ^ 2 := by
    simp only [hmd2, hSS, hB, hA]; ring
  rw [expand, e]
  simp only [hSS, hB, hA, hCross]; ring

/-! ### Horizontal condition (SEM-2) along the trajectory -/

/-- Without relative horizontal motion, the horizontal condition holds at every time or at none. -/
theorem horizontal_along_iff_of_hA_eq_zero (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ)
    (h : hA v = 0) : Horizontal p (along s v t) v ↔ hSS s ≤ p.dthr ^ 2 := by
  have hx : v.x = 0 := by
    have hx2 : v.x * v.x = 0 := by
      have := mul_self_nonneg v.x
      have := mul_self_nonneg v.y
      unfold hA at h
      linarith
    exact mul_self_eq_zero.mp hx2
  have hy : v.y = 0 := by
    have hy2 : v.y * v.y = 0 := by
      have := mul_self_nonneg v.x
      have := mul_self_nonneg v.y
      unfold hA at h
      linarith
    exact mul_self_eq_zero.mp hy2
  have hss : hSS (along s v t) = hSS s := by
    simp only [hSS, along, hx, hy]; ring
  have hb : hB (along s v t) v = 0 := by
    simp only [hB, along, hx, hy]; ring
  unfold Horizontal taumod
  rw [hss, hb, ite_eq_right (lt_irrefl (0 : ℝ))]
  constructor
  · rintro (h1 | ⟨-, h1, -⟩)
    · exact h1
    · norm_num at h1
  · exact Or.inl

/-- With relative horizontal motion, the horizontal condition at time `t` is equivalent to the
miss-distance test and the two root tests. -/
theorem horizontal_along_iff (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) (hT : 0 ≤ p.tthr)
    (hA0 : 0 < hA v) :
    Horizontal p (along s v t) v ↔ HmdTest p s v ∧ RTest p s v t ∧ XTest p s v t := by
  have hI := hA_mul_qD p s v t
  have hmd : hmd2 (along s v t) v * hA v = hCross s v ^ 2 := by
    rw [← hCross_along s v t]; exact hmd2_mul (along s v t) v hA0.ne'
  have hHmd : hmd2 (along s v t) v ≤ p.dthr ^ 2 ↔ HmdTest p s v := by
    unfold HmdTest
    constructor
    · intro h; nlinarith [mul_nonneg (sub_nonneg.mpr h) hA0.le]
    · intro h; by_contra h'; push Not at h'; nlinarith [mul_pos (sub_pos.mpr h') hA0]
  have hTau : (0 ≤ taumod p (along s v t) v ∧ taumod p (along s v t) v ≤ p.tthr) ↔
      (uAt s v t < 0 ∧ 0 ≤ qD p s v t ∧ qTau p s v t ≤ 0) := by
    have hnum : p.dthr ^ 2 - hSS (along s v t) = -qD p s v t := by
      rw [hSS_along p]; ring
    unfold taumod qTau
    rw [hB_along, hnum]
    by_cases hu : uAt s v t < 0
    · rw [ite_eq_left hu]
      have e : -qD p s v t / uAt s v t * uAt s v t = -qD p s v t :=
        div_mul_self_cancel _ hu.ne
      constructor
      · rintro ⟨h1, h2⟩
        refine ⟨hu, ?_, ?_⟩
        · nlinarith [mul_nonneg h1 (neg_nonneg.mpr hu.le)]
        · nlinarith [mul_nonneg (sub_nonneg.mpr h2) (neg_nonneg.mpr hu.le)]
      · rintro ⟨-, h1, h2⟩
        constructor
        · by_contra h; push Not at h; nlinarith [mul_pos_of_neg_of_neg h hu]
        · by_contra h; push Not at h; nlinarith [mul_pos (sub_pos.mpr h) (neg_pos.mpr hu)]
    · rw [ite_eq_right hu]
      constructor
      · rintro ⟨h1, -⟩; norm_num at h1
      · rintro ⟨h1, -⟩; exact absurd h1 hu
  unfold Horizontal
  rw [hSS_along p, hHmd, hTau]
  unfold RTest XTest qTau
  constructor
  · rintro (h | ⟨hm, hu, -, hQt⟩)
    · have hQ : qD p s v t ≤ 0 := by linarith
      refine ⟨?_, ?_, Or.inl hQ⟩
      · unfold HmdTest
        nlinarith [sq_nonneg (uAt s v t), mul_nonneg hA0.le (neg_nonneg.mpr hQ)]
      · by_cases h2 : 0 ≤ 2 * uAt s v t + p.tthr * hA v
        · exact Or.inr h2
        · push Not at h2
          have hTA : 0 ≤ p.tthr * hA v := mul_nonneg hT hA0.le
          have hu : uAt s v t < 0 := by linarith
          left
          nlinarith [mul_nonneg hT (neg_nonneg.mpr hu.le)]
    · exact ⟨hm, Or.inl hQt, Or.inr hu.le⟩
  · rintro ⟨hm, hR, hX⟩
    by_cases hQ : qD p s v t ≤ 0
    · left; linarith
    · right
      push Not at hQ
      unfold HmdTest at hm
      have hu : uAt s v t < 0 := by
        rcases hX with hX | hX
        · exact absurd hX (not_le.mpr hQ)
        · rcases hX.lt_or_eq with h | h
          · exact h
          · exfalso
            rw [h] at hI
            nlinarith [mul_pos hA0 hQ]
      refine ⟨hm, hu, hQ.le, ?_⟩
      rcases hR with hR | hR
      · exact hR
      · have h1 : uAt s v t * (uAt s v t + p.tthr * hA v) < 0 :=
          mul_neg_of_neg_of_pos hu (by linarith)
        have key : hA v * (qD p s v t + p.tthr * uAt s v t) < 0 := by nlinarith
        by_contra h; push Not at h
        nlinarith [mul_nonneg hA0.le h.le]

/-! ### Vertical condition (SEM-3) along the trajectory -/

theorem tcoa_mul {z vz : ℝ} (hz : vz ≠ 0) (hneg : z * vz < 0) : tcoa z vz * vz = -z := by
  unfold tcoa; rw [ite_eq_left hneg]; exact div_mul_self_cancel (-z) hz

theorem act_ge_zthr (p : Table ℝ) (v : Vec3 ℝ) : p.zthr ≤ act p v := by
  unfold act; exact le_max_left _ _

theorem act_ge_of_pos (p : Table ℝ) (v : Vec3 ℝ) (hv : 0 < v.z) : v.z * p.tcoa ≤ act p v := by
  have h : max v.z (-v.z) = v.z := max_eq_left (by linarith)
  unfold act; rw [h]; exact le_max_right _ _

theorem act_ge_of_neg (p : Table ℝ) (v : Vec3 ℝ) (hv : v.z < 0) : -v.z * p.tcoa ≤ act p v := by
  have h : max v.z (-v.z) = -v.z := max_eq_right (by linarith)
  unfold act; rw [h]; exact le_max_right _ _

theorem act_lt_of_pos (p : Table ℝ) (v : Vec3 ℝ) (hv : 0 < v.z) {w : ℝ} (h1 : p.zthr < w)
    (h2 : v.z * p.tcoa < w) : act p v < w := by
  have h : max v.z (-v.z) = v.z := max_eq_left (by linarith)
  unfold act; rw [h]; exact max_lt h1 h2

theorem act_lt_of_neg (p : Table ℝ) (v : Vec3 ℝ) (hv : v.z < 0) {w : ℝ} (h1 : p.zthr < w)
    (h2 : -v.z * p.tcoa < w) : act p v < w := by
  have h : max v.z (-v.z) = -v.z := max_eq_right (by linarith)
  unfold act; rw [h]; exact max_lt h1 h2

/-- For a climbing relative vertical speed, SEM-3 bounds the vertical separation. -/
theorem vertical_iff_of_pos (p : Table ℝ) (v : Vec3 ℝ) {z : ℝ} (hZ : 0 < p.zthr)
    (hv : 0 < v.z) : Vertical p z v.z ↔ -act p v ≤ z ∧ z ≤ p.zthr := by
  have hA1 := act_ge_zthr p v
  have hA2 := act_ge_of_pos p v hv
  unfold Vertical
  constructor
  · rintro (h | ⟨h1, h2⟩)
    · obtain ⟨h3, h4⟩ := abs_le.mp h
      exact ⟨by linarith, h4⟩
    · by_cases hneg : z * v.z < 0
      · have e := tcoa_mul hv.ne' hneg
        have hz : z < 0 := by
          by_contra h; push Not at h; nlinarith [mul_nonneg h hv.le]
        have hc : -z ≤ v.z * p.tcoa := by nlinarith [mul_nonneg (sub_nonneg.mpr h2) hv.le]
        exact ⟨by linarith, by linarith⟩
      · unfold tcoa at h1; rw [ite_eq_right hneg] at h1; norm_num at h1
  · rintro ⟨h1, h2⟩
    by_cases hz : -p.zthr ≤ z
    · exact Or.inl (abs_le.mpr ⟨hz, h2⟩)
    · right
      push Not at hz
      have hz0 : z < 0 := by linarith
      have hneg : z * v.z < 0 := mul_neg_of_neg_of_pos hz0 hv
      have e := tcoa_mul hv.ne' hneg
      have hc : -z ≤ v.z * p.tcoa := by
        by_contra h; push Not at h
        have := act_lt_of_pos p v hv (show p.zthr < -z by linarith) h
        linarith
      constructor
      · by_contra h; push Not at h; nlinarith [mul_neg_of_neg_of_pos h hv]
      · by_contra h; push Not at h; nlinarith [mul_pos (sub_pos.mpr h) hv]

/-- For a descending relative vertical speed, SEM-3 bounds the vertical separation. -/
theorem vertical_iff_of_neg (p : Table ℝ) (v : Vec3 ℝ) {z : ℝ} (hZ : 0 < p.zthr)
    (hv : v.z < 0) : Vertical p z v.z ↔ -p.zthr ≤ z ∧ z ≤ act p v := by
  have hA1 := act_ge_zthr p v
  have hA2 := act_ge_of_neg p v hv
  unfold Vertical
  constructor
  · rintro (h | ⟨h1, h2⟩)
    · obtain ⟨h3, h4⟩ := abs_le.mp h
      exact ⟨h3, by linarith⟩
    · by_cases hneg : z * v.z < 0
      · have e := tcoa_mul hv.ne hneg
        have hz : 0 < z := by
          by_contra h; push Not at h
          nlinarith [mul_nonneg (neg_nonneg.mpr h) (neg_nonneg.mpr hv.le)]
        have hc : z ≤ -v.z * p.tcoa := by
          nlinarith [mul_nonneg (sub_nonneg.mpr h2) (neg_nonneg.mpr hv.le)]
        exact ⟨by linarith, by linarith⟩
      · unfold tcoa at h1; rw [ite_eq_right hneg] at h1; norm_num at h1
  · rintro ⟨h1, h2⟩
    by_cases hz : z ≤ p.zthr
    · exact Or.inl (abs_le.mpr ⟨h1, hz⟩)
    · right
      push Not at hz
      have hz0 : 0 < z := by linarith
      have hneg : z * v.z < 0 := mul_neg_of_pos_of_neg hz0 hv
      have e := tcoa_mul hv.ne hneg
      have hc : z ≤ -v.z * p.tcoa := by
        by_contra h; push Not at h
        have := act_lt_of_neg p v hv hz h
        linarith
      constructor
      · by_contra h; push Not at h; nlinarith [mul_pos_of_neg_of_neg h hv]
      · by_contra h; push Not at h; nlinarith [mul_pos (sub_pos.mpr h) (neg_pos.mpr hv)]

/-- With relative vertical motion, the vertical condition holds exactly on `[vLo, vHi]`. -/
theorem vertical_along_iff (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) (hZ : 0 < p.zthr)
    (hz : v.z ≠ 0) : Vertical p (along s v t).z v.z ↔ vLo p s v ≤ t ∧ t ≤ vHi p s v := by
  show Vertical p (s.z + t * v.z) v.z ↔ _
  rcases hz.lt_or_gt with hneg | hpos
  · have h0 : ¬ (0 < v.z) := not_lt.mpr hneg.le
    have hlo : vLo p s v = (act p v - s.z) / v.z := by unfold vLo; rw [ite_eq_right h0]
    have hhi : vHi p s v = (-p.zthr - s.z) / v.z := by unfold vHi; rw [ite_eq_right h0]
    rw [vertical_iff_of_neg p v hZ hneg, hlo, hhi, div_le_iff_neg_den hneg,
      le_div_iff_neg_den hneg]
    constructor
    · rintro ⟨h1, h2⟩; constructor <;> linarith
    · rintro ⟨h1, h2⟩; constructor <;> linarith
  · have hlo : vLo p s v = (-act p v - s.z) / v.z := by unfold vLo; rw [ite_eq_left hpos]
    have hhi : vHi p s v = (p.zthr - s.z) / v.z := by unfold vHi; rw [ite_eq_left hpos]
    rw [vertical_iff_of_pos p v hZ hpos, hlo, hhi, div_le_iff_pos_den hpos,
      le_div_iff_pos_den hpos]
    constructor
    · rintro ⟨h1, h2⟩; constructor <;> linarith
    · rintro ⟨h1, h2⟩; constructor <;> linarith

/-- In level flight, the vertical condition holds at every time or at none. -/
theorem vertical_along_iff_of_eq_zero (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) (hz : v.z = 0) :
    Vertical p (along s v t).z v.z ↔ -p.zthr ≤ s.z ∧ s.z ≤ p.zthr := by
  show Vertical p (s.z + t * v.z) v.z ↔ _
  rw [hz, mul_zero, add_zero, ← abs_le]
  unfold Vertical tcoa
  rw [mul_zero, ite_eq_right (lt_irrefl (0 : ℝ))]
  constructor
  · rintro (h | ⟨h, -⟩)
    · exact h
    · norm_num at h
  · exact Or.inl

/-! ### Violations (SEM-4 and SEM-5) -/

theorem rTest_mono (p : Table ℝ) (s v : Vec3 ℝ) {t t' : ℝ} (hR : RTest p s v t)
    (htt : t ≤ t') : RTest p s v t' := by
  have hu := uAt_le s v htt
  unfold RTest at hR ⊢
  by_cases h2 : 0 ≤ 2 * uAt s v t' + p.tthr * hA v
  · exact Or.inr h2
  · left
    push Not at h2
    rcases hR with hR | hR
    · have e := qTau_sub p s v t t'
      nlinarith [mul_nonneg (sub_nonneg.mpr htt)
        (show 0 ≤ -(uAt s v t + uAt s v t' + p.tthr * hA v) by linarith)]
    · linarith

theorem xTest_anti (p : Table ℝ) (s v : Vec3 ℝ) {t t' : ℝ} (hX : XTest p s v t')
    (htt : t ≤ t') : XTest p s v t := by
  have hu := uAt_le s v htt
  unfold XTest at hX ⊢
  by_cases h : uAt s v t ≤ 0
  · exact Or.inr h
  · left
    push Not at h
    rcases hX with hX | hX
    · have e := qD_sub p s v t t'
      nlinarith [mul_nonneg (sub_nonneg.mpr htt) (show 0 ≤ uAt s v t + uAt s v t' by linarith)]
    · linarith

/-- The test of a single time is equivalent to a violation at that time. -/
theorem pointTest_iff (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) (hp : p.Valid) :
    PointTest p s v t ↔ WCVAt p s v t := by
  obtain ⟨-, hZ, hT, -⟩ := hp
  unfold PointTest WCVAt WCV
  apply and_congr
  · by_cases h : hA v = 0
    · rw [horizontal_along_iff_of_hA_eq_zero p s v t h]
      simp [h]
    · rw [horizontal_along_iff p s v t hT (hA_pos h)]
      simp [h]
  · by_cases h : v.z = 0
    · rw [vertical_along_iff_of_eq_zero p s v t h]
      simp [h]
    · rw [vertical_along_iff p s v t hZ h]
      simp [h]

/-- Between two violation times, every time is a violation time. -/
theorem wcvAt_convex (p : Table ℝ) (s v : Vec3 ℝ) (hp : p.Valid) {t₁ t₂ t : ℝ}
    (h₁ : WCVAt p s v t₁) (h₂ : WCVAt p s v t₂) (ht₁ : t₁ ≤ t) (ht₂ : t ≤ t₂) :
    WCVAt p s v t := by
  obtain ⟨hh₁, hv₁⟩ := (pointTest_iff p s v t₁ hp).mpr h₁
  obtain ⟨hh₂, hv₂⟩ := (pointTest_iff p s v t₂ hp).mpr h₂
  apply (pointTest_iff p s v t hp).mp
  refine ⟨?_, ?_⟩
  · rcases hh₁ with ⟨ha, hs⟩ | ⟨ha, hm, hR, -⟩
    · exact Or.inl ⟨ha, hs⟩
    · rcases hh₂ with ⟨ha', -⟩ | ⟨-, -, -, hX⟩
      · exact absurd ha' ha
      · exact Or.inr ⟨ha, hm, rTest_mono p s v hR ht₁, xTest_anti p s v hX ht₂⟩
  · rcases hv₁ with ⟨hz, hs⟩ | ⟨hz, hlo, -⟩
    · exact Or.inl ⟨hz, hs⟩
    · rcases hv₂ with ⟨hz', -⟩ | ⟨-, -, hhi⟩
      · exact absurd hz' hz
      · exact Or.inr ⟨hz, le_trans hlo ht₁, le_trans ht₂ hhi⟩

/-- SEM-5: the set of violation times is an interval (order-connected). -/
theorem violations_ordConnected (p : Table ℝ) (s v : Vec3 ℝ) (hp : p.Valid) :
    Set.OrdConnected {t | WCVAt p s v t} := by
  constructor
  intro x hx y hy t ht
  exact wcvAt_convex p s v hp hx hy ht.1 ht.2

theorem lost_of_endpoints (p : Table ℝ) (s v : Vec3 ℝ) (hp : p.Valid) {x y : ℝ}
    (hx : WCVAt p s v x) (hy : WCVAt p s v y) : Lost p s v x y := by
  intro t h₁ h₂
  exact wcvAt_convex p s v hp hx hy h₁ h₂

/-- The test of an interval is sound: if it succeeds, there is no violation in the interval. -/
theorem clear_of_clearTest (p : Table ℝ) (s v : Vec3 ℝ) (lo hi : ℝ) (hp : p.Valid)
    (h : ClearTest p s v lo hi) : Clear p s v lo hi := by
  intro t hlo hhi hw
  obtain ⟨hh, hv⟩ := (pointTest_iff p s v t hp).mpr hw
  have hL : winLo p s v lo ≤ t := by
    unfold winLo
    by_cases hz : v.z = 0
    · rw [ite_eq_left hz]; exact hlo
    · rw [ite_eq_right hz]
      rcases hv with ⟨h1, -⟩ | ⟨-, h2, -⟩
      · exact absurd h1 hz
      · exact max_le hlo h2
  have hU : t ≤ winHi p s v hi := by
    unfold winHi
    by_cases hz : v.z = 0
    · rw [ite_eq_left hz]; exact hhi
    · rw [ite_eq_right hz]
      rcases hv with ⟨h1, -⟩ | ⟨-, -, h3⟩
      · exact absurd h1 hz
      · exact le_min hhi h3
  unfold ClearTest at h
  rcases h with h | ⟨hz, hz'⟩ | h | ⟨ha, ha'⟩ | ⟨ha, h⟩
  · linarith
  · rcases hv with ⟨-, h2, h3⟩ | ⟨h1, -⟩
    · rcases hz' with h | h <;> linarith
    · exact h1 hz
  · linarith
  · rcases hh with ⟨-, h2⟩ | ⟨h1, -⟩
    · linarith
    · exact h1 ha
  · rcases hh with ⟨h1, -⟩ | ⟨-, hm, hR, hX⟩
    · exact ha h1
    · exact h ⟨hm, rTest_mono p s v hR hU, xTest_anti p s v hX hL⟩

/-! ### Symmetry (SEM-6) -/

theorem tcpa_neg (s v : Vec3 ℝ) : tcpa s.neg v.neg = tcpa s v := by
  unfold tcpa; rw [hA_neg, hB_neg]

theorem hmd2_neg (s v : Vec3 ℝ) : hmd2 s.neg v.neg = hmd2 s v := by
  unfold hmd2; rw [tcpa_neg]; simp only [Vec3.neg]; ring

theorem taumod_neg (p : Table ℝ) (s v : Vec3 ℝ) : taumod p s.neg v.neg = taumod p s v := by
  unfold taumod; rw [hB_neg, hSS_neg]

theorem horizontal_neg (p : Table ℝ) (s v : Vec3 ℝ) :
    Horizontal p s.neg v.neg ↔ Horizontal p s v := by
  unfold Horizontal; rw [hSS_neg, hmd2_neg, taumod_neg]

theorem tcoa_neg (z vz : ℝ) : tcoa (-z) (-vz) = tcoa z vz := by
  unfold tcoa
  rw [neg_mul_neg]
  split_ifs <;> ring

theorem vertical_neg (p : Table ℝ) (z vz : ℝ) : Vertical p (-z) (-vz) ↔ Vertical p z vz := by
  unfold Vertical; rw [abs_neg, tcoa_neg]

theorem wcv_neg (p : Table ℝ) (s v : Vec3 ℝ) : WCV p s.neg v.neg ↔ WCV p s v := by
  show (Horizontal p s.neg v.neg ∧ Vertical p (-s.z) (-v.z)) ↔
    (Horizontal p s v ∧ Vertical p s.z v.z)
  rw [horizontal_neg, vertical_neg]

/-- SEM-6: exchanging ownship and intruder does not change the violation predicate. -/
theorem wcv_swap (p : Table ℝ) (so vo si vi : Vec3 ℝ) :
    WCV p (rel si so) (rel vi vo) ↔ WCV p (rel so si) (rel vo vi) := by
  rw [rel_swap so si, rel_swap vo vi]
  exact wcv_neg p _ _

end Wellclear
