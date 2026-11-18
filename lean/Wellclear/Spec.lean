import Wellclear.Basic

/-!
# Derived requirements

The semantic requirements derived from the well-clear detection component of DAIDALUS
(`derivation/requirements.md`), stated over the real numbers. Each definition cites the
requirement it formalizes. The formalization follows the requirement text literally, divisions
included; Lean's convention that `x / 0 = 0` gives the stated value `tcpa = 0` when `v_h = 0`.

The numerical conventions (NUM-1 to NUM-4) and the conventions of SEM-7 and SEM-8 concern
floating-point implementations and are not part of this exact semantics. The tolerance of ACC-2
appears in `Within` and `Short`.
-/

noncomputable section

namespace Wellclear

/-- ENV-1: DTHR and ZTHR are positive, and TTHR and TCOA are nonnegative. -/
def Table.Valid {K : Type*} [Field K] [LinearOrder K] (p : Table K) : Prop :=
  0 < p.dthr ∧ 0 < p.zthr ∧ 0 ≤ p.tthr ∧ 0 ≤ p.tcoa

instance {K : Type*} [Field K] [LinearOrder K] (p : Table K) : Decidable p.Valid := by
  unfold Table.Valid; infer_instance

/-- The time of closest horizontal approach, `tcpa = -(s_h · v_h) / |v_h|²` (SEM-2). -/
def tcpa (s v : Vec3 ℝ) : ℝ := -hB s v / hA v

/-- The squared horizontal miss distance `HMD² = |s_h + tcpa v_h|²` (SEM-2). -/
def hmd2 (s v : Vec3 ℝ) : ℝ := (s.x + tcpa s v * v.x) ^ 2 + (s.y + tcpa s v * v.y) ^ 2

/-- The modified tau, `(DTHR² - |s_h|²) / (s_h · v_h)` if `s_h · v_h < 0` and `-1` otherwise
(SEM-2). -/
def taumod (p : Table ℝ) (s v : Vec3 ℝ) : ℝ :=
  if hB s v < 0 then (p.dthr ^ 2 - hSS s) / hB s v else -1

/-- SEM-2: horizontal well-clear violation, `|s_h|² ≤ DTHR²`, or `HMD² ≤ DTHR²` and
`0 ≤ taumod ≤ TTHR`. -/
def Horizontal (p : Table ℝ) (s v : Vec3 ℝ) : Prop :=
  hSS s ≤ p.dthr ^ 2 ∨ (hmd2 s v ≤ p.dthr ^ 2 ∧ 0 ≤ taumod p s v ∧ taumod p s v ≤ p.tthr)

/-- The time to co-altitude, `-sz / vz` if `sz vz < 0` and `-1` otherwise (SEM-3). -/
def tcoa (sz vz : ℝ) : ℝ := if sz * vz < 0 then -sz / vz else -1

/-- SEM-3: vertical well-clear violation, `|sz| ≤ ZTHR`, or `0 ≤ tcoa ≤ TCOA`. -/
def Vertical (p : Table ℝ) (sz vz : ℝ) : Prop :=
  |sz| ≤ p.zthr ∨ (0 ≤ tcoa sz vz ∧ tcoa sz vz ≤ p.tcoa)

/-- SEM-4: well-clear violation is horizontal and vertical violation, for the relative position
`s` and velocity `v` (SEM-1). -/
def WCV (p : Table ℝ) (s v : Vec3 ℝ) : Prop := Horizontal p s v ∧ Vertical p s.z v.z

/-- Well-clear violation at time `t` along the linear projection of the encounter. -/
def WCVAt (p : Table ℝ) (s v : Vec3 ℝ) (t : ℝ) : Prop := WCV p (along s v t) v

/-- No violation at any time of `[lo, hi]`. -/
def Clear (p : Table ℝ) (s v : Vec3 ℝ) (lo hi : ℝ) : Prop :=
  ∀ t, lo ≤ t → t ≤ hi → ¬ WCVAt p s v t

/-- A violation at every time of `[lo, hi]`. -/
def Lost (p : Table ℝ) (s v : Vec3 ℝ) (lo hi : ℝ) : Prop :=
  ∀ t, lo ≤ t → t ≤ hi → WCVAt p s v t

/-- SEM-5 within the tolerance `ε` of ACC-2: a reported conflict on `[tin, tout]` within the
lookahead window `[B, T]` has no violation before `tin - ε` or after `tout + ε`, and a violation
at every time of a nonempty interval whose endpoints lie within `ε` of `tin` and `tout`. Because
the set of violation times is an interval (`violations_ordConnected`), its endpoints within the
window then lie within `ε` of the reported endpoints. -/
def Within (p : Table ℝ) (s v : Vec3 ℝ) (B T ε tin tout : ℝ) : Prop :=
  Clear p s v B (tin - ε) ∧ Clear p s v (tout + ε) T ∧
    ∃ x y, tin - ε ≤ x ∧ x ≤ tin + ε ∧ tout - ε ≤ y ∧ y ≤ tout + ε ∧ x ≤ y ∧ Lost p s v x y

/-- SEM-7 within the tolerance `ε`: every violation within `[B, T]` lies strictly within `ε` of
`h`, so a no-conflict answer suppresses at most a near-instantaneous loss of well-clear. -/
def Short (p : Table ℝ) (s v : Vec3 ℝ) (B T ε h : ℝ) : Prop :=
  Clear p s v B (h - ε) ∧ Clear p s v (h + ε) T

end Wellclear
