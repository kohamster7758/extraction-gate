"""Fixtures for the duplicate check, including the one it got wrong.

The negative fixture is the point of this file. On 2026-09-17 the duplicate
check failed a table that was not corrupt: a projection that drops an identity
column repeats rows by construction, and a whole-row uniqueness test reads that
as corruption. The check was rewritten. This file keeps the case that caused it,
so an over-sensitive gate cannot come back and teach its operator to ignore it.

  distinctness is relative to a declared identity key
  a projection that omits an identity column is not necessarily corrupt

Mutation sensitivity is measured only after every native fixture agrees with
its expected exit. Each named mutant must kill the fixture it targets; skipped
mutants and an invalid baseline are reported separately from evaluated mutants.

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


def run_dir(name, build, want_exit, check=CHECK, quiet=False):
    """Hand the check a directory built by `build`, which may write nothing."""
    d = tempfile.mkdtemp(prefix="dupfix_")
    try:
        build(d)
        p = subprocess.run([sys.executable, check, "--dataset", d],
                           capture_output=True, text=True)
        ok = p.returncode == want_exit
        if not quiet:
            print("%-4s %-58s exit %d (wanted %d)" % ("ok" if ok else "RED", name,
                                                      p.returncode, want_exit))
            if not ok:
                print(p.stdout + p.stderr)
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_case(name, measurements, pairs, want_exit, check=CHECK, quiet=False):
    def build(d):
        write(os.path.join(d, "measurements.tsv"), MEAS_COLS, measurements)
        write(os.path.join(d, "pairs.tsv"), PAIR_COLS, pairs)
        write(os.path.join(d, "verification.tsv"), VERIF_COLS, project(measurements))
    return run_dir(name, build, want_exit, check, quiet)


# the parent is the reference at each position of a scan, so the projected table
# repeats it. Nothing here is a duplicate at the level of the measurement table.
scan = [meas("1", "parent", "T", "A-B"),
        meas("1", "parent", "T", "B-C"),
        meas("1", "parent", "T", "C-D"),
        meas("1", "analogue 1", "T", "A-B", unit="N_methyl", value="4.0"),
        meas("1", "analogue 2", "T", "B-C", unit="N_methyl", value="8.0")]
scan_pairs = [pair("1", "G", "A-B", "parent", "analogue 1", "T"),
              pair("1", "G", "B-C", "parent", "analogue 2", "T", fold="8.0")]

# Added 2026-09-21. The first four fixtures hand the check all three tables, which
# is why none of them could see the state the check was actually in: with no
# tables to read it printed PASS and returned 0. These two fixtures are the ones
# that fail if that ever comes back.
CASES = [
    (run_case, ("a projection that repeats rows is not corrupt", scan, scan_pairs, 0)),
    (run_case, ("an exact duplicate measurement row fails",
                scan + [meas("1", "analogue 1", "T", "A-B", unit="N_methyl", value="4.0")],
                scan_pairs, 1)),
    (run_case, ("an exact duplicate pair row fails",
                scan, scan_pairs + [pair("1", "G", "A-B", "parent", "analogue 1", "T")], 1)),
    (run_case, ("a clean set passes", scan, scan_pairs, 0)),
    (run_dir, ("no tables at all must not pass", lambda d: None, 2)),
    (run_dir, ("a header with no rows must not pass",
               lambda d: write(os.path.join(d, "pairs.tsv"), PAIR_COLS, []), 2)),
]

# Literal, newline-escaped replacements keep each change local. Target indices
# refer to CASES; the absent-table bug must be caught by both absence fixtures.
MUTANTS = [
    ("projection_repeats_rejected", "        if off:\n",
     "        if off or len(v) != len(vc):\n", (0,)),
    ("measurement_duplicates_ignored",
     '        failed += bool(show("measurements.tsv", m, ("pmid", "compound", "target", "position")))\n',
     '        show("measurements.tsv", m, ("pmid", "compound", "target", "position"))\n', (1,)),
    ("pair_duplicates_ignored",
     '        failed += bool(show("pairs.tsv", p, ("pmid", "group_id", "position", "cmpd_B", "target")))\n',
     '        show("pairs.tsv", p, ("pmid", "group_id", "position", "cmpd_B", "target"))\n', (2,)),
    ("missing_or_empty_tables_pass", "    if not read:\n", "    if False:\n", (4, 5)),
]


def run_checks(check, quiet=False):
    return [fn(*args, check=check, quiet=quiet) for fn, args in CASES]


def mutation_specs():
    return MUTANTS


def run_suite(check=CHECK, quiet=False, mutations=mutation_specs):
    native = run_checks(check, quiet)
    report = dict(checks_total=len(native), checks_passing=sum(native),
                  mutants_checked=0, mutants_skipped=0, mutants_na=len(MUTANTS),
                  mutation_evaluations=0, mutation_sensitivity="N/A",
                  state="INVALID_BASELINE")
    # Do not even construct mutants until all six native outcomes are accepted.
    if not all(native):
        return report
    report["mutants_na"] = 0
    with io.open(check, encoding="utf-8") as fh:
        source = fh.read()
    own_kills = 0
    with tempfile.TemporaryDirectory(prefix="dupmut_") as d:
        for name, old, new, targets in mutations():
            if source.count(old) != 1:
                report["mutants_skipped"] += 1
                if not quiet:
                    print("mutant: %r SKIPPED: anchor is absent or ambiguous" % name)
                continue
            changed = source.replace(old, new, 1)
            compile(changed, name, "exec")  # syntax errors are not mutant kills
            path = os.path.join(d, name + ".py")
            with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(changed)
            results = run_checks(path, quiet=True)
            report["mutants_checked"] += 1
            report["mutation_evaluations"] += len(results)
            hit = all(not results[i] for i in targets)
            own_kills += hit
            if not quiet:
                print("mutant: %r killed %d case(s); own_targets: %s" %
                      (name, results.count(False), "caught" if hit else "MISSED"))
    checked = report["mutants_checked"]
    if checked:
        report["mutation_sensitivity"] = "%d/%d" % (own_kills, checked)
    report["state"] = ("MUTATION_TEST_FAILED" if own_kills != checked else
                       "PASS_WITH_INCOMPLETE_MUTATION_COVERAGE" if report["mutants_skipped"] else
                       "PASS")
    return report


def baseline_guard_regression():
    with tempfile.TemporaryDirectory(prefix="dupbase_") as d:
        with io.open(CHECK, encoding="utf-8") as fh:
            source = fh.read()
        anchor = "        return 2\n"
        if source.count(anchor) != 1:
            raise AssertionError("broken-baseline regression needs one abstention return")
        broken = os.path.join(d, "broken.py")
        with io.open(broken, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(source.replace(anchor, "        return 0\n", 1))

        def forbidden_mutations():
            raise AssertionError("mutants were requested before the baseline passed")

        report = run_suite(broken, quiet=True, mutations=forbidden_mutations)
        if not (report["checks_passing"] == 4 and report["state"] == "INVALID_BASELINE"
                and report["mutation_evaluations"] == report["mutants_checked"] == 0
                and report["mutants_skipped"] == 0 and report["mutants_na"] == len(MUTANTS)
                and report["mutation_sensitivity"] == "N/A"):
            raise AssertionError("an invalid baseline produced mutation evidence: %r" % report)
    print("baseline_guard_regression: PASS (invalid baseline; evaluations 0; sensitivity N/A)")


if __name__ == "__main__":
    report = run_suite()
    if report["state"] != "INVALID_BASELINE":
        baseline_guard_regression()
    print("")
    for key, value in report.items():
        print("%s: %s" % (key, value))
    print("negative_fixture: a projection repeating rows must not fail")
    print("negative_fixture: an absent table must not read as a clean one")
    if report["state"] == "INVALID_BASELINE":
        sys.exit(1)
    sys.exit(0 if report["state"].startswith("PASS") else 1)
