"""Refuse a table that holds the same row twice, and say how many values are real.

Found on 2026-09-17, and not by reading the table. Someone asked for the record
ids behind a published count, the key built for them collided seven ways, and
the reason was 208 rows of the paired table that are identical in every column.

An exact duplicate fails no check that looks at a row. It inflates counts while
leaving untouched every statistic that takes an extreme over a set, so the
arithmetic still closes and the count reported to a reader is wrong in one
direction only: too large.

Three levels are printed because they are three different numbers:

  rows              what the file holds
  distinct rows     after removing rows identical in every column
  distinct values   after removing rows that repeat one measured value, which
                    happens by design when a parent is the reference at each
                    position of a scan

The projected table (verification.tsv) is checked differently. It does not
carry the column that separates those parent rows, so repeats in it are a
projection and not a defect. It is verified against the measurement table
instead of for uniqueness. The first version of this script reported those
repeats as a failure, which was a false alarm, and the check was rewritten
after looking at what distinguished the rows upstream.

A table that is not there is the other way this check can be wrong, and it is
the way that does not announce itself. Until 2026-09-21 every block below was
guarded by os.path.exists, nothing else ran, and the script printed PASS and
returned 0. Run from its own directory, which is where the repository puts it,
it read no tables at all and reported that they were unique. An empty input had
resolved to zero duplicates instead of to nothing measured. So the absence of
the tables is now a third state: it is not a pass, and the caller is told which
tables were read.

Usage:  python duplicate_rows.py [--dataset DIR]

Exit 0 when the tables that must be unique were read and are unique, 1 when a
table holds the same row twice, 2 when there was nothing to check.
"""
import argparse, collections, csv, io, os, sys

VALUE_KEY = ("pmid", "compound", "target", "assay", "readout", "value", "value_unit", "bound")


def rows_of(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def exact_duplicates(rows):
    seen = collections.Counter(tuple(sorted(r.items())) for r in rows)
    return {k: v for k, v in seen.items() if v > 1}


def show(name, rows, label_cols):
    dups = exact_duplicates(rows)
    extra = sum(v - 1 for v in dups.values())
    print("%-18s rows %5d   distinct rows %5d   duplicate rows %4d" %
          (name, len(rows), len(rows) - extra, extra))
    for k, v in sorted(dups.items(), key=lambda kv: -kv[1])[:3]:
        d = dict(k)
        print("    x%-3d %s" % (v, " | ".join(d.get(c, "") for c in label_cols)))
    if dups:
        print("    multiplicity: %s" % dict(sorted(collections.Counter(dups.values()).items())))
    return extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=".", help="directory holding the tables")
    a = ap.parse_args()
    here = lambda n: os.path.join(a.dataset, n)
    failed = 0
    read, missing, empty = [], [], []

    for name in ("measurements.tsv", "pairs.tsv", "verification.tsv"):
        if not os.path.exists(here(name)):
            missing.append(name)
        elif not rows_of(here(name)):
            empty.append(name)
        else:
            read.append(name)

    m = rows_of(here("measurements.tsv")) if "measurements.tsv" in read else []
    if m:
        failed += bool(show("measurements.tsv", m, ("pmid", "compound", "target", "position")))
        key = lambda r: tuple(r.get(c, "") for c in VALUE_KEY)
        vals = len({key(r) for r in m})
        parents = [r for r in m if (r.get("backbone_unit") or "").strip() == "amide"]
        print("    distinct measured values %d of %d rows; the parent rows are %d and carry %d of them"
              % (vals, len(m), len(parents), len({key(r) for r in parents})))

    p = rows_of(here("pairs.tsv")) if "pairs.tsv" in read else []
    if p:
        failed += bool(show("pairs.tsv", p, ("pmid", "group_id", "position", "cmpd_B", "target")))
        print("    a duplicated measurement row multiplies here: a pair is built per matching row")

    vpath = here("verification.tsv")
    if "verification.tsv" in read and m:
        v = rows_of(vpath)
        proj = ("pmid", "compound", "target", "value", "unit")
        vc = collections.Counter(tuple(r.get(c, "") for c in proj) for r in v)
        mc = collections.Counter(tuple(r.get(c if c != "unit" else "value_unit", "") for c in proj) for r in m)
        off = [k for k in set(vc) | set(mc) if vc.get(k, 0) != mc.get(k, 0)]
        print("verification.tsv   rows %5d   projected groups %5d   rows off against measurements %4d"
              % (len(v), len(vc), len(off)))
        print("    repeats here are a projection: this table drops the position column")
        if off:
            failed += 1
            for k in off[:3]:
                print("    %s: verification %d, measurements %d" % (" | ".join(k), vc.get(k, 0), mc.get(k, 0)))

    print("")
    print("tables read      %s" % (", ".join(read) if read else "none"))
    if empty:
        print("tables empty     %s" % ", ".join(empty))
    if missing:
        print("tables missing   %s" % ", ".join(missing))

    if failed:
        print("\nFAIL: a count taken from these tables is larger than the number of distinct records")
        return 1
    if not read:
        print("\nABSTAIN: nothing was read, so nothing is known about uniqueness."
              "\n         Pass --dataset DIR. An absent table is not a clean one.")
        return 2
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
