"""Fixtures for the ratio column of sensitivity_cuts.py, under both of its names.

The column was renamed from fold_B_over_A to fold_B_worse_than_A. Run against a
table with the new name, the script printed "0 with a ratio" for every row and
then failed on an empty median. The failure was loud, but the line before it was
a plausible count, and a caller reading the output for that line would have
taken zero as the answer.

  either name gives the same run, apart from the line naming the column
  a table with neither name, or both, prints no count at all
  a column that is present and empty is reported as such, which is a
  different thing from a column that is not there

Usage:  python selftest_sensitivity_cuts.py
"""
import csv, io, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CUTS = os.path.join(HERE, "sensitivity_cuts.py")
NEW, OLD = "fold_B_worse_than_A", "fold_B_over_A"
BASE = ["pmid", "group_id", "position", "cmpd_A", "cmpd_B", "target", "assay",
        "readout", "unit_B", "value_A", "value_B"]

# one group over four positions, one over two, and one row with no ratio
ROWS = [("1", "G1", "P1", "2.0"), ("1", "G1", "P2", "4.0"), ("1", "G1", "P3", "8.0"),
        ("1", "G1", "P4", "16.0"), ("2", "G2", "P1", "3.0"), ("2", "G2", "P2", "9.0"),
        ("2", "G2", "P3", "")]


def table(d, ratio_names, blank=False):
    cols = BASE + list(ratio_names) + ["flags"]
    with io.open(os.path.join(d, "pairs.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for pmid, g, pos, fold in ROWS:
            r = dict(zip(BASE, [pmid, g, pos, "parent", "analogue " + pos, "T", "binding",
                                "Ki", "N_methyl", "1.0", fold or "1.0"]))
            for c in ratio_names:
                r[c] = "" if blank else fold
            r["flags"] = ""
            w.writerow(r)


def run(ratio_names, blank=False):
    d = tempfile.mkdtemp(prefix="cutsfix_")
    try:
        table(d, ratio_names, blank)
        p = subprocess.run([sys.executable, CUTS, "--dataset", d, "--iters", "50"],
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def report(name, ok, rc, want, out, err):
    print("%-4s %-58s exit %d (wanted %d)" % ("ok" if ok else "RED", name, rc, want))
    if not ok:
        print(out)
        print(err)
    return ok


def without_column_line(out):
    return [x for x in out.splitlines() if not x.startswith("ratio column:")]


results = []

rc_n, out_n, err_n = run([NEW])
results.append(report("the new name is read", rc_n == 0
                      and "ratio column: %s" % NEW in out_n.splitlines()
                      and "  7 = 6 with a ratio + 1 without" in out_n.splitlines(),
                      rc_n, 0, out_n, err_n))

rc_o, out_o, err_o = run([OLD])
results.append(report("the old name is read, and the run is the same", rc_o == 0
                      and "ratio column: %s" % OLD in out_o.splitlines()
                      and without_column_line(out_o) == without_column_line(out_n),
                      rc_o, 0, out_o, err_o))

for name, cols in (("a table with neither name prints no count", []),
                   ("a table with both names prints no count", [NEW, OLD])):
    rc, out, err = run(cols)
    results.append(report(name, rc == 2 and not re.search(r"\d", out + err)
                          and "with a ratio" not in out, rc, 2, out, err))

rc, out, err = run([NEW], blank=True)
results.append(report("a present column with no values says so", rc == 2
                      and "ratio column: %s" % NEW in out.splitlines()
                      and "  7 = 0 with a ratio + 7 without" in out.splitlines()
                      and "Traceback" not in err, rc, 2, out, err))

print("")
print("checks_total: %d" % len(results))
print("checks_passing: %d" % sum(1 for x in results if x))
print("negative_fixture: a missing ratio column must not read as zero ratios")
sys.exit(0 if all(results) else 1)
