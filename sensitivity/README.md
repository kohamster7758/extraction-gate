# sensitivity

Two scripts and the output they produced on 2026-09-17, for the thread on what a
published spread statistic depends on.

The corpus they read is not public until 1 November 2026. Until then these run
against a local copy and this directory carries the outputs, so the numbers can
be checked against the code that made them rather than against a note.

## duplicate_rows.py

Refuses a table that holds the same row twice, and prints three counts that are
three different numbers: rows, distinct rows, and distinct measured values. The
third one matters because a parent is the reference at every position of a scan,
so its value is carried once per position by design.

It found 53 rows of the measurement table that are identical in every column,
and 208 in the paired table, where one duplicated measurement row multiplies
because a pair is built per matching row. The counts in `out_20260917/` are
therefore reported at the distinct level.

The first version of this script also failed the projected table
(`verification.tsv`), which repeats rows because it does not carry the position
column. That was a false alarm. The check now verifies that table against the
measurement table instead of for uniqueness.

```
python duplicate_rows.py --dataset DIR
```

Exit 0 when the tables that must be unique were read and are unique, 1 when a
table holds the same row twice, 2 when there was nothing to read.

That third state was added on 2026-09-21, because until then there were only
two and the missing one was load-bearing. Each table was guarded by an
existence test, so a directory holding none of them ran no check at all and the
script printed `PASS` and returned 0. Run with no `--dataset`, which defaults to
the working directory and is the obvious thing to do after `cd sensitivity`, it
reported that tables it had never opened were unique. An empty input had
resolved to zero duplicates rather than to nothing measured.

The four fixtures in `selftest_duplicate_rows.py` could not see it: every one of
them wrote all three tables before calling the check, so the path where a table
is absent was never executed. Two fixtures now cover it, and the run prints
which tables it read.

## sensitivity_cuts.py

One statistic, the within-group spread, under three evidence policies and two
baselines. The policies are inclusive, group-clean (drop any group holding a
value a person transcribed from a scanned table) and measurement-filtered (drop
only those values, rebuild the groups, reapply the minimum-position
requirement). The baselines hold the position count constant, and draw the same
number of ratios from the pooled set to break the group structure.

```
python sensitivity_cuts.py --dataset DIR --gate amide_parent_gate:amide_parent_only --out OUT
```

`--gate` names the admissibility rule to apply first. Without it every pair in
the table is used, which is not the population any of the published numbers
were computed on.

The sampling is seeded (`--seed`, default 20260917) and the medians move by
under a percent between seeds.

The ratio column was renamed from `fold_B_over_A` to `fold_B_worse_than_A`,
with the values unchanged. Tables released under the old name stay as they
are, so the script reads either name and prints `ratio column:` with the one it
used. Until 2026-10-12 it read only the old name. On a table with the new name
it printed `0 with a ratio` for every row and then failed on an empty median,
and that count line was the one a caller would pick out of the output. A table
with neither name, or both, now exits 2 before any count is printed. A column
that is present with no values in it also exits 2, after saying so.
`selftest_sensitivity_cuts.py` runs the same fixture under each name and
checks that the two runs agree.

## out_20260917

`cuts.txt` and `duplicate_rows.txt` are the two runs. `groups_human_transcribed.tsv`
lists the groups holding at least one transcribed value, for both the two- and
four-position populations, and `pairs_dual_state.tsv` lists the pairs that are
censored and carry a second unresolved issue. Flag strings are verbatim from the
corpus, including one internal marker character.

## Licence

MIT. Takuya Kobayakawa, 2026.
