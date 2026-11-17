/**
 * Unit tests of the JavaScript port of the regenerated component.
 *
 * Usage: node --test web/*.test.js
 */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const wellclear = require("./wellclear.js");

const PHASE_I = wellclear.thresholds(0.66 * 1852.0, 450 * 0.3048, 35.0, 0.0);
const encounter = (so, vo, si, vi) => ({ so, vo, si, vi });

test("head-on encounter has the closed-form interval", () => {
  const e = encounter([0, 0, 3000], [200, 0, 0], [20000, 0, 3000], [-200, 0, 0]);
  const d = wellclear.detect(PHASE_I, e, 0, 180);
  const dthr = 0.66 * 1852.0;
  assert.ok(wellclear.conflictOf(d));
  assert.ok(Math.abs(d.t_in - (20000 - (7000 + Math.sqrt(7000 ** 2 + dthr ** 2))) / 400) < 1e-9);
  assert.ok(Math.abs(d.t_out - (20000 + dthr) / 400) < 1e-9);
  assert.equal(wellclear.violation(PHASE_I, e), false);
});

test("exact tangency is a conflict and one ULP outside is not", () => {
  const dthr = 0.66 * 1852.0;
  const tangent = encounter([dthr, 2000, 3000], [0, -100, 0], [0, 0, 3000], [0, 0, 0]);
  assert.ok(wellclear.conflictOf(wellclear.detect(PHASE_I, tangent, 0, 180)));
  const next = dthr + Number.EPSILON * 1024; // One unit in the last place above DTHR.
  const outside = encounter([next, 2000, 3000], [0, -100, 0], [0, 0, 3000], [0, 0, 0]);
  assert.deepEqual(wellclear.detect(PHASE_I, outside, 0, 180), wellclear.EMPTY);
});

test("boundary contact at time zero is not a violation", () => {
  const e = encounter([0.66 * 1852.0, 0, 3000], [0, 75, 0], [0, 0, 3000], [0, 0, 0]);
  assert.equal(wellclear.violation(PHASE_I, e), false);
});

test("exchanging the aircraft does not change the result", () => {
  const [so, vo, si, vi] = [[0, -8000, 3000], [0, 200, 0], [-8000, 0, 3030], [200, 0, -1]];
  assert.deepEqual(
    wellclear.detect(PHASE_I, encounter(so, vo, si, vi), 0, 180),
    wellclear.detect(PHASE_I, encounter(si, vi, so, vo), 0, 180),
  );
});

test("invalid inputs are rejected with an explicit error", () => {
  const e = encounter([0, 0, 0], [0, 0, 0], [500, 0, 0], [0, 0, 0]);
  assert.throws(() => wellclear.thresholds(-1222.32, 137.16, 35, 0), /BadThreshold/);
  assert.throws(() => wellclear.thresholds(NaN, 137.16, 35, 0), /NonFiniteInput/);
  assert.throws(() => wellclear.detect(PHASE_I, { ...e, so: [Infinity, 0, 0] }, 0, 180), /NonFiniteInput/);
  assert.throws(() => wellclear.detect(PHASE_I, { ...e, vo: [2e6, 0, 0] }, 0, 180), /OutOfRange/);
  assert.throws(() => wellclear.detect(PHASE_I, e, 50, 10), /BadLookahead/);
  assert.throws(() => wellclear.detect(PHASE_I, e, -5, 10), /BadLookahead/);
});

test("almost equality follows the DAIDALUS tolerance", () => {
  assert.ok(wellclear.almostEquals(1, 1 + 1e-12));
  assert.ok(wellclear.almostEquals(0, 5e-14));
  assert.ok(!wellclear.almostEquals(1, 1 + 1e-11));
  assert.ok(!wellclear.almostEquals(Infinity, 1e308));
});

test("results on the explorer presets are identical to the Rust results", () => {
  const summary = JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "results", "summary.json"), "utf8"),
  );
  const number = (x) => ({ inf: Infinity, "-inf": -Infinity })[x] ?? x;
  for (const preset of summary.presets) {
    const x = preset.x;
    const th = wellclear.thresholds(x.DTHR, x.ZTHR, x.TTHR, x.TCOA);
    const e = encounter([x.sox, x.soy, x.soz], [x.vox, x.voy, x.voz], [x.six, x.siy, x.siz], [x.vix, x.viy, x.viz]);
    const d = wellclear.detect(th, e, x.B, x.T);
    assert.equal(d.t_in, number(preset.rust.t_in), preset.id);
    assert.equal(d.t_out, number(preset.rust.t_out), preset.id);
    assert.equal(wellclear.violation(th, e), preset.rust.violation, preset.id);
  }
});
