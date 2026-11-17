//! DO-365 well-clear violation detection (modified tau horizontally, time to
//! co-altitude vertically), regenerated from requirements derived from the
//! `WCV_TAUMOD` component of [NASA DAIDALUS](https://github.com/nasa/daidalus).
//!
//! The implementation is written from the derived requirements in
//! `derivation/requirements.md` rather than translated from the Java code, and
//! requirement identifiers are cited inline. The algorithm differs from the
//! DAIDALUS algorithm: the horizontal violation set is computed in closed form
//! over the whole time line as `[r1, t2]` (the first time at which the modified
//! tau is at most TTHR and the exit time from the DTHR circle), which is then
//! intersected with the vertical violation set and the lookahead window. The
//! quadratic roots are computed in a numerically stable form.
//!
//! The example below detects the loss of well-clear in a head-on encounter
//! (closing at 400 meters per second from 20 kilometers at the same altitude)
//! against the DO-365 DWC Phase I thresholds:
//!
//! ```
//! use wellclear::{detect, violation, Encounter, Thresholds, Vec3};
//!
//! let thresholds = Thresholds::do365_dwc_phase_i();
//! let encounter = Encounter {
//!     so: Vec3::new(0.0, 0.0, 3000.0),
//!     vo: Vec3::new(200.0, 0.0, 0.0),
//!     si: Vec3::new(20000.0, 0.0, 3000.0),
//!     vi: Vec3::new(-200.0, 0.0, 0.0),
//! };
//! let detection = detect(&thresholds, &encounter, 0.0, 180.0).unwrap();
//! assert!(detection.conflict());
//! assert!((detection.t_in - 14.735).abs() < 1e-3);
//! assert!((detection.t_out - 53.056).abs() < 1e-3);
//! assert!(!violation(&thresholds, &encounter).unwrap());
//! ```
//!
//! Invalid inputs are rejected with an explicit error (IMP-1):
//!
//! ```
//! use wellclear::{Error, Thresholds};
//!
//! assert_eq!(Thresholds::new(-1222.32, 137.16, 35.0, 0.0), Err(Error::BadThreshold));
//! assert_eq!(Thresholds::new(f64::NAN, 137.16, 35.0, 0.0), Err(Error::NonFiniteInput));
//! ```
#![forbid(unsafe_code)]
#![warn(missing_docs)]

use std::fmt;

/// Snap threshold of the DAIDALUS `Util.almost_equals(x, 0)` comparison (NUM-1, NUM-2).
const SNAP: f64 = 1e-13;

/// Tolerance (in units in the last place) of the default DAIDALUS `almost_equals` (SEM-7).
const ULPS: i64 = 16348;

/// Largest accepted magnitude of a position (m), threshold, or lookahead bound (s), which keeps
/// every intermediate product finite and meaningful (IMP-1).
const MAX_POS: f64 = 1e9;

/// Largest accepted magnitude of a velocity component (m/s) (IMP-1).
const MAX_VEL: f64 = 1e6;

/// A vector in a local Euclidean frame (meters, or meters per second).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Vec3 {
    /// East component.
    pub x: f64,
    /// North component.
    pub y: f64,
    /// Vertical component.
    pub z: f64,
}

impl Vec3 {
    /// Create a vector from its components.
    pub const fn new(x: f64, y: f64, z: f64) -> Self {
        Vec3 { x, y, z }
    }

    fn sub(self, o: Vec3) -> Vec3 {
        Vec3::new(self.x - o.x, self.y - o.y, self.z - o.z)
    }

    fn all(self, f: impl Fn(f64) -> bool) -> bool {
        f(self.x) && f(self.y) && f(self.z)
    }
}

