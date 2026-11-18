# Reproduction of every result in this repository.
#
# The committed corpus (data/vectors.csv.gz) is decompressed into build/, the original DAIDALUS
# component is fetched at the pinned commit and compiled together with the harness, and the
# exact model and all three implementations are run on the corpus. The command "make verify"
# checks that the reproduced outputs match the committed checksums and results.

PYTHON ?= python3
JAVA ?= java
JAVAC ?= javac
NODE ?= node
CARGO ?= cargo

BUILD := build
DAIDALUS := $(BUILD)/daidalus
CLASSES := $(BUILD)/classes
WELLCLEAR := PYTHONPATH=src $(PYTHON) -m wellclear
REGENERATED := rust/target/release/wellclear
VECTORS := $(BUILD)/vectors.csv
RESULTS := $(BUILD)/oracle.csv $(BUILD)/original.csv $(BUILD)/rust.csv $(BUILD)/js.csv
IMPLEMENTATIONS := orig=$(BUILD)/original.csv rust=$(BUILD)/rust.csv js=$(BUILD)/js.csv
CERTIFIED := $(BUILD)/certify
FUZZ := 20000000 20261117

.PHONY: all requirements corpus daidalus harness rust results checksums grades certify fuzz bench \
	summary page verify lean test lint clean

all: results

# Derived requirements (derivation/requirements.json and derivation/requirements.md).
requirements:
	$(WELLCLEAR) requirements derivation

# Regeneration of the corpus. The bytes are only expected to match the committed corpus on the
# platform on which it was generated (Linux x86-64, glibc 2.39, CPython 3.13), because some
# categories depend on the platform's math library.
corpus:
	mkdir -p $(BUILD)
	$(WELLCLEAR) vectors $(BUILD)/vectors-regenerated.csv
	gzip -dc data/vectors.csv.gz | cmp - $(BUILD)/vectors-regenerated.csv
	@echo "the regenerated corpus is identical to data/vectors.csv.gz"

$(VECTORS): data/vectors.csv.gz
	mkdir -p $(BUILD)
	gzip -dc $< > $@

# The original component: DAIDALUS at the pinned commit, compiled with the harness.
daidalus:
	sh scripts/fetch-daidalus.sh $(DAIDALUS)

$(CLASSES)/DaidalusDriver.class: harness/DaidalusDriver.java | daidalus
	mkdir -p $(CLASSES)
	find $(DAIDALUS)/Java/src -name '*.java' | sort > $(BUILD)/sources.txt
	$(JAVAC) -nowarn -encoding UTF-8 -d $(CLASSES) @$(BUILD)/sources.txt $<

harness: $(CLASSES)/DaidalusDriver.class

# The regenerated component and its harness.
$(REGENERATED): rust/Cargo.toml rust/Cargo.lock rust/src/lib.rs rust/src/main.rs
	cd rust && $(CARGO) build --release --locked

rust: $(REGENERATED)

$(BUILD)/oracle.csv: $(VECTORS) src/wellclear/oracle.py
	$(WELLCLEAR) oracle $< $@

$(BUILD)/original.csv: $(VECTORS) $(CLASSES)/DaidalusDriver.class
	$(JAVA) -cp $(CLASSES) DaidalusDriver run $< $@

$(BUILD)/rust.csv: $(VECTORS) $(REGENERATED)
	$(REGENERATED) run $< $@

$(BUILD)/js.csv: $(VECTORS) web/wellclear.js web/run-vectors.js
	$(NODE) web/run-vectors.js $< $@

results: $(RESULTS)

checksums: results
	cd $(BUILD) && sha256sum --check ../results/SHA256SUMS

# Committed results (results/ and index.html).
grades: results
	$(WELLCLEAR) check $(VECTORS) $(BUILD)/oracle.csv results/grades.json $(IMPLEMENTATIONS)

# Certification of every answer of every implementation by the executable twin of the Lean
# checker (lean/Wellclear/Check.lean), which also writes the input files of the Lean checker.
certify: results
	$(WELLCLEAR) certify $(VECTORS) $(BUILD)/oracle.csv $(CERTIFIED) results/certify.json \
	  $(IMPLEMENTATIONS)

fuzz: rust
	$(REGENERATED) fuzz $(FUZZ) > results/fuzz.txt

bench: $(VECTORS) harness rust
	$(WELLCLEAR) environment > results/bench.txt
	for run in 1 2 3; do \
	  $(JAVA) -cp $(CLASSES) DaidalusDriver bench $(VECTORS) 40 | sed "s/^/java run$$run /" \
	    >> results/bench.txt; \
	  $(REGENERATED) bench $(VECTORS) 40 | sed "s/^/rust run$$run /" >> results/bench.txt; \
	done

summary: results
	$(WELLCLEAR) summary results/summary.json

page:
	$(WELLCLEAR) page index.html

# Reproduce every committed result (except the machine-dependent benchmark) and compare.
verify: checksums rust
	$(WELLCLEAR) check $(VECTORS) $(BUILD)/oracle.csv $(BUILD)/grades.json $(IMPLEMENTATIONS)
	cmp $(BUILD)/grades.json results/grades.json
	$(WELLCLEAR) certify $(VECTORS) $(BUILD)/oracle.csv $(CERTIFIED) $(BUILD)/certify.json \
	  $(IMPLEMENTATIONS)
	cmp $(BUILD)/certify.json results/certify.json
	$(REGENERATED) fuzz $(FUZZ) > $(BUILD)/fuzz.txt
	cmp $(BUILD)/fuzz.txt results/fuzz.txt
	$(WELLCLEAR) summary $(BUILD)/summary.json --grades $(BUILD)/grades.json \
	  --certify $(BUILD)/certify.json --fuzz $(BUILD)/fuzz.txt
	cmp $(BUILD)/summary.json results/summary.json
	$(WELLCLEAR) page $(BUILD)/index.html --summary $(BUILD)/summary.json
	cmp $(BUILD)/index.html index.html
	@echo "every committed result was reproduced"

# The Lean development (requires elan; see lean/README.md). Building it checks every proof, and the
# axioms on which the main theorems depend are compared with the committed list. The Lean checker
# then certifies the answers of every implementation (run by the Lean interpreter, which avoids
# compiling Mathlib to native code), and its verdicts are compared with those of its executable
# twin.
LEAN_NAMES := orig rust js

lean: $(RESULTS)
	$(WELLCLEAR) certify $(VECTORS) $(BUILD)/oracle.csv $(CERTIFIED) $(BUILD)/certify-lean.json \
	  $(IMPLEMENTATIONS)
	cd lean && lake build
	cd lean && lake env lean scripts/axioms.lean > ../$(BUILD)/axioms.txt
	diff results/axioms.txt $(BUILD)/axioms.txt
	for name in $(LEAN_NAMES); do \
	  (cd lean && lake env lean --run Main.lean certify ../$(CERTIFIED)/lean-$$name.csv \
	    ../$(CERTIFIED)/lean-verdicts-$$name.csv) || exit 1; \
	  cmp $(CERTIFIED)/certify-$$name.csv $(CERTIFIED)/lean-verdicts-$$name.csv || exit 1; \
	done
	@echo "the Lean checker reproduced every verdict"

test:
	PYTHONPATH=src $(PYTHON) -m pytest
	cd rust && $(CARGO) test --release --locked
	$(NODE) --test web/*.test.js

lint:
	$(PYTHON) -m pylint src/wellclear
	cd rust && $(CARGO) fmt --check && $(CARGO) clippy --all-targets --locked -- -D warnings

clean:
	rm -rf $(BUILD) rust/target lean/.lake
