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

Fourteen cases: one poisoned row per check, plus a clean set that has to stay
green. False red announces itself. False green does not, so the only way to
trust a check is to have watched it fail.

## Licence

MIT. Takuya Kobayakawa, 2026.