/// Reason for which an input is rejected (IMP-1). The original component
/// sanitizes such inputs or silently computes a result instead.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error {
    /// A position, velocity, threshold, or lookahead bound is NaN or infinite (ENV-4).
    NonFiniteInput,
    /// A position or velocity component exceeds the numeric validity range.
    OutOfRange,
    /// A threshold is outside its domain (ENV-1) or exceeds the numeric validity range.
    BadThreshold,
    /// The lookahead window is malformed (ENV-2) or exceeds the numeric validity range.
    BadLookahead,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            Error::NonFiniteInput => "input is not finite",
            Error::OutOfRange => "position or velocity is outside the numeric validity range",
            Error::BadThreshold => "threshold is outside its domain",
            Error::BadLookahead => "lookahead window is malformed",
        };
        f.write_str(message)
    }
}

impl std::error::Error for Error {}

/// Validated well-clear thresholds (ENV-1): DTHR and ZTHR are positive, TTHR
/// and TCOA are nonnegative, and all are finite.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Thresholds {
    dthr: f64,
    zthr: f64,
    tthr: f64,
    tcoa: f64,
}

impl Thresholds {
    /// Create a validated threshold table from DTHR and ZTHR (in meters) and
    /// TTHR and TCOA (in seconds).
    pub fn new(dthr: f64, zthr: f64, tthr: f64, tcoa: f64) -> Result<Self, Error> {
        let v = [dthr, zthr, tthr, tcoa];
        if !v.iter().all(|x| x.is_finite()) {
            return Err(Error::NonFiniteInput);
        }
        if !(dthr > 0.0 && zthr > 0.0 && tthr >= 0.0 && tcoa >= 0.0)
            || v.iter().any(|x| *x > MAX_POS)
        {
            return Err(Error::BadThreshold);
        }
        Ok(Thresholds {
            dthr,
            zthr,
            tthr,
            tcoa,
        })
    }

    /// The DO-365 DWC Phase I table (the DAIDALUS default, ENV-3): DTHR of
    /// 0.66 nautical miles, ZTHR of 450 feet, TTHR of 35 seconds, and TCOA of
    /// 0 seconds.
    pub fn do365_dwc_phase_i() -> Self {
        Thresholds {
            dthr: 0.66 * 1852.0,
            zthr: 450.0 * 0.3048,
            tthr: 35.0,
            tcoa: 0.0,
        }
    }
}

/// Ownship and intruder positions and velocities (IF-1).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Encounter {
    /// Ownship position (m).
    pub so: Vec3,
    /// Ownship velocity (m/s).
    pub vo: Vec3,
    /// Intruder position (m).
    pub si: Vec3,
    /// Intruder velocity (m/s).
    pub vi: Vec3,
}

/// Detection interval within the lookahead window (IF-1). The empty result is
/// encoded as `(+inf, -inf)`, as in the original component.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Detection {
    /// Time (s) at which the loss of well-clear begins.
    pub t_in: f64,
    /// Time (s) at which the loss of well-clear ends.
    pub t_out: f64,
}

impl Detection {
    /// The empty detection result.
    pub const EMPTY: Detection = Detection {
        t_in: f64::INFINITY,
        t_out: f64::NEG_INFINITY,
    };

    /// Whether the result is a conflict, which requires a violation set that
    /// is longer than the almost-equal tolerance (SEM-7).
    pub fn conflict(&self) -> bool {
        almost_less(self.t_in, self.t_out)
    }
}

/// Whether two values are almost equal (SEM-7, NUM-1): they are equal, or one
/// of them is zero and both are within `1e-13` of zero, or they are within 16348
/// units in the last place of each other.
///
/// ```
/// use wellclear::almost_equals;
///
/// assert!(almost_equals(1.0, 1.0 + 1e-12));
/// assert!(almost_equals(0.0, 5e-14));
/// assert!(!almost_equals(1.0, 1.0 + 1e-11));
/// ```
pub fn almost_equals(a: f64, b: f64) -> bool {
    if a == b {
        return true;
    }
    if (a == 0.0 || b == 0.0) && a.abs() < SNAP && b.abs() < SNAP {
        return true;
    }
    if !(a < b || b < a) || a.is_infinite() || b.is_infinite() {
        return false;
    }
    // Lexicographic ordering of IEEE 754 bit patterns as two's complement integers.
    let key = |x: f64| {
        let i = x.to_bits() as i64;
        if i < 0 {
            i64::MIN.wrapping_sub(i)
        } else {
            i
        }
    };
    key(a).wrapping_sub(key(b)).wrapping_abs() <= ULPS
}

