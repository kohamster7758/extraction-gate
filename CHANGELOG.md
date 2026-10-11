# Changelog

Newest first. Each entry is taken from the commit it names, with the commit
date. No release has been cut.

## Unreleased

### 2026-10-12

- selftest: a check nobody saw run is not a detection. A catch now needs the
  check seen to run, and a name in `CHECKS` that finds no function is a
  structure failure, printed with the function it looked for.
  `selftest_baseline.py` renames C4 in memory and asserts that the run fails
  and names it. (eb372c1)
- selftest: the glossary that came in with the baseline gate is gone, since the
  rest of the repository already says it in its own words, and the refusal line
  names the checker. (fce0f87)
- selftest baseline gate, contributed by Stephen Lutar in PR #2. The clean set
  is the accepting baseline and runs before any poison, as it is and against
  its own accepted snapshot. If `gate.py` would refuse it, no poison is run, no
  coverage figure is printed, and the run reports `INVALID_BASELINE` and exits
  1. A poison its check does not catch is a `BLIND_SPOT` and is not counted.
  Every fixture is `CHECKED`, `SKIPPED` or `NOT_APPLICABLE`; a declared poison
  whose check has nothing to look at ends the run in `REVIEW`, exit 2.
  `--receipt PATH` writes the result as JSON. `selftest_baseline.py` is new and
  asserts all of this in memory. `gate.py` is unchanged. (e1be7bc, merged as
  04aa082)

### 2026-09-21

- sensitivity: an absent table is not a clean one. `duplicate_rows.py` used to
  print `PASS` and return 0 on a directory holding none of its tables. It now
  exits 2 with `ABSTAIN` and prints which tables it read, which were empty and
  which were missing. Two fixtures cover the path. (a45c2ff)

### 2026-09-17

- ledger: the narrow eighth mutant kills exactly its own case, so
  `mutation_coverage_state` is `COMPLETE`. A disputed denominator outranks an
  open identity, as `claimed_total_conflict`. The receipt declares
  `extraction-gate-receipt/v0`, experimental. The suggestions are Stephen
  Lutar's, from the thread. (68d36d4)
- ledger: a JSON receipt on refusal, a `claimed_total_rows` column with its
  conflict state, and mutation coverage taken from the targeted count, so one
  coarse mutant killing several cases is not reported as several invariants
  watched. sensitivity: fixtures for the duplicate gate, including the false
  positive on a projection that repeats rows by construction. (4555e59)
- sensitivity: three evidence cuts, two draw-matched baselines, and a
  duplicate-row gate that reports rows, distinct rows and distinct measured
  values as three numbers. (4cac312)

### 2026-09-16

- ledger: the identity `extracted + excluded == total_rows` per source table,
  with `unavailable` as a state. An empty denominator resolves to `unavailable`,
  never to zero. (ccad0b1)

### 2026-09-08

- selftest: the first case asserts that `CHECKS` and `coverage()` agree, and
  goes red when a check is dropped from one of them. (cb4be86)
- selftest: coverage is counted from the cases that ran, and the checks no
  poison exercises are printed as untested. C9 was the overclaim. (aa336e3)
- C12 completeness: a row deleted between runs used to pass silently. C12 walks
  from the accepted snapshot to what is here now, refuses a repeated `row_id`,
  and `--expect` pins the row count. Found by a peer's deletion poison.
  (61d92e2)
- SKILL.md wording matched to the public write-up. (f10267c)
- First commit: eleven checks that gate the write, `selftest.py` with a
  poisoned row per check, two example files and a snapshot. (7ef5a93)
