# extraction-gate

A skill for Claude Science, and a standalone script for anyone who just wants
the checks. It sits between an extraction and the file that extraction writes,
and it refuses the write when a row does not survive.

It exists because of four failures that got through a run of mine that
reported success, none of which raised an error: a correct formula on the
wrong skeleton, E built where the paper drew Z, two diastereomers with their
activities swapped, and six green checks written to a path that was not the
one I was reading. `SKILL.md` has the full account and the design that follows
from it.

## Install

Copy this directory into your skills folder:

- Claude Science: `~/.claude-science/skills/extraction-gate/`
- Claude Code: `~/.claude/skills/extraction-gate/`

Needs Python and RDKit. `conda install -c conda-forge rdkit`, or
`python -m pip install rdkit`. Nothing else is imported. Run the commands
below from the repository directory, and if your Python command is `python3`,
use that in place of `python`.

## Try it in five minutes

The script runs from a clone and does not need the skills folder. Make the
output directory first; `gate.py` does not create it, and C1 refuses the run
when it is missing, which is what C1 is for.

```bash
mkdir build
python gate.py examples/rows.tsv        --out build/clean.tsv --out-root build --write-snapshot build/snapshot.json
python gate.py examples/rows_broken.tsv --out build/clean.tsv --out-root build --snapshot build/snapshot.json
```

The first run writes three rows, exits 0, and ends with

```
  3 check(s) had nothing to work with: C3, C7, C9
  snapshot written to build/snapshot.json
  PASSED all checks, 3 rows written and read back.
```

C3 and C7 compare with a run you have already accepted, so on a first run
they have nothing to look at, and C9 is off without `--chembl`. The snapshot
is the accepted state of those three rows. `examples/snapshot.json` is a copy
of it.

The second file is the same rows with a plausible error planted in each, and
three more that collide with them. Against the snapshot it is refused on eight
of the twelve checks, exits 1, and writes nothing:

```
  REFUSED, 10 finding(s). Nothing was written.
    C2 r5: formula C6H12 does not match the paper's C9H20
    C4 r2: CIP labels 7:R do not match the paper's 7:S
    C4 r4: CIP labels 7:R do not match the paper's 7:S
    C5 10.1000/demo-a / seriesA: one structure carries 2 labels ['2', '3']
    C6 10.1000/demo-a: sequence AA-1 resolves to 2 different structures
    C7 r3: ring profile changed 1:6 to 1:5 while the formula stayed the same
    C8 r1: the paper draws E and no double bond is assigned (1 unassigned)
    C10: 1 measurement keys are stored more than once, 1 rows in excess. Collapse them before counting repeats.
          10.1000/demo-b | 4 | demo receptor | competition binding stored 2 times
    C11 label 1 is 2 different molecules across 2 reports. Do not key a cross-report match on it.
```

`build/clean.tsv` still holds the three rows from the first run. A step that
reads it after the second run gets the old rows, and the exit code is the only
thing that says so. That is the stale-file failure above, in miniature.

Then watch the checker itself:

```bash
python selftest.py
python selftest_baseline.py
```

Both exit 0. The first prints `16/16 cases` and `poison covers 11 of 12
checks`, and names C9 as the check no poison exercises offline. The second
ends with `checks_passing: 22`. What those lines mean is under "Check the
checker" below.

## What it cannot check

- It does not read the paper. `formula_reported`, `stereo_reported` and
  `geometry_reported` are what someone typed from the source, and the gate
  compares the structure with them. A wrong transcription there is a wrong
  reference, and the gate cannot tell.
- `value`, `unit`, `target`, `assay` and `readout` are compared with nothing.
  They are a key for C10 and nothing more. A correct structure carrying the
  wrong IC50 passes.
- A SMILES that does not parse is refused only by a check that has a column to
  compare it with. With the five required columns alone and no snapshot entry
  for that row, a row whose `smiles` reads `not_a_smiles` passes and is
  written.
- C9 needs the network and is off by default. It asks whether each structure
  is among the ones ChEMBL holds for the DOI. A DOI ChEMBL has not curated
  passes in silence, and the check does not compare activity values. It reads
  the first 1,000 activity records for the document, so on a larger document
  a deposited structure can be missed and the row refused.
- C3 and C7 compare with a snapshot from a run you accepted. On the first run
  they have nothing to look at, and the report says so. C12 runs without one:
  a repeated `row_id`, or a count that differs from `--expect`, is refused on
  the first run too. Only its third part, a row the snapshot holds that is not
  here now, needs the snapshot.
- C5, C6 and C11 compare canonical SMILES after the largest fragment is kept.
  A salt and its free ion are one molecule. A neutral acid and its anion, or
  two tautomers, are two.
- C8 looks at acyclic C=C bonds only, and accepts the row when any of them
  carries the printed letter. A double bond in a ring, or to a heteroatom, is
  not seen.

The gate says that the rows agree with what was typed next to them, with each
other, with the last run you accepted, and, with `--chembl`, with what ChEMBL
holds for the DOI. It does not say that the extracted values are right.

## Using it on your own table

