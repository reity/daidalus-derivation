/**
 * Runs the JavaScript port of the regenerated component (web/wellclear.js) over
 * a corpus of test vectors and writes the results in the same CSV format as the
 * Java and Rust harnesses.
 *
 * Usage: node web/run-vectors.js <vectors.csv> <results.csv>
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const wellclear = require(path.join(__dirname, "wellclear.js"));

const FIELDS = [
  "sox", "soy", "soz", "vox", "voy", "voz", "six", "siy", "siz", "vix", "viy", "viz",
  "B", "T", "DTHR", "ZTHR", "TTHR", "TCOA",
];

/** Number represented by a CSV entry (the corpus writes non-finite values as nan, inf, -inf). */
const number = (text) =>
  ({ nan: NaN, inf: Infinity, "-inf": -Infinity })[text] ?? Number(text);

/** Shortest round-trip representation, with infinities written as the Rust harness writes them. */
const format = (x) => (x === Infinity ? "inf" : x === -Infinity ? "-inf" : String(x));

/** Results row for a single vector (or the error with which the vector was rejected). */
const evaluate = (id, v) => {
  const e = { so: v.slice(0, 3), vo: v.slice(3, 6), si: v.slice(6, 9), vi: v.slice(9, 12) };
  try {
    const th = wellclear.thresholds(v[14], v[15], v[16], v[17]);
    const d = wellclear.detect(th, e, v[12], v[13]);
    const now = wellclear.violation(th, e);
    const within = wellclear.conflict(th, e, v[12], v[13]);
    const flags = [wellclear.conflictOf(d), now, within].map((x) => (x ? 1 : 0));
    return [id, format(d.t_in), format(d.t_out), ...flags, ""].join(",");
  } catch (error) {
    return `${id},,,,,,${error.message}`;
  }
};

const main = (input, output) => {
  const lines = fs.readFileSync(input, "utf8").trim().split(/\r?\n/);
  const header = lines[0].split(",");
  const indices = FIELDS.map((field) => header.indexOf(field));
  const id = header.indexOf("id");
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(",");
    return evaluate(cells[id], indices.map((i) => number(cells[i])));
  });
  fs.writeFileSync(output, ["id,t_in,t_out,conflict,violation,conflict_bt,error", ...rows].join("\n") + "\n");
};

if (process.argv.length !== 4) {
  console.error("usage: node web/run-vectors.js <vectors.csv> <results.csv>");
  process.exit(1);
}
main(process.argv[2], process.argv[3]);
