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

Needs Python and RDKit. `conda install -c conda-forge rdkit`.

## Try it

```bash
python gate.py examples/rows.tsv        --out build/clean.tsv --out-root build --write-snapshot examples/snapshot.json
python gate.py examples/rows_broken.tsv --out build/clean.tsv --out-root build --snapshot examples/snapshot.json
```

The first writes three rows. The second is the same file with a plausible
error planted in each row, and it refuses on eight of the twelve checks
without writing anything.

## Check the checker

```bash
python selftest.py
python selftest.py --receipt PATH
python selftest_baseline.py
```

Fifteen cases: a poisoned row per check, a clean set that has to stay green,
and one that asserts the tool's own lists of checks have not drifted apart. The run also prints which checks no poison has exercised, counted from
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