/// Whether `a` is less than `b` and the two values are not almost equal.
pub fn almost_less(a: f64, b: f64) -> bool {
    !almost_equals(a, b) && a < b
}

fn check_encounter(e: &Encounter) -> Result<(), Error> {
    let pos = [e.so, e.si];
    let vel = [e.vo, e.vi];
    if !pos.iter().chain(vel.iter()).all(|v| v.all(f64::is_finite)) {
        return Err(Error::NonFiniteInput);
    }
    if !pos.iter().all(|v| v.all(|x| x.abs() <= MAX_POS))
        || !vel.iter().all(|v| v.all(|x| x.abs() <= MAX_VEL))
    {
        return Err(Error::OutOfRange);
    }
    Ok(())
}

/// Roots of `a t^2 + 2 hb t + c = 0` given `sqrt_disc = sqrt(hb^2 - a c)` and
/// `a > 0`, computed in a stable form (without subtracting nearly equal
/// quantities). Returns the smaller root and then the larger root.
fn roots(a: f64, hb: f64, c: f64, sqrt_disc: f64) -> (f64, f64) {
    let q = -(hb + if hb >= 0.0 { sqrt_disc } else { -sqrt_disc });
    if q == 0.0 {
        let r = -hb / a;
        return (r, r);
    }
    let (r1, r2) = (q / a, c / q);
    if r1 <= r2 {
        (r1, r2)
    } else {
        (r2, r1)
    }
}

/// Times (over the whole real line) at which the vertical condition holds
/// (SEM-3, NUM-1).
fn vertical_set(sz: f64, vz: f64, th: &Thresholds) -> Option<(f64, f64)> {
    if vz.abs() < SNAP {
        // Level flight (NUM-1).
        return if sz.abs() <= th.zthr {
            Some((f64::NEG_INFINITY, f64::INFINITY))
        } else {
            None
        };
    }
    // The converging side extends to |vz| * TCOA (SEM-3), so the vertical separation must lie
    // within [-ZTHR, act] or [-act, ZTHR].
    let act = th.zthr.max(vz.abs() * th.tcoa);
    if vz > 0.0 {
        Some(((-act - sz) / vz, (th.zthr - sz) / vz))
    } else {
        Some(((act - sz) / vz, (-th.zthr - sz) / vz))
    }
}

/// Times (over the whole real line) at which the horizontal condition holds at
/// `s + t v` (SEM-2, NUM-2 to NUM-4). The start of the vertical window, `tv`, is
/// where the stationary snap (NUM-2) is evaluated.
fn horizontal_set(
    sx: f64,
    sy: f64,
    vx: f64,
    vy: f64,
    tv: f64,
    th: &Thresholds,
) -> Option<(f64, f64)> {
    let d2 = th.dthr * th.dthr;
    let a = vx * vx + vy * vy;
    if a < SNAP {
        // No relative horizontal motion, or almost none (NUM-2).
        let (x, y) = (sx + tv * vx, sy + tv * vy);
        if x * x + y * y <= d2 {
            return Some((f64::NEG_INFINITY, f64::INFINITY));
        }
        if a == 0.0 {
            return None;
        }
    }
    let ss = sx * sx + sy * sy;
    let inside = ss <= d2; // Closed boundary (NUM-3).
    let cross = sx * vy - sy * vx;
    // The circle discriminant a * (DTHR^2 - HMD^2), by Lagrange's identity.
    let disc_c = d2 * a - cross * cross;
    if !inside && disc_c < 0.0 {
        return None; // The miss distance exceeds DTHR (SEM-2).
    }
    let disc_c = disc_c.max(0.0); // A discriminant rounded below zero is a tangency (NUM-4).
    let sv = sx * vx + sy * vy;
    // Exit from the DTHR circle: the larger root of a t^2 + 2 sv t + (ss - DTHR^2).
    let (_, t2) = roots(a, sv, ss - d2, disc_c.sqrt());
    // First time at which the modified tau is at most TTHR: the smaller root of
    // a t^2 + (2 sv + TTHR a) t + (ss + TTHR sv - DTHR^2), whose quarter-discriminant is
    // disc_c + (TTHR a / 2)^2.
    let half_ta = 0.5 * th.tthr * a;
    let (r1, _) = roots(
        a,
        sv + half_ta,
        ss + th.tthr * sv - d2,
        (disc_c + half_ta * half_ta).sqrt(),
    );
    if inside {
        // The condition holds at t = 0, so the set must contain 0 (SEM-5 at t = 0).
        Some((r1.min(0.0), t2.max(0.0)))
    } else {
        Some((r1, t2))
    }
}

