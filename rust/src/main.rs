//! Test harness for the regenerated component (not part of the component itself).
//!
//! ```text
//! wellclear run <vectors.csv> <results.csv>  results for every vector (same columns as the Java harness)
//! wellclear bench <vectors.csv> <passes>     time and heap allocation per call (PERF-2, IMP-3)
//! wellclear fuzz <iterations> <seed>         arbitrary bit patterns: panics, invariants, errors (IMP-1, IMP-2)
//! ```
use std::alloc::{GlobalAlloc, Layout, System};
use std::collections::HashMap;
use std::fs;
use std::hint::black_box;
use std::process::ExitCode;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;
use wellclear::{conflict, detect, violation, Detection, Encounter, Error, Thresholds, Vec3};

/// Global allocator that counts the bytes allocated, so that the benchmark can report heap
/// allocation per call. This is test instrumentation only; the component crate forbids unsafe
/// code.
struct Counting;

static ALLOCATED: AtomicUsize = AtomicUsize::new(0);

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCATED.fetch_add(layout.size(), Ordering::Relaxed);
        System.alloc(layout)
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        System.dealloc(pointer, layout)
    }
}

#[global_allocator]
static GLOBAL: Counting = Counting;

/// Numeric columns of a test vector, in the order used below.
const FIELDS: [&str; 18] = [
    "sox", "soy", "soz", "vox", "voy", "voz", "six", "siy", "siz", "vix", "viy", "viz", "B", "T",
    "DTHR", "ZTHR", "TTHR", "TCOA",
];

/// Read the identifier and the numeric columns of every vector in a CSV file.
fn read(path: &str) -> Result<Vec<(String, [f64; 18])>, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("cannot read {path}: {e}"))?;
    let mut lines = text.lines();
    let header: Vec<&str> = lines.next().ok_or("empty file")?.split(',').collect();
    let column = |name: &str| {
        header
            .iter()
            .position(|h| *h == name)
            .ok_or(format!("missing column {name}"))
    };
    let id = column("id")?;
    let indices = FIELDS
        .iter()
        .map(|f| column(f))
        .collect::<Result<Vec<usize>, String>>()?;
    lines
        .map(|line| {
            let cells: Vec<&str> = line.split(',').collect();
            let mut values = [0.0; 18];
            for (value, &i) in values.iter_mut().zip(indices.iter()) {
                *value = cells[i]
                    .parse::<f64>()
                    .map_err(|e| format!("bad number in {line}: {e}"))?;
            }
            Ok((cells[id].to_string(), values))
        })
        .collect()
}

fn encounter(v: &[f64; 18]) -> Encounter {
    Encounter {
        so: Vec3::new(v[0], v[1], v[2]),
        vo: Vec3::new(v[3], v[4], v[5]),
        si: Vec3::new(v[6], v[7], v[8]),
        vi: Vec3::new(v[9], v[10], v[11]),
    }
}

fn flag(x: bool) -> &'static str {
    if x {
        "1"
    } else {
        "0"
    }
}

/// Write the detection interval, conflict flag, violation flag, and conflict flag on the
/// lookahead window (or the error) for every vector.
fn run(input: &str, output: &str) -> Result<(), String> {
    let mut out = String::from("id,t_in,t_out,conflict,violation,conflict_bt,error\n");
    for (id, v) in read(input)? {
        let e = encounter(&v);
        let result = Thresholds::new(v[14], v[15], v[16], v[17]).and_then(|th| {
            let d = detect(&th, &e, v[12], v[13])?;
            Ok((d, violation(&th, &e)?, conflict(&th, &e, v[12], v[13])?))
        });
        match result {
            Ok((d, now, within)) => out.push_str(&format!(
                "{id},{},{},{},{},{},\n",
                d.t_in,
                d.t_out,
                flag(d.conflict()),
                flag(now),
                flag(within)
            )),
            Err(error) => out.push_str(&format!("{id},,,,,,{error:?}\n")),
        }
    }
    fs::write(output, out).map_err(|e| format!("cannot write {output}: {e}"))
}

