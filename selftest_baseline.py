# -*- coding: utf-8 -*-
"""Break the clean set and the checker on purpose, and watch selftest.py say so.

selftest.py counts a check as covered only after the clean set has been
accepted and one of the check's poisons has been caught. This file is the
evidence that it does. Most cases run selftest.main() in-process with one
controlled break, made in memory and undone afterwards; a few run selftest.py
as a script, to see its exit codes and its handling of --receipt. Each case
asserts what the run prints and what its receipt says.

Nothing in gate.py is weakened and no tracked file is changed.

  baseline broken    the clean set carries a formula the paper did not print
  checker broken     a check fires on every row, raises, or refuses without an id
  blind spot         a check never fires, fires the wrong way, or is never called
  not applicable     a check has no rows to look at, here or in the baseline
  structure drift    CHECKS and coverage() disagree
  receipt handling   a crash, a missing directory, a directory given as the path

Assertions are made against a reference run of the unbroken suite taken in the
same process, so adding a poison to selftest.py does not turn this file red.
Only the fixtures that existed when this file was written are named.

Passing the baseline establishes only that the verifier accepts the declared native valid fixture. It does not establish that every mutation will be detected.

Usage:  python selftest_baseline.py
"""
import contextlib
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gate  # noqa: E402
import selftest  # noqa: E402

COUNTS = ("applicable_mutations", "executed_mutations", "detected_mutations",
          "escaped_mutations", "skipped_mutations", "not_applicable_mutations")
FIELDS = ("fixture_id", "execution_state", "expected_result", "actual_result",
          "detecting_check", "diagnostics")
# The fixtures that existed when this file was written. More may be added.
PRE_EXISTING = ["clean", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10",
                "C11", "C11-cross", "C12-deleted", "C12-duplicate-id"]
PRE_EXISTING_COVERED = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C10", "C11", "C12"]
# A refused figure leaves exactly these keys in the receipt: no counts, no lists.
REFUSED_KEYS = {"schema", "schema_stability", "decision", "terminal_cause", "baseline_fixture",
                "baseline_accepted", "structure_agrees", "sensitivity_reported", "fixtures"}
C9_REASON = "needs the network, so it is not exercised offline"
INVALID_HEAD = "  INVALID_BASELINE: the accepting baseline did not pass"
REVIEW_LINE = "  REVIEW: nothing failed, and a declared poison could not be run against its check."
COVERS = re.compile(r"^  poison covers (\d+) of (\d+) checks: (\S*)$", re.M)


@contextlib.contextmanager
def replaced(module, name, value):
    old = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, old)


