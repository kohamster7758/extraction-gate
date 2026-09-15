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
```

Fifteen cases: a poisoned row per check, a clean set that has to stay green,
and one that asserts the tool's own lists of checks have not drifted apart. The run also prints which checks no poison has exercised, counted from
the cases that ran rather than from a list kept by hand. False red announces
itself. False green does not, so the only way to trust a check is to have
watched it fail.

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
and the selftest says which of its own cases it has watched go red.

## Licence

MIT. Takuya Kobayakawa, 2026.
