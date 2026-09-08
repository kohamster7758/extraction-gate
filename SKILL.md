---
name: extraction-gate
description: Mechanical checks that gate the write when structured chemistry or bioactivity data is pulled out of papers. Use when an agent has extracted compounds, structures or activity values from literature and is about to write them to a file, when rebuilt SMILES need to be reconciled against what the paper printed, when a matched-pair or repeat count is about to be taken from extracted rows, or when a run reported success and the numbers downstream look wrong. Catches the failures that return a plausible value instead of an error.
license: MIT
---

# extraction-gate

The failures worth worrying about in literature extraction are not the ones
that raise. They come back as a plausible number. Four that got through a run
of mine that reported success:

1. A compound with the correct molecular formula and the wrong skeleton. The
   formula check passed because atoms were conserved while the ring was not.
2. A double bond built as E where the paper had drawn Z. Same formula, same
   skeleton, and the two differ in potency by more than three orders of
   magnitude.
3. Two diastereomers with their activities attached to the wrong structures.
   Nothing internal to the data could see this. It surfaced only against an
   external database, matched on the DOI.
4. A run that reported six green checks and wrote nothing. The output path
   resolved somewhere else, and every downstream number came from a stale file.

Two things follow, and they are the whole design.

**The check has to gate the write, not the read.** Every check run after the
fact eventually gets forgotten. This one refuses to write the file.

**A second database is worth more than a second prompt,** and it should be
keyed on the paper rather than the compound name, because names are not
unique. A printed compound label is unique inside its own table and nowhere
else.

## When to use this

Run it before writing extracted rows anywhere that something else will read.
Also run it before counting matched pairs, repeats or duplicates, because two
of the checks exist to stop counts that are inflated by bookkeeping.

## Input

A TSV. Required columns: `row_id`, `doi`, `group`, `label`, `smiles`.

Optional columns, each enabling the checks that use it: `formula_reported`,
`stereo_reported`, `geometry_reported`, `sequence`, and `target` `assay`
`readout` `unit` `value`. Give `stereo_reported` the CIP labels as printed,
in the form `7:S`, and `geometry_reported` a single `E` or `Z`.

Leave a column blank and its checks are skipped for that row rather than
passed. The report says which checks had nothing to work with.

## Running it

```bash
python gate.py rows.tsv --out build/clean.tsv --out-root build
python gate.py rows.tsv --out build/clean.tsv --out-root build --write-snapshot snap.json
python gate.py rows.tsv --out build/clean.tsv --out-root build --snapshot snap.json
python gate.py rows.tsv --out build/clean.tsv --out-root build --snapshot snap.json --chembl
python gate.py rows.tsv --out build/clean.tsv --out-root build --snapshot snap.json --expect 940
python gate.py --list-checks
```

Exit status is 0 only when every check passed, the file was written, and it
was read back at the expected row count. On any finding nothing is written.

The snapshot is the accepted state of a previous run. Checks C3 and C7 compare
against it, so structure drift between runs is caught even when the current
rows are internally consistent. Write a new snapshot only from a run you have
accepted.

`--chembl` is off by default because it needs the network. It is the only
check that can see failure 3 above, so run it at least once per corpus.

## The checks

| | what it stops |
|---|---|
| C1 destination | the path you write is not the path you looked at |
| C2 formula against the source | the rebuilt structure is not the printed formula |
| C3 formula against a snapshot | a structure changed since the run you accepted |
| C4 stereocentres | the epimer was built, and the formula agreed |
| C5 duplicate structures | one molecule sitting under two labels in one series |
| C6 sequence collisions | one sequence resolving to two structures in one paper |
| C7 ring skeleton | atoms conserved, ring not |
| C8 double bond geometry | a geometry the paper drew, left unassigned or built the other way |
| C9 external cross-check | activities attached to the wrong member of a pair |
| C10 exact duplicates | the same measurement stored more than once |
| C11 label identity | a printed label treated as a chemical identity |
| C12 completeness | a row that was there last time has quietly gone missing |

C10, C11 and C12 are about counting rather than structure. C10 exists because a corpus that stores one measurement
once per substitution position will return hundreds of repeats at a ratio of
exactly 1.00, all of them one row copied. C11 exists because bare compound
numbers collide: in the corpus that produced this skill, of the twelve printed
labels appearing in two or more papers with a structure resolved in both,
twelve of twelve denoted more than one molecule. C12 exists because every
other check walks the rows that are present, so a row that was deleted between
runs is looked at by nobody and leaves the run green. It walks the other way,
from the accepted snapshot to what is here now.

## Verifying the checker itself

```bash
python selftest.py
```

False red is visible the moment it happens. False green is never visible. So
each check gets its own poisoned row, and the test asserts two things: that the
check fires on its poison, and that nothing fires on the clean set. If you
change a check, run this. A check that has never been seen to fail is not a
check.

The run counts, from the cases that actually ran, which checks a poison has
exercised, and prints the ones it has not. At present that is C9, which needs
the network. It is listed as untested rather than folded into the pass count,
because a summary line that implies full coverage is the same failure this
whole skill is about.

## Adapting it

The checks assume small molecules and peptides with SMILES available. If your
corpus has no structures, C2 through C8 and C11 have nothing to work with, and
what is left is C1, C10, C12 and whatever external check you can key on the
DOI. That is still worth wiring in, because those three are field-independent.