The input is a TSV with five required columns: `row_id`, `doi`, `group`,
`label` and `smiles`. `group` is the series C5 looks within, usually one table
of one paper. C11 does not use it: it compares a label within one DOI and
across DOIs. The optional columns each switch on the checks
that read them: `formula_reported`, `stereo_reported`, `geometry_reported`,
`sequence`, and `target` `assay` `readout` `unit` `value`. `stereo_reported`
takes CIP labels in the form `7:S`, where 7 is the position of the atom in
your SMILES, counted from 1 after any counter-ion is dropped and the largest
fragment kept, and not the locant in the paper.
`geometry_reported` takes one letter, `E` or `Z`. A blank column skips the
checks that read it for that row, except in C10, which drops only rows with a
blank `value` and keeps a blank `target`, `assay`, `readout` or `unit` in the
key, and the report lists the checks that had nothing to work
with, so an empty column does not read as a pass. Keep `row_id` stable between
runs, because the snapshot is keyed on it. `examples/rows.tsv` has every
column filled.

If your corpus has no structures, the structure checks have nothing to
compare, except that C2, C4 and C8 still refuse a row whose
`formula_reported`, `stereo_reported` or `geometry_reported` is filled and
whose `smiles` is empty or does not parse, and C3 and C7 refuse it when the
snapshot holds a structure for that `row_id`. C1, C10 and C12 do not depend
on the field.
Each check is one function in `gate.py`, named in `CHECKS`, called in
`run_checks` and counted in `coverage()`. `selftest.py` asserts that `CHECKS`
and `coverage()` list the same checks and that each name in `CHECKS` finds a
`check_` function. A check that `run_checks` never calls shows up as a
`BLIND_SPOT` when its poison is run. Give a new check its own poisoned row in
`selftest.py` before you count on it.

## Check the checker

```bash
python selftest.py
python selftest.py --receipt PATH
python selftest_baseline.py
```

Sixteen cases: a poisoned row per check, a clean set that has to stay green,
and two that assert the tool's own lists of checks have not drifted apart, or
from the functions they name. The run also prints which checks no poison has exercised, counted from
the cases that ran rather than from a list kept by hand. False red announces
itself. False green does not, so the only way to trust a check is to have
watched it fail.

The clean set is the accepting baseline, and it runs before any poison: once as
it is, and once against its own accepted snapshot, so that C3 and C7 have rows
to look at too. If `gate.py` would refuse it, on any finding with or without a
check id, or a check raises on it, no poison is run and no coverage figure is
printed. The run reports `INVALID_BASELINE`, names the fixture, shows what was
expected and what happened, and exits 1 with this line:

```
No sensitivity figure was produced because the checker failed its accepting baseline.
```

A poison that its check does not catch is reported as `BLIND_SPOT`, with what
was expected, what fired, and whether the check was seen to run. That includes
a poison that makes a different check fire, and one whose check is never
called. It is not counted as a detection, and the run exits 1. A check stays on
the coverage line while at least one of its poisons was caught, and C11 and C12
have two each. Every fixture is `CHECKED`, `SKIPPED` with its reason (C9 is
declared and skipped offline), or `NOT_APPLICABLE` when its check has no rows
to look at in that fixture or had none in the baseline. A declared poison that
turns out not applicable cannot pass the run: unless something failed, the run
ends in `REVIEW` and exits 2, as the ledger does for a source it cannot decide.
A poison declared skipped, as C9 is, is not held against the run, and a run in
which no poison ran prints no figure at all. The coverage line counts checks;
the `*_mutations` counts under it count poisons.

`--receipt PATH` writes the result as JSON whatever the decision: `PASS` with
`terminal_cause` `none` (exit 0); `FAIL` with `INVALID_BASELINE`, `BLIND_SPOT`
or `structure_mismatch` (exit 1); or `REVIEW` with `unresolved` (exit 2).
Without a figure it carries no counts and no lists of what was caught, rather
than zeros. Like the ledger receipt, its shape is version 0 and experimental.
`selftest_baseline.py` breaks the clean set and the checker in memory and
asserts all of this.

## The rows you did not take

```bash
python ledger/build_ledger.py
python ledger/ledger_gate.py
python ledger/selftest_ledger.py
```

`ledger/` holds the exclusion ledger for the six-paper audit set behind the
Discourse thread on false green, and a gate for the identity
`extracted + excluded == total_rows`, per source table. It returns PASS, FAIL
or REVIEW. REVIEW exists so that a denominator nobody wrote down is reported
as `unavailable` rather than as zero, which would close the identity by
accident. The four states (measured, reported, unknown, unavailable) follow
Stephen Lutar's proposal in that thread. On the current ledger the gate fails,
and the selftest says which of its own cases it has watched go red, separating
the ones killed by the mutant written for them from the ones a coarse mutant
happened to kill as well. Aggregate mutation counts can overstate invariant
coverage when one coarse mutant breaks a shared evaluator path, which is why
`mutation_coverage_state` is taken from the narrower count (the observation is
Stephen Lutar's, on the thread). `--receipt PATH` writes the decision as JSON so a
caller does not have to read this output; its shape is version 0 and will move
before the corpus release.

`sensitivity/` holds the three evidence cuts, the two draw-matched baselines,
the duplicate-row gate and its fixtures, including the negative one: a
projection that repeats rows because it drops an identity column must not be
reported as corrupt.

## Licence

MIT. Takuya Kobayakawa, 2026.
