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

Usage:  python duplicate_rows.py [--dataset DIR]

Exit 0 when the tables that must be unique are unique, 1 otherwise.
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

    m = rows_of(here("measurements.tsv")) if os.path.exists(here("measurements.tsv")) else []
    if m:
        failed += bool(show("measurements.tsv", m, ("pmid", "compound", "target", "position")))
        key = lambda r: tuple(r.get(c, "") for c in VALUE_KEY)
        vals = len({key(r) for r in m})
        parents = [r for r in m if (r.get("backbone_unit") or "").strip() == "amide"]
        print("    distinct measured values %d of %d rows; the parent rows are %d and carry %d of them"
              % (vals, len(m), len(parents), len({key(r) for r in parents})))

    p = rows_of(here("pairs.tsv")) if os.path.exists(here("pairs.tsv")) else []
    if p:
        failed += bool(show("pairs.tsv", p, ("pmid", "group_id", "position", "cmpd_B", "target")))
        print("    a duplicated measurement row multiplies here: a pair is built per matching row")

    vpath = here("verification.tsv")
    if os.path.exists(vpath) and m:
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

    if failed:
        print("\nFAIL: a count taken from these tables is larger than the number of distinct records")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
