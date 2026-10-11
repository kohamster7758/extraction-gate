# -*- coding: utf-8 -*-
"""Prove that every check can go red, and that a clean set goes green.

A checker that has never been seen to fail is not evidence of anything. False
red is visible the moment it happens. False green is never visible. So each
check here gets its own poisoned row, and the test asserts that the check
fires on it and that nothing fires on the clean set.

The clean set is the accepting baseline, and it is a precondition rather than
one case among the others. A check that fires on rows it should accept also
"catches" its own poison, so a coverage figure taken after a red baseline
cannot be trusted. If the baseline is red, no poison is run, no figure is
printed, and the run says INVALID_BASELINE.

A poison that its check does not catch is a BLIND_SPOT: it is named, and it is
not counted as a detection. Every fixture is CHECKED, SKIPPED or
NOT_APPLICABLE, and only a checked poison that its check caught counts as a
detection. A declared poison whose check has nothing to look at cannot pass
the run: it ends in REVIEW, as the ledger does for a source it cannot decide.

Usage:  python selftest.py [--receipt PATH]
"""
import argparse
import csv
import json
import re
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gate  # noqa: E402

INVALID_BASELINE = "INVALID_BASELINE"
BLIND_SPOT = "BLIND_SPOT"
CHECKED = "CHECKED"
SKIPPED = "SKIPPED"
NOT_APPLICABLE = "NOT_APPLICABLE"
NO_FIGURE = "No sensitivity figure was produced because the checker failed its accepting baseline."
NO_POISON_RAN = "No sensitivity figure was produced because no poison was run."
EXECUTED = {True: "executed", False: "not executed", None: "execution not observed"}
RECEIPT_VERSION = 0

COLS = ["row_id", "doi", "group", "label", "smiles", "formula_reported",
        "stereo_reported", "geometry_reported", "sequence",
        "target", "assay", "readout", "unit", "value"]

# (E) and (Z) butenoyl-alanine: same formula, different molecule.
E_ISOMER = "C/C=C/C(=O)N[C@@H](C)C(=O)O"
Z_ISOMER = "C/C=C\\C(=O)N[C@@H](C)C(=O)O"
NO_GEOM = "CC=CC(=O)N[C@@H](C)C(=O)O"
EPIMER = "C/C=C/C(=O)N[C@H](C)C(=O)O"
CYCLOHEXANE = "C1CCCCC1"
METHYLCYCLOPENTANE = "CC1CCCC1"


def row(**kw):
    r = {c: "" for c in COLS}
    r.update(kw)
    return r


def clean_rows():
    import gate as g
    e = g.mol_of(E_ISOMER)
    z = g.mol_of(Z_ISOMER)
    c6 = g.mol_of(CYCLOHEXANE)
    return [
        row(row_id="r1", doi="10.1000/a", group="S1", label="1", smiles=E_ISOMER,
            formula_reported=g.formula(e), stereo_reported=g.cip_string(e),
            geometry_reported="E", sequence="AA-1",
            target="T", assay="binding", readout="IC50", unit="nM", value="10"),
        row(row_id="r2", doi="10.1000/a", group="S1", label="2", smiles=Z_ISOMER,
            formula_reported=g.formula(z), stereo_reported=g.cip_string(z),
            geometry_reported="Z", sequence="AA-2",
            target="T", assay="binding", readout="IC50", unit="nM", value="250"),
        row(row_id="r3", doi="10.1000/b", group="S2", label="4", smiles=CYCLOHEXANE,
            formula_reported=g.formula(c6),
            target="T", assay="binding", readout="IC50", unit="nM", value="900"),
    ]