def run_selftest():
    """selftest.main() in-process: (exit code, what it printed, its receipt)."""
    d = tempfile.mkdtemp(prefix="baseline_")
    try:
        path = os.path.join(d, "receipt.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = selftest.main(["--receipt", path])
        with io.open(path, encoding="utf-8") as fh:
            receipt = json.load(fh)
        return code, buf.getvalue(), receipt
    finally:
        shutil.rmtree(d, ignore_errors=True)


_REFERENCE = []


def reference():
    """The receipt of the unbroken suite, taken once."""
    if not _REFERENCE:
        _REFERENCE.append(run_selftest()[2])
    return _REFERENCE[0]


def poisons(receipt):
    return [f for f in receipt["fixtures"] if f["detecting_check"]]


def by_id(receipt):
    return dict((f["fixture_id"], f) for f in receipt["fixtures"])


def block(out, first):
    """The line `first` and the indented lines that follow it."""
    lines = out.splitlines()
    if first not in lines:
        return []
    i = lines.index(first)
    j = i + 1
    while j < len(lines) and lines[j].startswith("      "):
        j += 1
    return lines[i:j]


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def schema(rc, bad):
    """Every fixture carries the six fields with values, and no local temp path."""
    ids_ = [f.get("fixture_id") for f in rc["fixtures"]]
    it = iter(ids_)
    if not all(x in it for x in PRE_EXISTING):
        bad.append("the pre-existing fixtures are not all there, in order: %r" % ids_)
    if rc["baseline_fixture"] != "clean":
        bad.append("baseline_fixture is %r" % rc["baseline_fixture"])
    for f in rc["fixtures"]:
        missing = [k for k in FIELDS if k not in f]
        empty = [k for k in FIELDS if k in f and f[k] is None
                 and not (k == "detecting_check" and f["fixture_id"] == "clean")]
        if missing or empty:
            bad.append("%s lacks %s" % (f.get("fixture_id"), ",".join(missing + empty)))
            continue
        if f["execution_state"] not in (selftest.CHECKED, selftest.SKIPPED,
                                         selftest.NOT_APPLICABLE):
            bad.append("%s has state %r" % (f["fixture_id"], f["execution_state"]))
        if f["execution_state"] != selftest.CHECKED and not f["diagnostics"]:
            bad.append("%s did not run and gives no reason" % f["fixture_id"])
        if f["fixture_id"] != "clean" and not f["expected_result"]:
            bad.append("%s names no expectation" % f["fixture_id"])
    root = tempfile.gettempdir()
    forms = {root, root.replace("\\", "/"), root.replace("\\", "\\\\")}
    if any(form in x for x in strings(rc) for form in forms):
        bad.append("the receipt carries the local temp path")


def arithmetic(rc, bad):
    """The counts behind a figure agree with the fixtures they were taken from."""
    ps = poisons(rc)
    checked = [f for f in ps if f["execution_state"] == selftest.CHECKED]
    escaped = [f for f in checked if f.get("reason") == selftest.BLIND_SPOT]
    state = lambda s: sum(1 for f in ps if f["execution_state"] == s)  # noqa: E731
    want = dict(applicable_mutations=len(checked), executed_mutations=len(checked),
                detected_mutations=len(checked) - len(escaped),
                escaped_mutations=len(escaped), skipped_mutations=state(selftest.SKIPPED),
                not_applicable_mutations=state(selftest.NOT_APPLICABLE))
    for k, v in want.items():
        if rc.get(k) != v:
            bad.append("%s is %r, the fixtures say %d" % (k, rc.get(k), v))
    if rc["executed_mutations"] + rc["skipped_mutations"] + rc["not_applicable_mutations"] \
            != len(ps):
        bad.append("executed + skipped + not applicable is not every poison")
    if rc["blind_spots"] != [f["fixture_id"] for f in escaped]:
        bad.append("blind_spots %r does not list every escape" % rc["blind_spots"])


def printed(out, rc, bad):
    """The counts and the coverage line printed are the ones in the receipt."""
    lines = out.splitlines()
    for k in COUNTS:
        if "  %s: %d" % (k, rc[k]) not in lines:
            bad.append("%s is not printed as in the receipt" % k)
    m = COVERS.search(out)
    if not m or int(m.group(1)) != len(rc["poison_covers"]) \
            or int(m.group(2)) != len(gate.CHECKS) \
            or m.group(3).split(",") != rc["poison_covers"]:
        bad.append("the coverage line does not match the receipt")


def no_figure(out, rc, bad, refusal):
    """A refused figure is absent, not zero: no count, no ratio, no list of what was caught."""
    if set(rc) != REFUSED_KEYS:
        bad.append("the receipt carries %s" % sorted(set(rc) ^ REFUSED_KEYS))
    if rc["sensitivity_reported"] is not False:
        bad.append("sensitivity_reported is %r" % rc["sensitivity_reported"])
    lines = out.splitlines()
    if "  " + refusal not in lines:
        bad.append("the refusal is not printed: %s" % refusal)
    else:
        after = lines[lines.index("  " + refusal):]
        if any(re.search(r"\d", x) for x in after if not x.startswith("  receipt -> ")):
            bad.append("a number is printed after the refusal")
    if COVERS.search(out) or re.search(r"_mutations: \d", out) or "%" in out \
            or re.search(r"\d+/\d+ cases", out) or "NO POISON EXERCISES" in out:
        bad.append("a figure, count or ratio was printed")


def not_run(rc, bad):
    for f in poisons(rc):
        if f["execution_state"] == selftest.CHECKED or f["detecting_check_executed"]:
            bad.append("%s was run" % f["fixture_id"])


def outcome(code, rc, want, bad):
    got = (code, rc["decision"], rc["terminal_cause"])
    if got != want:
        bad.append("exit %s, %s / %s; wanted %s" % (got + (want,)))


def baseline_accepted():
    code, out, rc = run_selftest()
    bad = []
    schema(rc, bad)
    arithmetic(rc, bad)
    printed(out, rc, bad)
    outcome(code, rc, (0, "PASS", "none"), bad)
    clean = by_id(rc)["clean"]
    if (clean["execution_state"], clean["actual_result"]) != (selftest.CHECKED, "fired: (none)"):
        bad.append("the clean set did not run and stay green")
    if not rc["baseline_accepted"] or \
            "  baseline: clean was accepted before any poison was run" not in out:
        bad.append("the accepted baseline is not visible")
    looked = clean["baseline_rows"]
    if [c for c, _n, _w in gate.CHECKS if c != "C9" and not looked.get(c)]:
        bad.append("the baseline gave a check nothing to look at: %r" % looked)
    if not all(c in rc["poison_covers"] for c in PRE_EXISTING_COVERED):
        bad.append("a pre-existing check is no longer covered: %r" % rc["poison_covers"])
    if not re.search(r"^  (\d+)/\1 cases$", out, re.M):
        bad.append("not every case behaved")
    checked = [f for f in poisons(rc) if f["execution_state"] == selftest.CHECKED]
    if [f["fixture_id"] for f in poisons(rc) if f["execution_state"] != selftest.CHECKED] != ["C9"]:
        bad.append("a poison other than C9 did not stay checked")
    for f in checked:
        if f["detecting_check_executed"] is not True or \
                not any(d.startswith(f["detecting_check"]) for d in f["diagnostics"]):
            bad.append("%s's detection is not backed by its check's output" % f["fixture_id"])
    if sum("<tmp>" in d for d in by_id(rc)["C1"]["diagnostics"][0].split()) != 2:
        bad.append("the temp paths in C1's diagnostic are not masked")
    if rc["blind_spots"] or selftest.INVALID_BASELINE in out or selftest.BLIND_SPOT in out:
        bad.append("a clean run reports a defect")
    return bad, out


def baseline_broken():
    real = selftest.clean_rows

    def broken():
        rows = real()
        rows[2]["formula_reported"] = "C99H99"
        return rows

    with replaced(selftest, "clean_rows", broken):
        code, out, rc = run_selftest()
    bad = []
    schema(rc, bad)
    no_figure(out, rc, bad, selftest.NO_FIGURE)
    not_run(rc, bad)
    outcome(code, rc, (1, "FAIL", selftest.INVALID_BASELINE), bad)
    clean = by_id(rc)["clean"]
    want = [INVALID_HEAD, "      baseline fixture: clean", "      expected: nothing fires",
            "      actual:   fired: C2"] + ["      " + d for d in clean["diagnostics"]]
    if block(out, INVALID_HEAD) != want:
        bad.append("the INVALID_BASELINE block is not %r" % want)
    if not any(d.startswith("C2 r3:") for d in clean["diagnostics"]):
        bad.append("the diagnostic does not name the broken row")
    if clean.get("reason") != selftest.INVALID_BASELINE or rc["baseline_accepted"] is not False:
        bad.append("the baseline fixture is not marked INVALID_BASELINE")
    for f in poisons(rc):
        why = C9_REASON if f["fixture_id"] == "C9" else "the accepting baseline did not pass"
        if f["execution_state"] != selftest.SKIPPED or f["diagnostics"] != [why]:
            bad.append("%s is %s with %r" % (f["fixture_id"], f["execution_state"],
                                            f["diagnostics"]))
    return bad, out


def checker_overfires():
    def always(rows):
        return ["C2 %s: fires on every row" % r["row_id"] for r in rows]

    with replaced(gate, "check_formula_vs_source", always):
        code, out, rc = run_selftest()
    bad = []
    no_figure(out, rc, bad, selftest.NO_FIGURE)
    not_run(rc, bad)
    outcome(code, rc, (1, "FAIL", selftest.INVALID_BASELINE), bad)
    diags = ["C2 r%d: fires on every row" % i for i in (1, 2, 3)]
    if by_id(rc)["clean"]["diagnostics"] != diags or \
            block(out, INVALID_HEAD)[4:] != ["      " + d for d in diags]:
        bad.append("the baseline diagnostics are not all shown")
    return bad, out


def snapshot_check_overfires():
    # C3 looks only at a snapshot. The baseline runs the clean set against its
    # own accepted snapshot, so a C3 that fires on anything is caught there.
    def whenever_there_is_a_snapshot(rows, snap):
        return ["C3 %s: fires on any snapshot" % r["row_id"] for r in rows] if snap else []

    with replaced(gate, "check_formula_vs_snapshot", whenever_there_is_a_snapshot):
        code, out, rc = run_selftest()
    bad = []
    no_figure(out, rc, bad, selftest.NO_FIGURE)
    outcome(code, rc, (1, "FAIL", selftest.INVALID_BASELINE), bad)
    if by_id(rc)["clean"]["actual_result"] != "fired: C3":
        bad.append("the baseline did not see C3 fire")
    return bad, out


def refused_without_an_id():
    # gate.py refuses the write on any finding, with or without a check id.
    real = gate.check_label_identity

    def with_a_bare_line(rows):
        return real(rows) + ["      a finding that carries no check id"]

    with replaced(gate, "check_label_identity", with_a_bare_line):
        code, out, rc = run_selftest()
    bad = []
    no_figure(out, rc, bad, selftest.NO_FIGURE)
    outcome(code, rc, (1, "FAIL", selftest.INVALID_BASELINE), bad)
    if by_id(rc)["clean"]["actual_result"] != "refused: 1 finding(s), none with a check id":
        bad.append("the refusal is not recorded: %r" % by_id(rc)["clean"]["actual_result"])
    return bad, out


def baseline_raises():
    def boom(rows):
        raise ValueError("boom")

    with replaced(gate, "check_formula_vs_source", boom):
        code, out, rc = run_selftest()
    bad = []
    schema(rc, bad)
    no_figure(out, rc, bad, selftest.NO_FIGURE)
    outcome(code, rc, (1, "FAIL", selftest.INVALID_BASELINE), bad)
    clean = by_id(rc)["clean"]
    if (clean["actual_result"], clean["diagnostics"]) != \
            ("raised ValueError: boom", ["raised ValueError: boom"]):
        bad.append("the raise is not recorded as the baseline's result: %r" % clean)
    if "      actual:   raised ValueError: boom" not in out.splitlines():
        bad.append("the raise is not shown")
    return bad, out


def load_raises():
    # gate.load failing on the clean set fails the baseline; it does not crash
    # the run before the baseline is recorded.
    def boom(path):
        raise OSError("cannot read %s" % path)

    with replaced(gate, "load", boom):
        code, out, rc = run_selftest()
    bad = []
    schema(rc, bad)
    no_figure(out, rc, bad, selftest.NO_FIGURE)
    outcome(code, rc, (1, "FAIL", selftest.INVALID_BASELINE), bad)
    if not by_id(rc)["clean"]["actual_result"].startswith("raised OSError: cannot read <tmp>"):
        bad.append("the raise is not recorded, masked: %r" % by_id(rc)["clean"]["actual_result"])
    return bad, out


def blind_spot():
    ref = reference()
    with replaced(gate, "check_stereocentres", lambda rows: []):
        code, out, rc = run_selftest()
    bad = []
    schema(rc, bad)
    arithmetic(rc, bad)
    printed(out, rc, bad)
    outcome(code, rc, (1, "FAIL", selftest.BLIND_SPOT), bad)
    c4 = by_id(rc)["C4"]
    if (c4.get("reason"), c4["execution_state"], c4["expected_result"], c4["actual_result"],
            c4["detecting_check"], c4["detecting_check_executed"]) != \
            (selftest.BLIND_SPOT, selftest.CHECKED, "C4 fires", "fired: (none)", "C4", True):
        bad.append("the C4 fixture is not a checked, executed blind spot: %r" % c4)
    if not re.search(r"^  FAIL\s+CHECKED\s+C4\s+fired: \(none\)  BLIND_SPOT$", out, re.M):
        bad.append("the C4 line is not marked BLIND_SPOT")
    want = ["  BLIND_SPOT C4", "      expected: C4 fires", "      actual:   fired: (none)",
            "      detecting check: C4 stereocentres, executed, %d of %d rows to look at"
            % (c4["detecting_check_rows"], c4["fixture_rows"]),
            "      diagnostics: (none)"]
    if block(out, "  BLIND_SPOT C4") != want:
        bad.append("the BLIND_SPOT block is %r" % block(out, "  BLIND_SPOT C4"))
    if rc["poison_covers"] != [c for c in ref["poison_covers"] if c != "C4"]:
        bad.append("the escaped poison is counted as coverage")
    if (rc["blind_spots"], rc["detected_mutations"]) != (["C4"], ref["detected_mutations"] - 1):
        bad.append("the escaped poison is counted as detected")
    if "      C4   C4 escaped: BLIND_SPOT" not in out.splitlines():
        bad.append("NO POISON EXERCISES does not say why C4 is there")
    return bad, out


def two_blind_spots():
    with replaced(gate, "check_stereocentres", lambda rows: []), \
            replaced(gate, "check_double_bond_geometry", lambda rows: []):
        code, out, rc = run_selftest()
    bad = []
    arithmetic(rc, bad)
    if (code, rc["blind_spots"], rc["escaped_mutations"]) != (1, ["C4", "C8"], 2):
        bad.append("exit %s, %s, %s" % (code, rc["blind_spots"], rc["escaped_mutations"]))
    for cid in ("C4", "C8"):
        if len(block(out, "  BLIND_SPOT " + cid)) != 5:
            bad.append("no full BLIND_SPOT block for %s" % cid)
    return bad, out


def wrong_check_fires():
    # C12-duplicate-id also trips C10. With C12 silenced on duplicate ids the
    # poison still makes something fire, but not the check it was written for.
    real = gate.check_completeness

    def no_duplicate_ids(rows, snap, expect=None):
        return [f for f in real(rows, snap, expect) if "not unique" not in f]

    with replaced(gate, "check_completeness", no_duplicate_ids):
        code, out, rc = run_selftest()
    bad = []
    arithmetic(rc, bad)
    f = by_id(rc)["C12-duplicate-id"]
    if (code, rc["blind_spots"]) != (1, ["C12-duplicate-id"]):
        bad.append("exit %s, %s" % (code, rc["blind_spots"]))
    if (f.get("reason"), f["actual_result"]) != (selftest.BLIND_SPOT, "fired: C10"):
        bad.append("a poison that fired another check counted as caught: %r" % f)
    # C12 stays on the coverage line, because its other poison was caught.
    if "C12" not in rc["poison_covers"] or by_id(rc)["C12-deleted"].get("reason"):
        bad.append("C12-deleted was not caught")
    return bad, out


def swapped_during_run_checks(replacement):
    """A run_checks that calls `replacement` in C4's place, not the registered C4."""
    real = gate.run_checks

    def run_checks(*a, **k):
        registered = gate.check_stereocentres
        gate.check_stereocentres = replacement
        try:
            return real(*a, **k)
        finally:
            gate.check_stereocentres = registered

    return run_checks


def check_not_called():
    # The drift the structure case cannot see: run_checks stops calling C4.
    with replaced(gate, "run_checks", swapped_during_run_checks(lambda rows: [])):
        code, out, rc = run_selftest()
    bad = []
    c4 = by_id(rc)["C4"]
    if (code, c4.get("reason"), c4["detecting_check_executed"]) != (1, selftest.BLIND_SPOT, False):
        bad.append("exit %s, %r" % (code, c4))
    if not any(x.startswith("      detecting check: C4 stereocentres, not executed,")
               for x in out.splitlines()):
        bad.append("the report does not say C4 never ran")
    return bad, out


def fired_but_not_called():
    # C4 findings appear, but not from the function registered for C4, so the
    # poison was not caught by the declared check.
    with replaced(gate, "run_checks", swapped_during_run_checks(gate.check_stereocentres)):
        code, out, rc = run_selftest()
    bad = []
    c4 = by_id(rc)["C4"]
    if (code, c4.get("reason"), c4["actual_result"], c4["detecting_check_executed"]) != \
            (1, selftest.BLIND_SPOT, "fired: C4", False):
        bad.append("a detection without the declared check counted: exit %s, %r" % (code, c4))
    if "C4" in rc["poison_covers"]:
        bad.append("C4 is on the coverage line")
    return bad, out


def fixture_states():
    ref = reference()
    real = gate.coverage

    def c8_has_nothing(rows, snap, chembl):
        return [(c, n, 0 if c == "C8" else k, t) for c, n, k, t in real(rows, snap, chembl)]

    with replaced(gate, "coverage", c8_has_nothing):
        code, out, rc = run_selftest()
    bad = []
    schema(rc, bad)
    arithmetic(rc, bad)
    printed(out, rc, bad)
    fx = by_id(rc)
    states = dict((f["fixture_id"], f["execution_state"]) for f in poisons(rc))
    if states.pop("C8") != selftest.NOT_APPLICABLE or states.pop("C9") != selftest.SKIPPED:
        bad.append("C8 or C9 lost its state")
    if set(states.values()) != {selftest.CHECKED}:
        bad.append("a checked fixture did not stay checked: %r" % states)
    c8_why = "C8 has nothing to look at in this fixture, 0 of 3 rows"
    if fx["C8"]["diagnostics"] != [c8_why] or fx["C9"]["diagnostics"] != [C9_REASON]:
        bad.append("a reason was lost")
    lines = out.splitlines()
    if not re.search(r"^\s+NOT_APPLICABLE\s+C8\s+not run: " + c8_why, out, re.M) or \
            not re.search(r"^\s+SKIPPED\s+C9\s+not run: " + C9_REASON, out, re.M):
        bad.append("a state or its reason is not printed")
    if "      C8   NOT_APPLICABLE: " + c8_why not in lines:
        bad.append("NO POISON EXERCISES does not say why C8 is there")
    if any("reason" in fx[i] or fx[i]["detecting_check_executed"] for i in ("C8", "C9")):
        bad.append("a fixture that did not run is marked as executed or failed")
    if (rc["applicable_mutations"], rc["executed_mutations"], rc["not_applicable_mutations"]) \
            != (ref["applicable_mutations"] - 1, ref["executed_mutations"] - 1, 1):
        bad.append("the denominator includes a fixture that did not run")
    if "C8" in rc["poison_covers"] or "C9" in rc["poison_covers"]:
        bad.append("a fixture that did not run is counted as coverage")
    # A declared poison that its check cannot see does not pass the run.
    outcome(code, rc, (2, "REVIEW", "unresolved"), bad)
    if REVIEW_LINE not in lines:
        bad.append("the REVIEW line is not printed")
    return bad, out


def unbacked_by_the_baseline():
    # C5 is given nothing to look at in the three-row clean set only. Its
    # four-row poison could still fire, but nothing shows C5 would have stayed
    # quiet on rows it should accept, so the detection is not counted.
    real = gate.coverage

    def c5_blind_on_clean(rows, snap, chembl):
        return [(c, n, 0 if c == "C5" and len(rows) == 3 else k, t)
                for c, n, k, t in real(rows, snap, chembl)]

    with replaced(gate, "coverage", c5_blind_on_clean):
        code, out, rc = run_selftest()
    bad = []
    arithmetic(rc, bad)
    c5 = by_id(rc)["C5"]
    if (c5["execution_state"], c5["diagnostics"]) != \
            (selftest.NOT_APPLICABLE, ["C5 had nothing to look at in the accepting baseline"]):
        bad.append("an unbacked detection was counted: %r" % c5)
    outcome(code, rc, (2, "REVIEW", "unresolved"), bad)
    return bad, out


def nothing_ran():
    real = gate.coverage

    def nothing_to_look_at(rows, snap, chembl):
        return [(c, n, 0, t) for c, n, k, t in real(rows, snap, chembl)]

    with replaced(gate, "coverage", nothing_to_look_at):
        code, out, rc = run_selftest()
    bad = []
    no_figure(out, rc, bad, selftest.NO_POISON_RAN)
    not_run(rc, bad)
    outcome(code, rc, (2, "REVIEW", "unresolved"), bad)
    if rc["baseline_accepted"] is not True or "every case behaved" in out:
        bad.append("a run that ran no poison says every case behaved")
    return bad, out


def structure_drift():
    with replaced(gate, "CHECKS", gate.CHECKS + [("C13", "phantom", "declared, never wired in")]):
        code, out, rc = run_selftest()
    bad = []
    arithmetic(rc, bad)
    outcome(code, rc, (1, "FAIL", "structure_mismatch"), bad)
    if rc["structure_agrees"] is not False:
        bad.append("structure_agrees is %r" % rc["structure_agrees"])
    if not re.search(r"^  FAIL\s+CHECKED\s+structure: CHECKS == coverage\(\)\s+fired: C13$",
                     out, re.M):
        bad.append("the structure line does not fail")
    return bad, out


def coverage_drops_a_check():
    # coverage() stops reporting C8. The lists no longer agree, which is a
    # failure and outranks the REVIEW that the unrun C8 poison would give.
    real = gate.coverage

    def without_c8(rows, snap, chembl):
        return [x for x in real(rows, snap, chembl) if x[0] != "C8"]

    with replaced(gate, "coverage", without_c8):
        code, out, rc = run_selftest()
    bad = []
    outcome(code, rc, (1, "FAIL", "structure_mismatch"), bad)
    c8 = by_id(rc)["C8"]
    if (c8["execution_state"], c8["diagnostics"]) != \
            (selftest.NOT_APPLICABLE, ["C8 is not reported by gate.coverage()"]):
        bad.append("C8 is %r" % c8)
    if not re.search(r"^\s+NOT_APPLICABLE\s+C8\s+not run: C8 is not reported", out, re.M):
        bad.append("the C8 line is not printed")
    return bad, out


def leaked():
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "extraction-gate-*")))


