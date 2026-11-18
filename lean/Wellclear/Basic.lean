import Mathlib

/-!
# Encounter geometry

Relative position and velocity vectors, threshold tables, and the polynomial quantities in which
the derived requirements are stated (`Wellclear.Spec`) and decided (`Wellclear.Tests`).

Every definition in this file is made over an arbitrary field, so that the same definitions are
used over the real numbers (in the requirements and the proofs) and over the rational numbers (by
the executable checker in `Wellclear.Check`). The identities at the end of the file are the only
algebra that the proofs need.
-/

namespace Wellclear

/-- A vector in a local Euclidean frame: east, north, and up components (m, or m/s). -/
structure Vec3 (K : Type*) where
  /-- East component. -/
  x : K
  /-- North component. -/
  y : K
  /-- Vertical component. -/
  z : K

/-- A table of well-clear thresholds: DTHR and ZTHR (m), and TTHR and TCOA (s). -/
structure Table (K : Type*) where
  /-- Horizontal distance threshold DTHR. -/
  dthr : K
  /-- Vertical distance threshold ZTHR. -/
  zthr : K
  /-- Modified tau threshold TTHR. -/
  tthr : K
  /-- Time to co-altitude threshold TCOA. -/
  tcoa : K

section Field

variable {K : Type*} [Field K]

/-- The relative vector `a - b`. Only relative positions and velocities enter the requirements
(SEM-1). -/
def rel (a b : Vec3 K) : Vec3 K := ⟨a.x - b.x, a.y - b.y, a.z - b.z⟩

/-- The sum of two vectors. -/
def Vec3.add (a b : Vec3 K) : Vec3 K := ⟨a.x + b.x, a.y + b.y, a.z + b.z⟩

/-- The opposite vector. -/
def Vec3.neg (a : Vec3 K) : Vec3 K := ⟨-a.x, -a.y, -a.z⟩

/-- The relative position `s + t v` at time `t` along the linear projection. -/
def along (s v : Vec3 K) (t : K) : Vec3 K := ⟨s.x + t * v.x, s.y + t * v.y, s.z + t * v.z⟩

/-- The squared relative horizontal speed `|v_h|²`. -/
def hA (v : Vec3 K) : K := v.x * v.x + v.y * v.y

/-- The horizontal dot product `s_h · v_h`. -/
def hB (s v : Vec3 K) : K := s.x * v.x + s.y * v.y

/-- The squared horizontal separation `|s_h|²`. -/
def hSS (s : Vec3 K) : K := s.x * s.x + s.y * s.y

/-- The horizontal cross product `s_h × v_h`. By Lagrange's identity, `hCross² / hA` is the
squared horizontal miss distance. -/
def hCross (s v : Vec3 K) : K := s.x * v.y - s.y * v.x

/-- The horizontal dot product `s_h(t) · v_h` at time `t`. -/
def uAt (s v : Vec3 K) (t : K) : K := hB s v + hA v * t

/-- The squared horizontal separation at time `t` minus `DTHR²`, which is nonpositive exactly
when the aircraft are horizontally within DTHR at time `t`. -/
def qD (p : Table K) (s v : Vec3 K) (t : K) : K :=
  hA v * t * t + 2 * hB s v * t + hSS s - p.dthr ^ 2

/-- The quadratic `qD + TTHR uAt`, which is nonpositive where a converging modified tau is at most
TTHR. -/
def qTau (p : Table K) (s v : Vec3 K) (t : K) : K := qD p s v t + p.tthr * uAt s v t

/-- SEM-1: translating both aircraft by the same vector does not change the relative state. -/
theorem rel_add (a b d : Vec3 K) : rel (a.add d) (b.add d) = rel a b := by
  simp only [rel, Vec3.add, Vec3.mk.injEq]
  refine ⟨?_, ?_, ?_⟩ <;> ring

/-- Exchanging ownship and intruder negates the relative state. -/
theorem rel_swap (a b : Vec3 K) : rel b a = (rel a b).neg := by
  simp only [rel, Vec3.neg, Vec3.mk.injEq]
  refine ⟨?_, ?_, ?_⟩ <;> ring

theorem hA_neg (v : Vec3 K) : hA v.neg = hA v := by
  simp only [hA, Vec3.neg]; ring

theorem hB_neg (s v : Vec3 K) : hB s.neg v.neg = hB s v := by
  simp only [hB, Vec3.neg]; ring

theorem hSS_neg (s : Vec3 K) : hSS s.neg = hSS s := by
  simp only [hSS, Vec3.neg]; ring

theorem hSS_along (p : Table K) (s v : Vec3 K) (t : K) :
    hSS (along s v t) = qD p s v t + p.dthr ^ 2 := by
  simp only [hSS, along, qD, hA, hB]; ring

theorem hB_along (s v : Vec3 K) (t : K) : hB (along s v t) v = uAt s v t := by
  simp only [hB, along, uAt, hA]; ring

theorem hCross_along (s v : Vec3 K) (t : K) : hCross (along s v t) v = hCross s v := by
  simp only [hCross, along]; ring

/-- `hA qD = uAt² + hCross² - DTHR² hA`: the circle quadratic in terms of the miss distance. -/
theorem hA_mul_qD (p : Table K) (s v : Vec3 K) (t : K) :
    hA v * qD p s v t = uAt s v t ^ 2 + hCross s v ^ 2 - p.dthr ^ 2 * hA v := by
  simp only [hA, qD, uAt, hB, hSS, hCross]; ring

theorem uAt_sub (s v : Vec3 K) (t t' : K) : uAt s v t' - uAt s v t = hA v * (t' - t) := by
  simp only [uAt]; ring

theorem qD_sub (p : Table K) (s v : Vec3 K) (t t' : K) :
    qD p s v t - qD p s v t' = (t - t') * (uAt s v t + uAt s v t') := by
  simp only [qD, uAt]; ring

theorem qTau_sub (p : Table K) (s v : Vec3 K) (t t' : K) :
    qTau p s v t' - qTau p s v t = (t' - t) * (uAt s v t + uAt s v t' + p.tthr * hA v) := by
  simp only [qTau, qD, uAt]; ring

end Field

end Wellclear