/// Measure the time per call (median and minimum over the passes, after 10 warm-up passes)
/// and the heap allocation per call of `detect` and `violation` on the valid vectors.
fn bench(input: &str, passes: usize) -> Result<(), String> {
    let mut cases = Vec::new();
    let mut tables: HashMap<[u64; 4], Thresholds> = HashMap::new();
    for (_, v) in read(input)? {
        let Ok(th) = Thresholds::new(v[14], v[15], v[16], v[17]) else {
            continue;
        };
        let e = encounter(&v);
        if detect(&th, &e, v[12], v[13]).is_err() {
            continue;
        }
        let key = [v[14], v[15], v[16], v[17]].map(f64::to_bits);
        let th = *tables.entry(key).or_insert(th);
        cases.push((th, e, v[12], v[13]));
    }
    let n = cases.len();
    for kind in ["detect", "violation"] {
        let mut times = Vec::new();
        let mut total = 0.0;
        let mut bytes = 0;
        for pass in 0..passes + 10 {
            let before = ALLOCATED.load(Ordering::Relaxed);
            let start = Instant::now();
            if kind == "detect" {
                for (th, e, b, t) in &cases {
                    let d: Detection = detect(black_box(th), black_box(e), *b, *t).unwrap();
                    total += d.t_out;
                }
            } else {
                for (th, e, _, _) in &cases {
                    if violation(black_box(th), black_box(e)).unwrap() {
                        total += 1.0;
                    }
                }
            }
            let elapsed = start.elapsed().as_nanos() as f64 / n as f64;
            let after = ALLOCATED.load(Ordering::Relaxed);
            if pass >= 10 {
                times.push(elapsed);
                bytes = after - before;
            }
        }
        black_box(total);
        times.sort_by(|a, b| a.total_cmp(b));
        println!(
            "{kind} n={n} passes={passes} ns_per_call_median={:.2} ns_per_call_min={:.2} bytes_per_call={:.1}",
            times[times.len() / 2],
            times[0],
            bytes as f64 / n as f64
        );
    }
    Ok(())
}

/// Deterministic, dependency-free pseudorandom generator (xorshift64*).
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545F4914F6CDD1D)
    }

    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }

    fn value(&mut self) -> f64 {
        const SPECIAL: [f64; 8] = [
            0.0,
            -0.0,
            f64::NAN,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::MIN_POSITIVE,
            f64::MAX,
            1e-13,
        ];
        match self.next() % 8 {
            0 => f64::from_bits(self.next()), // Any bit pattern: NaN, infinity, subnormal, huge.
            1 => SPECIAL[(self.next() % 8) as usize],
            2 => (self.unit() - 0.5) * 2e12, // Beyond the numeric validity range.
            _ => (self.unit() - 0.5) * 2e5,  // Plausible magnitudes.
        }
    }
}

/// Call the component on arbitrary inputs and count panics, malformed results, and errors.
fn fuzz(iterations: u64, seed: u64) {
    std::panic::set_hook(Box::new(|_| {})); // Panics are counted below.
    let mut rng = Rng(seed | 1);
    let mut errors: HashMap<String, u64> = HashMap::new();
    let (mut ok, mut panics, mut malformed, mut conflicts) = (0u64, 0u64, 0u64, 0u64);
    for _ in 0..iterations {
        let mut v = [0.0; 18];
        for x in v.iter_mut() {
            *x = rng.value();
        }
        if rng.next().is_multiple_of(2) {
            // Half of the time, keep the thresholds and lookahead sensible so that the geometry
            // code is exercised.
            v[12] = rng.unit() * 60.0;
            v[13] = v[12] + rng.unit() * 180.0 + 1e-3;
            v[14..].copy_from_slice(&[1222.32, 137.16, 35.0, 0.0]);
        }
        let result = std::panic::catch_unwind(|| {
            let th = Thresholds::new(v[14], v[15], v[16], v[17])?;
            let e = encounter(&v);
            let d = detect(&th, &e, v[12], v[13])?;
            violation(&th, &e)?;
            conflict(&th, &e, v[12], v[13])?;
            Ok::<Detection, Error>(d)
        });
        match result {
            Err(_) => panics += 1,
            Ok(Err(e)) => *errors.entry(format!("{e:?}")).or_default() += 1,
            Ok(Ok(d)) => {
                ok += 1;
                let well_formed = d == Detection::EMPTY
                    || (d.t_in.is_finite()
                        && d.t_out.is_finite()
                        && v[12] <= d.t_in
                        && d.t_in < d.t_out
                        && d.t_out <= v[13]);
                if !well_formed {
                    malformed += 1;
                }
                if d.conflict() {
                    conflicts += 1;
                }
            }
        }
    }
    let mut errors: Vec<_> = errors.into_iter().collect();
    errors.sort();
    println!(
        "fuzz iterations={iterations} ok={ok} conflicts={conflicts} panics={panics} \
         invariant_violations={malformed} errors={errors:?}"
    );
}

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().collect();
    let parameters: Vec<&str> = arguments.iter().skip(1).map(String::as_str).collect();
    let result = match parameters.as_slice() {
        ["run", input, output] => run(input, output),
        ["bench", input, passes] => passes
            .parse()
            .map_err(|e| format!("bad number of passes: {e}"))
            .and_then(|passes| bench(input, passes)),
        ["fuzz", iterations, seed] => match (iterations.parse(), seed.parse()) {
            (Ok(iterations), Ok(seed)) => {
                fuzz(iterations, seed);
                Ok(())
            }
            _ => Err("bad number of iterations or seed".to_string()),
        },
        _ => Err("usage: wellclear run <vectors.csv> <results.csv> | \
                  bench <vectors.csv> <passes> | fuzz <iterations> <seed>"
            .to_string()),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}