def write(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run(rows, tmp, snap=None, out_name="out.tsv", out_root=None):
    src = os.path.join(tmp, "rows.tsv")
    write(rows, src)
    loaded = gate.load(src)
    root = out_root or tmp
    fails, _ = gate.run_checks(loaded, os.path.join(tmp, out_name), root, snap)
    return fails


def clean_rows_loaded(tmp):
    """coverage() は gate.load() が付ける _mol を見るので、実際に読み込んで渡す。"""
    src = os.path.join(tmp, "_structure.tsv")
    write(clean_rows(), src)
    return gate.load(src)


def ids(fails):
    """Check ids only. Continuation lines are indented and carry no id."""
    out = set()
    for f in fails:
        m = re.match(r"^(C\d+)", f)
        if m:
            out.add(m.group(1))
    return out


def fired(got):
    return "fired: %s" % (",".join(sorted(got)) or "(none)")


def rows_for(cid, rows, tmp, snap=None):
    """(rows check `cid` can look at, rows in the fixture), from gate.coverage().

    A poison aimed at a check with nothing to look at cannot be seen by it, so
    that case is not applicable, and it is not a detection either way.
    """
    src = os.path.join(tmp, "_applies.tsv")
    write(rows, src)
    loaded = gate.load(src)
    for c, _name, k, t in gate.coverage(loaded, snap, False):
        if c == cid:
            return k, t
    return None, len(loaded)


def function_name(cid):
    """The name looked for in gate: check_ and the check's name in CHECKS."""
    name = dict((c, n) for c, n, _w in gate.CHECKS).get(cid, "")
    return "check_" + name.replace(" ", "_").replace("-", "_")


def check_function(cid):
    """The name of gate's function for check `cid`, found from CHECKS, or None.

    C9's function is check_chembl, which does not follow the naming, so for C9
    this is None and whether it ran is recorded as unknown rather than guessed.
    """
    fn = function_name(cid)
    return fn if callable(getattr(gate, fn, None)) else None


def run_watching(cid, rows, tmp, snap=None, **kw):
    """run(), with gate's function for `cid` wrapped to record whether it was called.

    Whether the detecting check executed is observed here, not assumed from the
    fact that the poison was run. Returns (fails, called); called is None when
    no function could be found for the check.
    """
    fn = check_function(cid)
    if fn is None:
        return run(rows, tmp, snap=snap, **kw), None
    real, calls = getattr(gate, fn), []

    def watched(*a, **k):
        calls.append(1)
        return real(*a, **k)

    setattr(gate, fn, watched)
    try:
        return run(rows, tmp, snap=snap, **kw), bool(calls)
    finally:
        setattr(gate, fn, real)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Watch every check go red, and a clean set stay green.")
    ap.add_argument("--receipt", help="write the result as JSON here, whatever the decision")
    a = ap.parse_args(argv)
    if a.receipt:
        if os.path.isdir(a.receipt) or a.receipt.endswith(("/", os.sep)):
            ap.error("--receipt names a directory, not a file: %s" % a.receipt)
        if not os.path.isdir(os.path.dirname(os.path.abspath(a.receipt))):
            ap.error("the directory for --receipt does not exist: %s" % a.receipt)
        # A receipt left by an earlier run must not outlive a run that crashes.
        if os.path.exists(a.receipt):
            os.remove(a.receipt)

    # The cases write their rows under a temporary directory, which goes
    # whatever happens to the run.
    tmp = tempfile.mkdtemp(prefix="extraction-gate-")
    try:
        return run_cases(a, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_cases(a, tmp):
    """Run the baseline and the poisons, print the result, and return the exit code."""

    def masked(lines):
        # The temporary directory belongs to this harness, not to the checks.
        # A Windows message may quote it with doubled backslashes or slashes.
        forms = (tmp.replace("\\", "\\\\"), tmp, tmp.replace("\\", "/"))
        out = []
        for x in lines:
            for form in forms:
                x = x.replace(form, "<tmp>")
            out.append(x)
        return out

    results = []
    fixtures = []

    # gate.py keeps three parallel lists by hand: CHECKS, the call sequence in
    # run_checks, and coverage(). If any of them drifts, the tool reports a
    # count that is not the count that ran. Assert they agree before anything
    # else, because every number below is stated against CHECKS.
    declared = [c[0] for c in gate.CHECKS]
    try:
        reported = [c[0] for c in gate.coverage(clean_rows_loaded(tmp), None, True)]
        results.append(("structure: CHECKS == coverage()", declared == reported,
                        sorted(set(declared) ^ set(reported)), []))
    except Exception as exc:
        # The clean set could not be loaded at all. The baseline below says so.
        results.append(("structure: CHECKS == coverage()", False, [],
                        masked(["raised %s: %s" % (type(exc).__name__, exc)])))

    # run_watching finds a check's function by the name CHECKS gives it. A name
    # that finds no function leaves every poison aimed at that check
    # unobserved, and a detection nobody saw is not a detection, so the name is
    # a failure stated here. C9 is the one exception: its function is
    # check_chembl, and it is skipped offline.
    unresolved = [c for c in declared if c != "C9" and check_function(c) is None]
    results.append(("structure: CHECKS name gate functions", not unresolved, unresolved,
                    ["%s: gate.%s is not a function" % (c, function_name(c)) for c in unresolved]))

    # green: nothing fires on a clean set. This is the accepting baseline, run
    # before any poison and unmodified: once as it is, and once against its own
    # accepted snapshot, so that the checks which only look at a snapshot (C3,
    # C7) have rows to look at as well. It is a precondition, not one more
    # case: a check that fires on rows it should accept also "catches" its own
    # poison, so nothing counted after a red baseline can be trusted. Accepted
    # means what it means to gate.py, no finding at all, not only no finding
    # that starts with a check id. A checker that raises on these rows has
    # failed them too.
    raised = None
    seen = {}
    try:
        fails = run(clean_rows(), tmp)
        loaded = clean_rows_loaded(tmp)
        own = gate.snapshot_of(loaded)
        fails = list(dict.fromkeys(fails + run(clean_rows(), tmp, snap=own)))
        seen = dict((c, k) for c, _n, k, _t in gate.coverage(loaded, own, False))
    except Exception as exc:
        raised = masked(["raised %s: %s" % (type(exc).__name__, exc)])[0]
        fails = [raised]
    got = ids(fails)
    baseline_ok = not fails
    if raised:
        actual = raised
    elif fails and not got:
        actual = "refused: %d finding(s), none with a check id" % len(fails)
    else:
        actual = fired(got)
    results.append(("clean", baseline_ok, sorted(got), masked(fails[:2])))
    fixtures.append(dict(fixture_id="clean", execution_state=CHECKED,
                         expected_result="nothing fires", actual_result=actual,
                         detecting_check=None, diagnostics=masked(fails),
                         baseline_rows=dict(sorted(seen.items()))))
    if not baseline_ok:
        fixtures[0]["reason"] = INVALID_BASELINE

    # A check counts as exercised only when one of its poisons was caught. A
    # poison that ran and was not caught is a blind spot, not coverage.
    exercised = set()

    def case(cid, rows, expect, snap=None, skip=None, **kw):
        rec = dict(fixture_id=cid, expected_result="%s fires" % expect,
                   detecting_check=expect, detecting_check_executed=False)
        fixtures.append(rec)
        if skip is None and not baseline_ok:
            skip = "the accepting baseline did not pass"
        if skip:
            rec.update(execution_state=SKIPPED, actual_result="not run", diagnostics=[skip])
            return None
        k, n = rows_for(expect, rows, tmp, snap)
        if not k:
            why = ("%s has nothing to look at in this fixture, 0 of %d rows" % (expect, n)
                   if k == 0 else "%s is not reported by gate.coverage()" % expect)
            rec.update(execution_state=NOT_APPLICABLE, actual_result="not run", diagnostics=[why])
            return None
        if not seen.get(expect):
            # The baseline never gave this check anything to accept, so a
            # detection here could not be told apart from a check that always fires.
            why = "%s had nothing to look at in the accepting baseline" % expect
            rec.update(execution_state=NOT_APPLICABLE, actual_result="not run", diagnostics=[why])
            return None
        fails, called = run_watching(expect, rows, tmp, snap=snap, **kw)
        got = ids(fails)
        # Caught means the declared check fired, and was seen to run. A check
        # whose function could not be found was not seen, and does not count.
        ok = expect in got and called is True
        rec.update(execution_state=CHECKED, actual_result=fired(got), diagnostics=masked(fails),
                   detecting_check_executed=called, detecting_check_rows=k, fixture_rows=n)
        if ok:
            exercised.add(expect)
        else:
            rec["reason"] = BLIND_SPOT
        results.append((cid, ok, sorted(got), masked(fails[:2])))
        return ok

    import gate as g

    # C1 destination outside the declared root
    case("C1", clean_rows(), "C1", out_root=os.path.join(tmp, "elsewhere"))

    # C2 formula the paper did not print
    r = clean_rows()
    r[0]["formula_reported"] = "C99H99NO9"
    case("C2", r, "C2")

    # C3 formula drift against an accepted snapshot
    r = clean_rows()
    snap = {"r1": {"formula": "C9H99NO3", "rings": g.ring_profile(g.mol_of(E_ISOMER))}}
    case("C3", r, "C3", snap=snap)

    # C4 the epimer built where the paper prints the other configuration
    r = clean_rows()
    r[0]["smiles"] = EPIMER
    case("C4", r, "C4")

    # C5 one structure under two labels in one series
    r = clean_rows()
    r.append(row(row_id="r4", doi="10.1000/a", group="S1", label="3", smiles=E_ISOMER))
    case("C5", r, "C5")

    # C6 one sequence resolving to two structures in one paper
    r = clean_rows()
    r[1]["sequence"] = "AA-1"
    case("C6", r, "C6")

    # C7 atoms conserved, ring not
    r = clean_rows()
    r[2]["smiles"] = METHYLCYCLOPENTANE
    r[2]["formula_reported"] = g.formula(g.mol_of(METHYLCYCLOPENTANE))
    snap = {"r3": {"formula": g.formula(g.mol_of(CYCLOHEXANE)),
                   "rings": g.ring_profile(g.mol_of(CYCLOHEXANE))}}
    case("C7", r, "C7", snap=snap)

    # C8 the paper draws a geometry and the structure leaves it unassigned
    r = clean_rows()
    r[0]["smiles"] = NO_GEOM
    case("C8", r, "C8")

    # C9 needs the network. Declared so that it is reported as skipped, with its
    # reason, instead of being absent from the run.
    case("C9", None, "C9", skip="needs the network, so it is not exercised offline")

    # C10 the same measurement stored twice
    r = clean_rows()
    d = dict(r[0])
    d["row_id"] = "r1b"
    r.append(d)
    case("C10", r, "C10")

    # C11 one printed label, two molecules, inside one report
    r = clean_rows()
    r.append(row(row_id="r4", doi="10.1000/a", group="S9", label="1", smiles=CYCLOHEXANE))
    case("C11", r, "C11")

    # C11 the same label meaning different things in different reports
    r = clean_rows()
    r.append(row(row_id="r5", doi="10.1000/c", group="S3", label="1", smiles=CYCLOHEXANE))
    case("C11-cross", r, "C11")

    # C12 a compound that was accepted last time has quietly gone missing.
    # Every other check walks the rows that are here, so nobody looks for it.
    r = [x for x in clean_rows() if x["row_id"] != "r2"]
    snap = {"r1": {}, "r2": {}, "r3": {}}
    case("C12-deleted", r, "C12", snap=snap)

    # C12 the same row_id twice
    r = clean_rows()
    d = dict(r[0])
    r.append(d)
    case("C12-duplicate-id", r, "C12")

    blind = [f for f in fixtures if f.get("reason") == BLIND_SPOT]
    poisons = [f for f in fixtures if f["detecting_check"]]
    executed = [f for f in poisons if f["execution_state"] == CHECKED]
    not_applicable = [f for f in poisons if f["execution_state"] == NOT_APPLICABLE]
    structure_ok = results[0][1] and results[1][1]
    # A figure needs an accepted baseline and at least one poison that ran.
    figure = baseline_ok and bool(executed)

    print()
    width = max(len(x) for x in [c for c, *_ in results] + [f["fixture_id"] for f in fixtures])
    bad = 0
    for cid, ok, got, sample in results:
        tag = "  " + BLIND_SPOT if any(f["fixture_id"] == cid for f in blind) else ""
        print("  %-7s %-14s %-*s  fired: %s%s" % ("PASS" if ok else "FAIL", CHECKED, width, cid,
                                                 ",".join(got) or "(none)", tag))
        if not ok:
            bad += 1
            for s in sample:
                print("          %s" % s)
    # A fixture that did not run has no PASS or FAIL. It keeps its state and its
    # reason, and it is not a detection.
    for f in fixtures:
        if f["execution_state"] != CHECKED:
            print("  %-7s %-14s %-*s  not run: %s" % ("", f["execution_state"], width,
                                                       f["fixture_id"], f["diagnostics"][0]))
    print()

    all_ids = [c[0] for c in gate.CHECKS]
    unexercised = [c for c in all_ids if c not in exercised]
    counts = []
    if not baseline_ok:
        # No poison ran, so there is no figure. A zero here would read as a
        # measurement of a checker that was never measured.
        base = fixtures[0]
        print("  %s: the accepting baseline did not pass" % INVALID_BASELINE)
        print("      baseline fixture: %s" % base["fixture_id"])
        print("      expected: %s" % base["expected_result"])
        print("      actual:   %s" % base["actual_result"])
        for d in base["diagnostics"]:
            print("      %s" % d)
        print("  " + NO_FIGURE)
    elif not executed:
        # The baseline was accepted and no poison ran, so there is nothing to
        # count. Every fixture listed above says why it did not run.
        print("  " + NO_POISON_RAN)
    else:
        print("  baseline: %s was accepted before any poison was run" % fixtures[0]["fixture_id"])
        print("  %d/%d cases" % (len(results) - bad, len(results)))

        # Which checks has a poison actually exercised? Counted from the cases that
        # ran, not from a list kept by hand, because a list kept by hand drifts.
        # A check is on this line when at least one of its poisons was caught.
        # C11 and C12 have two poisons each, so one of theirs can escape while
        # the check stays here; that escape is still reported below.
        print("  poison covers %d of %d checks: %s"
              % (len(exercised), len(all_ids), ",".join(i for i in all_ids if i in exercised)))
        if unexercised:
            # Declared, not assumed. A check nobody has watched fail is untested,
            # and saying so is better than a summary line that implies otherwise.
            print("  NO POISON EXERCISES: %s" % ",".join(unexercised))
            for cid in unexercised:
                why = []
                for f in poisons:
                    if f["detecting_check"] != cid:
                        continue
                    if f.get("reason") == BLIND_SPOT:
                        why.append("%s escaped: %s" % (f["fixture_id"], BLIND_SPOT))
                    elif f["execution_state"] == NOT_APPLICABLE:
                        why.append("%s: %s" % (NOT_APPLICABLE, f["diagnostics"][0]))
                    elif f["execution_state"] == SKIPPED:
                        why.append(f["diagnostics"][0])
                print("      %-4s %s" % (cid, "; ".join(why) or "no case yet"))

        # These count poisons; the coverage line above counts checks. A poison is
        # applicable when its check has rows to look at, decided just before it
        # runs, so applicable and executed are equal here. A skipped poison was
        # never found applicable or not, so it is counted apart, and neither it
        # nor a not-applicable one is a detection.
        counts = [
            ("applicable_mutations", len(executed)),
            ("executed_mutations", len(executed)),
            ("detected_mutations", len(executed) - len(blind)),
            ("escaped_mutations", len(blind)),
            ("skipped_mutations", sum(1 for f in poisons if f["execution_state"] == SKIPPED)),
            ("not_applicable_mutations", len(not_applicable)),
        ]
        for k, v in counts:
            print("  %s: %d" % (k, v))

        names = dict((c, n) for c, n, _w in gate.CHECKS)
        for f in blind:
            print("  %s %s" % (BLIND_SPOT, f["fixture_id"]))
            print("      expected: %s" % f["expected_result"])
            print("      actual:   %s" % f["actual_result"])
            print("      detecting check: %s %s, %s, %d of %d rows to look at"
                  % (f["detecting_check"], names.get(f["detecting_check"], ""),
                     EXECUTED[f["detecting_check_executed"]],
                     f["detecting_check_rows"], f["fixture_rows"]))
            print("      diagnostics:%s" % (" (none)" if not f["diagnostics"] else ""))
            for d in f["diagnostics"]:
                print("        %s" % d)

    # Precedence, as in the ledger: a red baseline outranks everything, because
    # no detection is interpretable after it; any failure outranks REVIEW; and a
    # run in which a declared poison turned out not applicable, or in which no
    # poison ran, is not a pass. A poison declared skipped, as C9 is offline, is
    # not held against the run.
    if not baseline_ok:
        decision, cause = "FAIL", INVALID_BASELINE
    elif blind:
        decision, cause = "FAIL", BLIND_SPOT
    elif not structure_ok:
        decision, cause = "FAIL", "structure_mismatch"
    elif not_applicable or not executed:
        decision, cause = "REVIEW", "unresolved"
    else:
        decision, cause = "PASS", "none"

    if decision == "FAIL" and baseline_ok:
        print("  a check that cannot be seen to fail is not a check")
    elif decision == "REVIEW":
        print("  REVIEW: nothing failed, and a declared poison could not be run against its check.")
    elif decision == "PASS":
        print("  every case behaved, and nothing fired on the clean set.")
        if unexercised:
            print("  the checks listed above are untested here, not passing.")

    if a.receipt:
        # Written whatever the decision. Without a figure it carries no counts
        # and no lists of what was caught, rather than zeros and empty lists.
        receipt = {
            "schema": "extraction-gate-selftest/v%d" % RECEIPT_VERSION,
            "schema_stability": "experimental",
            "decision": decision,
            "terminal_cause": cause,
            "baseline_fixture": fixtures[0]["fixture_id"],
            "baseline_accepted": baseline_ok,
            "structure_agrees": structure_ok,
            "sensitivity_reported": figure,
            "fixtures": fixtures,
        }
        if figure:
            receipt.update(counts)
            receipt["blind_spots"] = [f["fixture_id"] for f in blind]
            receipt["poison_covers"] = [i for i in all_ids if i in exercised]
            receipt["checks_not_exercised"] = unexercised
        with open(a.receipt, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(receipt, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print("  receipt -> %s" % a.receipt)
    return {"PASS": 0, "FAIL": 1, "REVIEW": 2}[decision]


if __name__ == "__main__":
    sys.exit(main())