/// Detection interval (SEM-5) of an encounter within the lookahead window
/// `[b, t]`, where `0 <= b < t` (ENV-2).
pub fn detect(th: &Thresholds, e: &Encounter, b: f64, t: f64) -> Result<Detection, Error> {
    check_encounter(e)?;
    if !(b.is_finite() && t.is_finite()) {
        return Err(Error::NonFiniteInput);
    }
    if !(0.0 <= b && b < t && t <= MAX_POS) {
        return Err(Error::BadLookahead);
    }
    Ok(detect_unchecked(th, e, b, t))
}

fn detect_unchecked(th: &Thresholds, e: &Encounter, b: f64, t: f64) -> Detection {
    let s = e.so.sub(e.si); // Only the relative state matters (SEM-1).
    let v = e.vo.sub(e.vi);
    let Some((v_lo, v_hi)) = vertical_set(s.z, v.z, th) else {
        return Detection::EMPTY;
    };
    let tv = b.max(v_lo);
    let Some((h_lo, h_hi)) = horizontal_set(s.x, s.y, v.x, v.y, tv, th) else {
        return Detection::EMPTY;
    };
    let lo = tv.max(h_lo);
    let hi = t.min(v_hi).min(h_hi);
    let d = Detection {
        t_in: lo,
        t_out: hi,
    };
    if d.conflict() {
        d
    } else {
        Detection::EMPTY // The canonical empty result, as in the original component (IF-1).
    }
}

/// Whether the encounter is currently a well-clear violation, which is defined
/// as a detection on `[0, 1]` that starts at (almost) zero (SEM-8).
pub fn violation(th: &Thresholds, e: &Encounter) -> Result<bool, Error> {
    check_encounter(e)?;
    let d = detect_unchecked(th, e, 0.0, 1.0);
    Ok(d.conflict() && almost_equals(d.t_in, 0.0))
}