def crash_leaves_nothing_behind():
    d = tempfile.mkdtemp(prefix="baseline_")
    real = gate.check_label_identity

    def boom(rows):
        if len(rows) > 3:  # the clean set has three rows; some poisons have four
            raise RuntimeError("boom")
        return real(rows)

    try:
        path = os.path.join(d, "receipt.json")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write('{"decision": "PASS"}\n')
        before, raised = leaked(), None
        with replaced(gate, "check_label_identity", boom), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                selftest.main(["--receipt", path])
            except RuntimeError as exc:
                raised = exc
        bad = []
        if raised is None:
            bad.append("the crash did not propagate")
        if os.path.exists(path):
            bad.append("a receipt from an earlier run outlived a crash")
        if leaked() - before:
            bad.append("the crash left its temporary directory behind")
        return bad, ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


def script(args, driver=None):
    head = ["-c", driver] if driver else [os.path.join(HERE, "selftest.py")]
    return subprocess.run([sys.executable] + head + args, capture_output=True, text=True,
                          cwd=HERE)


def as_a_script():
    d = tempfile.mkdtemp(prefix="baseline_")
    try:
        path = os.path.join(d, "receipt.json")
        p = script(["--receipt", path])
        bad = []
        if p.returncode != 0:
            bad.append("exit %d" % p.returncode)
        else:
            with io.open(path, encoding="utf-8") as fh:
                if json.load(fh)["decision"] != "PASS":
                    bad.append("the receipt does not say PASS")
        return bad, p.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def as_a_script_red():
    # selftest.py run as __main__, with the checker broken before it starts.
    d = tempfile.mkdtemp(prefix="baseline_")
    try:
        path = os.path.join(d, "receipt.json")
        driver = ("import runpy, sys; sys.path.insert(0, %r); import gate; "
                  "gate.check_formula_vs_source = "
                  "lambda rows: ['C2 %%s: fires' %% r['row_id'] for r in rows]; "
                  "sys.argv = ['selftest.py', '--receipt', %r]; "
                  "runpy.run_path(%r, run_name='__main__')"
                  % (HERE, path, os.path.join(HERE, "selftest.py")))
        p = script([], driver)
        bad = []
        if p.returncode != 1:
            bad.append("exit %d" % p.returncode)
        elif not os.path.exists(path):
            bad.append("no receipt")
        else:
            with io.open(path, encoding="utf-8") as fh:
                if json.load(fh)["terminal_cause"] != selftest.INVALID_BASELINE:
                    bad.append("the receipt does not say INVALID_BASELINE")
        return bad, p.stdout + p.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def receipt_paths_refused():
    d = tempfile.mkdtemp(prefix="baseline_")
    try:
        bad, text = [], ""
        for path, why in ((os.path.join(d, "no", "such", "receipt.json"), "does not exist"),
                          (d, "names a directory"),
                          (os.path.join(d, "sub") + os.sep, "names a directory")):
            p = script(["--receipt", path])
            text += p.stdout + p.stderr
            if p.returncode != 2 or why not in p.stderr or p.stdout:
                bad.append("exit %d for %s: not refused before anything ran" % (p.returncode, why))
        if not os.path.isdir(d):
            bad.append("the directory given as a receipt path was removed")
        return bad, text
    finally:
        shutil.rmtree(d, ignore_errors=True)


