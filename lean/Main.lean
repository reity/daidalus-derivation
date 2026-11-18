import Wellclear

/-!
# Command-line checker

`lake env lean --run Main.lean certify INPUT OUTPUT` reads the answers of an implementation in
the format written by `python -m wellclear certify` (`lean-NAME.csv`: one row per test vector,
every number written as the hexadecimal bit pattern of an IEEE 754 double), certifies every
answer with `Wellclear.certify`, and writes the verdicts (`id,verdict`, one row per test vector).
The Python twin of the checker writes the same verdict file, and the two are compared byte for
byte. The same program can be compiled with `lake exe wellclear`, which first compiles the
imported part of Mathlib to native code.
-/

open Wellclear

/-- The value of a hexadecimal digit. -/
def hexDigit (c : Char) : Option Nat :=
  if '0' ≤ c ∧ c ≤ '9' then some (c.toNat - '0'.toNat)
  else if 'a' ≤ c ∧ c ≤ 'f' then some (c.toNat - 'a'.toNat + 10)
  else none

/-- The natural number written in hexadecimal. -/
def parseHex (text : String) : Option Nat :=
  if text.isEmpty then none
  else text.foldl (fun acc c => acc.bind fun n => (hexDigit c).map fun d => 16 * n + d) (some 0)

/-- The exact value of an IEEE 754 binary64 bit pattern, or `none` for an infinity or a NaN. -/
def ofBits (n : Nat) : Option ℚ :=
  let e : Nat := n / 2 ^ 52 % 2 ^ 11
  let m : Nat := n % 2 ^ 52
  if e = 2 ^ 11 - 1 then none
  else
    let mant : ℚ := if e = 0 then m else m + 2 ^ 52
    let shift : Int := if e = 0 then -1074 else (e : Int) - 1075
    let mag : ℚ := if 0 ≤ shift then mant * 2 ^ shift.toNat else mant / 2 ^ (-shift).toNat
    some (if n / 2 ^ 63 % 2 = 1 then -mag else mag)

/-- The number in a column of a row. -/
def column (cols : Array String) (i : Nat) : Option ℚ :=
  (parseHex (cols.getD i "")).bind ofBits

/-- The verdict for one row: the 18 inputs (ownship and intruder positions and velocities, the
lookahead window, and the thresholds), the answer, and the hint. -/
def verdict (cols : Array String) : Verdict :=
  match (List.range 18).mapM (fun i => column cols (i + 1)) with
  | none => .invalid
  | some vals =>
    let g := fun i => vals.getD i 0
    let so : Vec3 ℚ := ⟨g 0, g 1, g 2⟩
    let vo : Vec3 ℚ := ⟨g 3, g 4, g 5⟩
    let si : Vec3 ℚ := ⟨g 6, g 7, g 8⟩
    let vi : Vec3 ℚ := ⟨g 9, g 10, g 11⟩
    let p : Table ℚ := ⟨g 14, g 15, g 16, g 17⟩
    let B := g 12
    let T := g 13
    if p.Valid ∧ 0 ≤ B ∧ B < T then
      let answer :=
        if cols.getD 19 "" = "1" then Answer.conflict (column cols 20) (column cols 21)
        else Answer.clear
      certify p (rel so si) (rel vo vi) B T answer ((column cols 22).getD B)
    else .invalid

def main (args : List String) : IO UInt32 := do
  match args with
  | ["certify", input, output] =>
    let text ← IO.FS.readFile input
    let rows := ((text.splitOn "\n").filter (fun line => !line.isEmpty)).drop 1
    let results := rows.map fun line =>
      let cols := (line.splitOn ",").toArray
      (cols.getD 0 "", verdict cols)
    let lines := results.map fun (key, v) => key ++ "," ++ v.name
    IO.FS.writeFile output (String.intercalate "\n" ("id,verdict" :: lines) ++ "\n")
    let count := fun (v : Verdict) => (results.filter fun r => r.2 = v).length
    let summary := [Verdict.interval, .empty, .short, .uncertified, .invalid].map fun v =>
      toString (count v) ++ " " ++ v.name
    IO.println ("certified " ++ toString rows.length ++ " answers: " ++
      String.intercalate ", " summary)
    return 0
  | _ =>
    IO.eprintln "usage: wellclear certify INPUT OUTPUT"
    return 1