/// Whether there is a conflict within the lookahead window `[b, t]` (ENV-2): if
/// `b` is almost equal to `t`, this is an instantaneous check, and if `b > t`,
/// there is no conflict.
pub fn conflict(th: &Thresholds, e: &Encounter, b: f64, t: f64) -> Result<bool, Error> {
    check_encounter(e)?;
    if !(b.is_finite() && t.is_finite()) {
        return Err(Error::NonFiniteInput);
    }
    if !((0.0..=MAX_POS).contains(&b) && t <= MAX_POS) {
        return Err(Error::BadLookahead);
    }
    if almost_equals(b, t) {
        let d = detect_unchecked(th, e, b, b + 1.0);
        return Ok(d.conflict() && almost_equals(d.t_in, b));
    }
    if b > t {
        return Ok(false);
    }
    Ok(detect_unchecked(th, e, b, t).conflict())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn enc(so: [f64; 3], vo: [f64; 3], si: [f64; 3], vi: [f64; 3]) -> Encounter {
        let v = |a: [f64; 3]| Vec3::new(a[0], a[1], a[2]);
        Encounter {
            so: v(so),
            vo: v(vo),
            si: v(si),
            vi: v(vi),
        }
    }

    #[test]
    fn head_on_conflict_interval() {
        // Closing at 400 m/s from 20 km at the same altitude.
        let th = Thresholds::do365_dwc_phase_i();
        let e = enc(
            [0., 0., 3000.],
            [200., 0., 0.],
            [20000., 0., 3000.],
            [-200., 0., 0.],
        );
        let d = detect(&th, &e, 0.0, 180.0).unwrap();
        assert!(d.conflict());
        // Exit when the range equals DTHR on the far side: (20000 + 1222.32) / 400.
        assert!((d.t_out - (20000.0 + 1222.32) / 400.0).abs() < 1e-9);
        assert!(!violation(&th, &e).unwrap());
    }

    #[test]
    fn tangential_contact_is_not_a_violation() {
        // Exactly on the circle, moving tangentially away from the closest point (SEM-8).
        let th = Thresholds::do365_dwc_phase_i();
        let e = enc(
            [0.66 * 1852.0, 0., 3000.],
            [0., 75., 0.],
            [0., 0., 3000.],
            [0., 0., 0.],
        );
        assert!(!violation(&th, &e).unwrap());
    }

    #[test]
    fn exact_tangency_is_a_conflict() {
        // A horizontal miss distance of exactly DTHR gives a horizontal violation set that is
        // TTHR seconds long, here [-15, 20], clipped by the lookahead window to [0, 20] (NUM-4).
        let th = Thresholds::do365_dwc_phase_i();
        let e = enc(
            [0.66 * 1852.0, 2000., 3000.],
            [0., -100., 0.],
            [0., 0., 3000.],
            [0.; 3],
        );
        let d = detect(&th, &e, 0.0, 180.0).unwrap();
        assert!(d.conflict());
        assert_eq!(d.t_in, 0.0);
        assert!((d.t_out - 20.0).abs() < 1e-6);
    }

    #[test]
    fn symmetric_under_exchange() {
        // Exchanging ownship and intruder does not change the result (SEM-6).
        let th = Thresholds::do365_dwc_phase_i();
        let (so, vo) = ([0., -8000., 3000.], [0., 200., 0.]);
        let (si, vi) = ([-8000., 0., 3030.], [200., 0., -1.]);
        let d = detect(&th, &enc(so, vo, si, vi), 0.0, 180.0).unwrap();
        assert_eq!(d, detect(&th, &enc(si, vi, so, vo), 0.0, 180.0).unwrap());
    }

    #[test]
    fn rejects_what_the_original_sanitizes() {
        assert_eq!(
            Thresholds::new(-1222.0, 137.0, 35.0, 0.0),
            Err(Error::BadThreshold)
        );
        let th = Thresholds::do365_dwc_phase_i();
        let e = enc([f64::NAN, 0., 0.], [0.; 3], [0.; 3], [0.; 3]);
        assert_eq!(detect(&th, &e, 0.0, 180.0), Err(Error::NonFiniteInput));
        let e = enc([0.; 3], [0.; 3], [0.; 3], [0.; 3]);
        assert_eq!(detect(&th, &e, 50.0, 10.0), Err(Error::BadLookahead));
        assert_eq!(detect(&th, &e, -5.0, 10.0), Err(Error::BadLookahead));
    }

    #[test]
    fn instantaneous_and_inverted_windows() {
        // An almost-empty window is an instantaneous check, and an inverted one has no conflict.
        let th = Thresholds::do365_dwc_phase_i();
        let e = enc(
            [0., 0., 3000.],
            [100., 0., 0.],
            [500., 0., 3000.],
            [-100., 0., 0.],
        );
        assert!(conflict(&th, &e, 0.0, 0.0).unwrap());
        assert!(!conflict(&th, &e, 50.0, 10.0).unwrap());
    }
}