CASES = [
    ("an accepted baseline lets the poisons run and be counted", baseline_accepted),
    ("a broken clean set is INVALID_BASELINE, and no figure is produced", baseline_broken),
    ("a checker that fires on every row is INVALID_BASELINE, not coverage", checker_overfires),
    ("a snapshot check that fires on anything is caught by the baseline", snapshot_check_overfires),
    ("a refusal without a check id still fails the baseline", refused_without_an_id),
    ("a checker that raises on the clean set is INVALID_BASELINE", baseline_raises),
    ("a load that raises on the clean set is INVALID_BASELINE, not a crash", load_raises),
    ("an escaped poison is a BLIND_SPOT and is not counted", blind_spot),
    ("every escaped poison is reported, not only the first", two_blind_spots),
    ("a poison that fires another check is not caught by its own", wrong_check_fires),
    ("a detecting check that was never called is reported as not executed", check_not_called),
    ("findings that did not come from the declared check are not a catch", fired_but_not_called),
    ("checked, skipped and not-applicable fixtures keep their states", fixture_states),
    ("a detection the baseline never exercised is not counted", unbacked_by_the_baseline),
    ("a run that runs no poison produces no figure and does not pass", nothing_ran),
    ("CHECKS drifting from coverage() fails the run", structure_drift),
    ("coverage() dropping a check fails the run and names it", coverage_drops_a_check),
    ("a crash leaves no old receipt and no temporary directory behind",
     crash_leaves_nothing_behind),
    ("selftest.py run as a script writes a receipt and exits 0", as_a_script),
    ("selftest.py run as a script exits 1 on a red baseline", as_a_script_red),
    ("a receipt path that cannot be written is refused before anything runs",
     receipt_paths_refused),
]

results = []
for name, fn in CASES:
    try:
        bad, out = fn()
    except Exception:
        bad, out = ["raised: " + traceback.format_exc().strip().splitlines()[-1]], \
            traceback.format_exc()
    results.append(not bad)
    print("%-4s %s" % ("ok" if not bad else "RED", name))
    if bad:
        for b in bad:
            print("       %s" % b)
        print(out)

print("")
print("checks_total: %d" % len(results))
print("checks_passing: %d" % sum(1 for x in results if x))
sys.exit(0 if all(results) else 1)
