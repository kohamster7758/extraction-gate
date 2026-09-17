"""Emit the exclusion ledger for the six-paper audit set.

The ledger is generated, not hand-typed, because a hand-typed TSV drifts a column
and nothing tells you. Every field here comes from the audit of 2026-09-09 plus a
recount of the corpus on 2026-09-14.

total_rows is deliberately empty where the row count was never recorded. An empty
denominator is not zero. The gate resolves it to `unavailable`.
"""
import io, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))

FIELDS = ["pmid", "source_table", "total_rows", "extracted", "excluded",
          "claim", "claimed_total_rows", "reason"]

ROWS = [
    # pmid, table, total, extracted, excluded, claim, claimed_total_rows, reason
    # claimed_total_rows is empty everywhere: no source in this set states a numeric total.
    # The column exists so that a disagreement between a stated total and the observed
    # one has somewhere to live instead of being resolved silently.
    ("16468724", "Table 1", "7", "7", "0", "complete", "", ""),
    ("22352868", "Table 1", "6", "6", "0", "complete", "", ""),
    ("19007202", "Table 2", "11", "7", "0", "", "",
     "rows 21, 22, 23 and 26 are in neither the corpus nor this ledger"),
    ("25247671", "Table 3", "6", "5", "0", "", "",
     "row 10c, the alpha-beta-unsaturated analogue, is in neither"),
    ("1323677", "Tables I and II", "", "7", "0", "complete", "",
     "read as complete; the row count was never written down"),
    ("1323677", "Tables III and IV", "0", "0", "0", "complete", "",
     "parent compounds only, no isostere present, nothing to take"),
    ("2405159", "activity tables", "", "8", "", "", "",
     "one representative per class was taken; the row count was never written down"),
]

out = os.path.join(HERE, "exclusions.tsv")
with io.open(out, "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, delimiter="\t", lineterminator="\n")
    w.writerow(FIELDS)
    for r in ROWS:
        assert len(r) == len(FIELDS), r
        w.writerow(r)

# read it back and check the shape, because writing is not the same as having written
with io.open(out, encoding="utf-8", newline="") as fh:
    back = list(csv.DictReader(fh, delimiter="\t"))
assert len(back) == len(ROWS), (len(back), len(ROWS))
for r in back:
    assert None not in r, r
    t = r["total_rows"]
    # an empty denominator is allowed and must stay empty; it must never read as 0
    assert t == "" or int(t) >= 0, r
    assert t != "0" or r["extracted"] == "0", r
n_empty = sum(1 for r in back if r["total_rows"] == "")
assert n_empty == 2, "expected 2 unrecorded denominators, got %d" % n_empty
print("wrote %s: %d source rows, %d fields" % (out, len(back), len(FIELDS)))
