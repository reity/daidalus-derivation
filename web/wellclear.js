/**
 * DO-365 well-clear violation detection, regenerated from requirements derived
 * from NASA DAIDALUS. This is a JavaScript port of rust/src/lib.rs: it performs
 * the same IEEE 754 operations in the same order, and it is graded on the same
 * corpus of test vectors as the other implementations. The interactive page
 * embeds this file, so its explorer runs the graded code. Requirement
 * identifiers refer to derivation/requirements.md.
 */
const wellclear = (() => {
  "use strict";

  /** Snap threshold of the DAIDALUS almost_equals(x, 0) comparison (NUM-1, NUM-2). */
  const SNAP = 1e-13;
  /** Tolerance (in units in the last place) of the default almost_equals (SEM-7). */
  const ULPS = 16348n;
  /** Largest accepted magnitude of a position, threshold, or lookahead bound (IMP-1). */
  const MAX_POS = 1e9;
  /** Largest accepted magnitude of a velocity component (IMP-1). */
  const MAX_VEL = 1e6;
  const MIN_INT64 = -(2n ** 63n);
  const float = new Float64Array(1);
  const integer = new BigInt64Array(float.buffer);

  /** Position of a value in the lexicographic ordering of IEEE 754 bit patterns. */
  const key = (x) => {
    float[0] = x;
    const i = integer[0];
    return i < 0n ? BigInt.asIntN(64, MIN_INT64 - i) : i;
  };

  /**
   * Whether two values are equal, or one of them is zero and both are within
   * 1e-13 of zero, or they are within 16348 units in the last place of each
   * other (SEM-7, NUM-1).
   */
  const almostEquals = (a, b) => {
    if (a === b) return true;
    if ((a === 0 || b === 0) && Math.abs(a) < SNAP && Math.abs(b) < SNAP) return true;
    if (!(a < b || b < a) || !Number.isFinite(a) || !Number.isFinite(b)) return false;
    let d = BigInt.asIntN(64, key(a) - key(b));
    if (d < 0n) d = BigInt.asIntN(64, -d);
    return d <= ULPS;
  };

  const almostLess = (a, b) => !almostEquals(a, b) && a < b;

  /** Validated thresholds (ENV-1); throws BadThreshold or NonFiniteInput. */
  const thresholds = (dthr, zthr, tthr, tcoa) => {
    const values = [dthr, zthr, tthr, tcoa];
    if (!values.every(Number.isFinite)) throw new Error("NonFiniteInput");
    if (!(dthr > 0 && zthr > 0 && tthr >= 0 && tcoa >= 0) || values.some((x) => x > MAX_POS)) {
      throw new Error("BadThreshold");
    }
    return { dthr, zthr, tthr, tcoa };
  };

  const checkEncounter = (e) => {
    const positions = [e.so, e.si];
    const velocities = [e.vo, e.vi];
    if (!positions.concat(velocities).every((v) => v.every(Number.isFinite))) {
      throw new Error("NonFiniteInput");
    }
    if (
      !positions.every((v) => v.every((x) => Math.abs(x) <= MAX_POS)) ||
      !velocities.every((v) => v.every((x) => Math.abs(x) <= MAX_VEL))
    ) {
      throw new Error("OutOfRange");
    }
  };

  /** Roots of a t^2 + 2 hb t + c = 0 in stable form, smaller root first. */
  const roots = (a, hb, c, sqrtDisc) => {
    const q = -(hb + (hb >= 0 ? sqrtDisc : -sqrtDisc));
    if (q === 0) {
      const r = -hb / a;
      return [r, r];
    }
    const r1 = q / a;
    const r2 = c / q;
    return r1 <= r2 ? [r1, r2] : [r2, r1];
  };

  /** Times at which the vertical condition holds (SEM-3, NUM-1). */
  const verticalSet = (sz, vz, th) => {
    if (Math.abs(vz) < SNAP) return Math.abs(sz) <= th.zthr ? [-Infinity, Infinity] : null;
    const act = Math.max(th.zthr, Math.abs(vz) * th.tcoa);
    return vz > 0
      ? [(-act - sz) / vz, (th.zthr - sz) / vz]
      : [(act - sz) / vz, (-th.zthr - sz) / vz];
  };

  /** Times at which the horizontal condition holds (SEM-2, NUM-2 to NUM-4). */
  const horizontalSet = (sx, sy, vx, vy, tv, th) => {
    const d2 = th.dthr * th.dthr;
    const a = vx * vx + vy * vy;
    if (a < SNAP) {
      const x = sx + tv * vx;
      const y = sy + tv * vy;
      if (x * x + y * y <= d2) return [-Infinity, Infinity];
      if (a === 0) return null;
    }
    const ss = sx * sx + sy * sy;
    const inside = ss <= d2;
    const cross = sx * vy - sy * vx;
    let discC = d2 * a - cross * cross;
    if (!inside && discC < 0) return null;
    discC = Math.max(discC, 0);
    const sv = sx * vx + sy * vy;
    const t2 = roots(a, sv, ss - d2, Math.sqrt(discC))[1];
    const halfTa = 0.5 * th.tthr * a;
    const r1 = roots(a, sv + halfTa, ss + th.tthr * sv - d2, Math.sqrt(discC + halfTa * halfTa))[0];
    return inside ? [Math.min(r1, 0), Math.max(t2, 0)] : [r1, t2];
  };

  /** The empty detection result (IF-1). */
  const EMPTY = Object.freeze({ t_in: Infinity, t_out: -Infinity });

  /** Whether a detection result is a conflict (SEM-7). */
  const conflictOf = (d) => almostLess(d.t_in, d.t_out);

  const detectUnchecked = (th, e, b, t) => {
    const s = [e.so[0] - e.si[0], e.so[1] - e.si[1], e.so[2] - e.si[2]]; // SEM-1
    const v = [e.vo[0] - e.vi[0], e.vo[1] - e.vi[1], e.vo[2] - e.vi[2]];
    const vertical = verticalSet(s[2], v[2], th);
    if (!vertical) return EMPTY;
    const tv = Math.max(b, vertical[0]);
    const horizontal = horizontalSet(s[0], s[1], v[0], v[1], tv, th);
    if (!horizontal) return EMPTY;
    const d = { t_in: Math.max(tv, horizontal[0]), t_out: Math.min(t, vertical[1], horizontal[1]) };
    return conflictOf(d) ? d : EMPTY;
  };

  /** Detection interval within the lookahead window [b, t] (SEM-5, ENV-2). */
  const detect = (th, e, b, t) => {
    checkEncounter(e);
    if (!(Number.isFinite(b) && Number.isFinite(t))) throw new Error("NonFiniteInput");
    if (!(0 <= b && b < t && t <= MAX_POS)) throw new Error("BadLookahead");
    return detectUnchecked(th, e, b, t);
  };

  /** Whether the encounter is currently a violation (SEM-8). */
  const violation = (th, e) => {
    checkEncounter(e);
    const d = detectUnchecked(th, e, 0, 1);
    return conflictOf(d) && almostEquals(d.t_in, 0);
  };

  /** Whether there is a conflict within the lookahead window [b, t] (ENV-2). */
  const conflict = (th, e, b, t) => {
    checkEncounter(e);
    if (!(Number.isFinite(b) && Number.isFinite(t))) throw new Error("NonFiniteInput");
    if (!(0 <= b && b <= MAX_POS && t <= MAX_POS)) throw new Error("BadLookahead");
    if (almostEquals(b, t)) {
      const d = detectUnchecked(th, e, b, b + 1);
      return conflictOf(d) && almostEquals(d.t_in, b);
    }
    if (b > t) return false;
    return conflictOf(detectUnchecked(th, e, b, t));
  };

  /**
   * Relative geometry of an encounter for drawing: relative position and
   * velocity, time of closest approach, horizontal miss distance, and the
   * horizontal and vertical violation sets. Not part of the graded interface.
   */
  const geometry = (th, e) => {
    const s = [e.so[0] - e.si[0], e.so[1] - e.si[1], e.so[2] - e.si[2]];
    const v = [e.vo[0] - e.vi[0], e.vo[1] - e.vi[1], e.vo[2] - e.vi[2]];
    const a = v[0] * v[0] + v[1] * v[1];
    const tcpa = a > 0 ? -(s[0] * v[0] + s[1] * v[1]) / a : 0;
    const hmd = a > 0 ? Math.abs(s[0] * v[1] - s[1] * v[0]) / Math.sqrt(a) : Math.hypot(s[0], s[1]);
    const vertical = verticalSet(s[2], v[2], th);
    const horizontal = horizontalSet(s[0], s[1], v[0], v[1], vertical ? Math.max(0, vertical[0]) : 0, th);
    return { s, v, tcpa, hmd, H: horizontal, V: vertical };
  };

  return Object.freeze({
    thresholds, detect, violation, conflict, conflictOf, almostEquals, geometry, EMPTY
  });
})();

if (typeof module !== "undefined") {
  module.exports = wellclear;
}
