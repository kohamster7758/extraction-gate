"""Fixtures for the duplicate check, including the one it got wrong.

The negative fixture is the point of this file. On 2026-09-17 the duplicate
check failed a table that was not corrupt: a projection that drops an identity
column repeats rows by construction, and a whole-row uniqueness test reads that
as corruption. The check was rewritten. This file keeps the case that caused it,
so an over-sensitive gate cannot come back and teach its operator to ignore it.

  distinctness is relative to a declared identity key
  a projection that omits an identity column is not necessarily corrupt

Usage:  python selftest_duplicate_rows.py
"""
import csv, io, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "duplicate_rows.py")

MEAS_COLS = ["pmid", "compound", "target", "assay", "readout", "value_unit",
             "value", "bound", "position", "backbone_unit"]
PAIR_COLS = ["pmid", "group_id", "position", "cmpd_A", "cmpd_B", "target",
             "assay", "readout", "value_A", "value_B", "fold_B_over_A"]
VERIF_COLS = ["pmid", "compound", "target", "value", "unit", "status"]


def meas(pmid, compound, target, position, unit="amide", value="1.0"):
    return dict(zip(MEAS_COLS, [pmid, compound, target, "binding", "Ki", "nM",
                                value, "", position, unit]))


def pair(pmid, group, position, a, b, target, fold="2.0"):
    return dict(zip(PAIR_COLS, [pmid, group, position, a, b, target, "binding",
                                "Ki", "1.0", "2.0", fold]))


def write(path, cols, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def project(measurements):
    """What the verification table is: the measurement table without position."""
    out = []
    for r in measurements:
        out.append(dict(zip(VERIF_COLS, [r["pmid"], r["compound"], r["target"],
                                         r["value"], r["value_unit"], "FOUND"])))
    return out


def run_dir(name, build, want_exit):
    """Hand the check a directory built by `build`, which may write nothing."""
    d = tempfile.mkdtemp(prefix="dupfix_")
    try:
        build(d)
        p = subprocess.run([sys.executable, CHECK, "--dataset", d],
                           capture_output=True, text=True)
        ok = p.returncode == want_exit
        print("%-4s %-58s exit %d (wanted %d)" % ("ok" if ok else "RED", name,
                                                  p.returncode, want_exit))
        if not ok:
            print(p.stdout)
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_case(name, measurements, pairs, want_exit):
    d = tempfile.mkdtemp(prefix="dupfix_")
    try:
        write(os.path.join(d, "measurements.tsv"), MEAS_COLS, measurements)
        write(os.path.join(d, "pairs.tsv"), PAIR_COLS, pairs)
        write(os.path.join(d, "verification.tsv"), VERIF_COLS, project(measurements))
        p = subprocess.run([sys.executable, CHECK, "--dataset", d],
                           capture_output=True, text=True)
        ok = p.returncode == want_exit
        print("%-4s %-58s exit %d (wanted %d)" % ("ok" if ok else "RED", name,
                                                  p.returncode, want_exit))
        if not ok:
            print(p.stdout)
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


# the parent is the reference at each position of a scan, so the projected table
# repeats it. Nothing here is a duplicate at the level of the measurement table.
scan = [meas("1", "parent", "T", "A-B"),
        meas("1", "parent", "T", "B-C"),
        meas("1", "parent", "T", "C-D"),
        meas("1", "analogue 1", "T", "A-B", unit="N_methyl", value="4.0"),
        meas("1", "analogue 2", "T", "B-C", unit="N_methyl", value="8.0")]
scan_pairs = [pair("1", "G", "A-B", "parent", "analogue 1", "T"),
              pair("1", "G", "B-C", "parent", "analogue 2", "T", fold="8.0")]

results = []
results.append(run_case("a projection that repeats rows is not corrupt", scan, scan_pairs, 0))
results.append(run_case("an exact duplicate measurement row fails",
                        scan + [meas("1", "analogue 1", "T", "A-B", unit="N_methyl", value="4.0")],
                        scan_pairs, 1))
results.append(run_case("an exact duplicate pair row fails",
                        scan, scan_pairs + [pair("1", "G", "A-B", "parent", "analogue 1", "T")], 1))
results.append(run_case("a clean set passes", scan, scan_pairs, 0))

# Added 2026-09-21. Every fixture above hands the check all three tables, which
# is why none of them could see the state the check was actually in: with no
# tables to read it printed PASS and returned 0. These two fixtures are the ones
# that fail if that ever comes back.
results.append(run_dir("no tables at all must not pass", lambda d: None, 2))
results.append(run_dir("a header with no rows must not pass",
                       lambda d: write(os.path.join(d, "pairs.tsv"), PAIR_COLS, []), 2))

print("")
print("checks_total: %d" % len(results))
print("checks_passing: %d" % sum(1 for x in results if x))
print("negative_fixture: a projection repeating rows must not fail")
print("negative_fixture: an absent table must not read as a clean one")
sys.exit(0 if all(results) else 1)
