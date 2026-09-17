"""Poison the ledger gate and check that it goes red.

The failure this file exists for is the one that cannot be seen from outside: an
empty denominator being read as zero, so that 0 + 0 == 0 closes the identity and a
source nobody measured is reported as a pass. That is the only way this gate can
lie, so it gets its own poison and is checked first.

False red announces itself. False green never does, so a check that has not been
watched to fail is not evidence of anything.

Two things are asserted, and the second is the one that matters:

  1. every case is green on the real code
  2. every case is killed by at least one injected bug, and each bug kills the
     case it was written for

Until (2) holds for every case, the honest state is not PASS. It is
PASS_WITH_INCOMPLETE_MUTATION_COVERAGE, and this file prints that, names the
cases nothing has killed, and exits 0 only because the code under test is
correct today. The four mutants below were proposed by Stephen Lutar on the
forum thread after he ran the gate himself, and the narrow eighth one after he
read the coverage split.
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger_gate import (classify, MEASURED_OK, MEASURED_BAD, REPORTED,
                         UNAVAILABLE, CONFLICT)

# (name, invariant, row, expected_state, expected_gap)
CASES = [
    ("empty denominator must never close", "empty_is_not_zero",
     {"total_rows": "", "extracted": "0", "excluded": "0", "claim": ""},
     UNAVAILABLE, None),
    ("empty denominator with a completeness claim is reported, not measured", "empty_claim_is_reported",
     {"total_rows": "", "extracted": "7", "excluded": "0", "claim": "complete"},
     REPORTED, None),
    ("a real zero table does close", "real_zero_can_close",
     {"total_rows": "0", "extracted": "0", "excluded": "0", "claim": "complete"},
     MEASURED_OK, 0),
    ("a closing table closes", "closure_is_equality",
     {"total_rows": "7", "extracted": "7", "excluded": "0", "claim": ""},
     MEASURED_OK, 0),
    ("a short table is open, by the right amount", "gap_is_exact",
     {"total_rows": "11", "extracted": "7", "excluded": "0", "claim": ""},
     MEASURED_BAD, 4),
    ("exclusions count toward the identity", "exclusions_are_counted",
     {"total_rows": "11", "extracted": "7", "excluded": "4", "claim": ""},
     MEASURED_OK, 0),
    ("a completeness claim cannot rescue a short table", "claim_cannot_override",
     {"total_rows": "6", "extracted": "5", "excluded": "0", "claim": "complete"},
     MEASURED_BAD, 1),
    ("a stated total that disagrees is neither a pass nor a failure", "stated_total_conflicts",
     {"total_rows": "6", "extracted": "6", "excluded": "0", "claim": "complete",
      "claimed_total_rows": "8"},
     CONFLICT, 2),
]


def run(fn, quiet=False):
    """Run every case against fn. Return the list of case names that went red."""
    red = []
    for name, _inv, row, want_state, want_gap in CASES:
        got_state, got_gap = fn(row)
        ok = (got_state == want_state) and (got_gap == want_gap)
        if not ok:
            red.append(name)
        if not quiet:
            print("%-4s %-70s -> %s" % ("ok" if ok else "RED", name, got_state))
    return red


# 1. the real implementation must be green on every case
red = run(classify)
if red:
    print("\nselftest FAILED on the real implementation: %d of %d" % (len(red), len(CASES)))
    sys.exit(1)


# 2. every case must go red under a bug it is supposed to catch. A case that
#    stays green under its own poison is not testing anything.
def read_empty_as_zero(row):
    r = dict(row)
    r["total_rows"] = r["total_rows"] or "0"
    return classify(r)


def ignore_exclusions(row):
    r = dict(row)
    r["excluded"] = "0"
    return classify(r)


def real_zero_becomes_unavailable(row):
    """Zero-boundary mutant: a recorded zero is treated as no denominator."""
    r = dict(row)
    if (r.get("total_rows") or "").strip() == "0":
        r["total_rows"] = ""
    return classify(r)


def closure_off_by_one(row):
    """Closure-comparison mutant: equality replaced by a wrong boundary."""
    state, gap = classify(row)
    if state == MEASURED_OK and gap == 0:
        return MEASURED_BAD, 1
    if state == MEASURED_BAD:
        return MEASURED_OK, 0
    return state, gap


def gap_is_wrong(row):
    """Gap-calculation mutant: the unaccounted count is off."""
    state, gap = classify(row)
    if state == MEASURED_BAD:
        return state, gap + 1
    return state, gap


def claim_overrides_count(row):
    """Claim-override mutant: a completeness claim converts a short table."""
    state, gap = classify(row)
    if state == MEASURED_BAD and (row.get("claim") or "").strip() == "complete":
        return MEASURED_OK, 0
    return state, gap


def stated_total_is_ignored(row):
    """Conflict mutant: a stated total that disagrees is silently dropped."""
    r = dict(row)
    r.pop("claimed_total_rows", None)
    return classify(r)


def claim_over_empty_becomes_unavailable(row):
    """Narrow mutant (Lutar, t348/10): invert only the branch where the
    denominator is absent and a completeness claim is present, leaving the
    closure arithmetic and every other branch alone. Written to find out whether
    that path can be killed for its own reason or only by a coarse mutant."""
    state, gap = classify(row)
    if state == REPORTED:
        return UNAVAILABLE, gap
    return state, gap


# each poison names the invariant it is written to break
POISONS = [
    ("empty denominator read as zero", read_empty_as_zero, "empty_is_not_zero"),
    ("exclusions dropped", ignore_exclusions, "exclusions_are_counted"),
    ("a recorded zero read as unavailable", real_zero_becomes_unavailable, "real_zero_can_close"),
    ("closure compared off by one", closure_off_by_one, "closure_is_equality"),
    ("the unaccounted count is wrong", gap_is_wrong, "gap_is_exact"),
    ("a completeness claim overrides the count", claim_overrides_count, "claim_cannot_override"),
    ("a stated total is ignored", stated_total_is_ignored, "stated_total_conflicts"),
    ("a claim over an absent denominator reads as unavailable",
     claim_over_empty_becomes_unavailable, "empty_claim_is_reported"),
]

# Coverage is counted twice on purpose. A mutant that kills five cases at once is
# not evidence that five invariants are watched: it is evidence that the mutant is
# coarse. Only a case killed by the mutant written against its own invariant has
# been shown to test that invariant, so that is the number the state is taken from.
print("")
covered_any = set()
covered_own = set()
missed_target = []
for label, fn, target_invariant in POISONS:
    caught = run(fn, quiet=True)
    covered_any |= set(caught)
    target_case = [n for n, inv, _r, _s, _g in CASES if inv == target_invariant]
    hit = bool(target_case) and target_case[0] in caught
    if hit:
        covered_own.add(target_case[0])
    note = ""
    if not hit:
        note = "  <- NOT its own case"
    elif len(caught) > 1:
        note = "  <- coarse: also kills %d other case(s)" % (len(caught) - 1)
    print("poison: %-42s killed %d case(s)%s" % (label, len(caught), note))
    if not caught:
        print("  a poison that nothing catches means the suite is not watching this")
        sys.exit(1)
    if not hit:
        missed_target.append((label, target_invariant))

no_own = [(n, inv) for n, inv, _r, _s, _g in CASES if n not in covered_own]
no_any = [(n, inv) for n, inv, _r, _s, _g in CASES if n not in covered_any]

print("")
print("checks_total: %d" % len(CASES))
print("checks_passing: %d" % len(CASES))
print("mutation_verified_by_own_mutant: %d" % len(covered_own))
print("mutation_verified_by_any_mutant: %d" % len(covered_any))
print("mutation_untested: %d" % len(no_any))
print("mutation_coverage_state: %s" % ("COMPLETE" if not no_own else "INCOMPLETE"))
print("state: %s" % ("PASS" if not no_own else "PASS_WITH_INCOMPLETE_MUTATION_COVERAGE"))
print("")
for name, inv, _r, _s, _g in CASES:
    if name in covered_own:
        mark = "VERIFIED"
    elif name in covered_any:
        mark = "KILLED_ONLY_BY_A_COARSE_MUTANT"
    else:
        mark = "UNTESTED"
    print("  invariant_%-24s %s" % (inv + ":", mark))
for name, inv in no_any:
    print("  untested by any poison here: %s" % name)
if missed_target:
    print("")
    for label, inv in missed_target:
        print("  a poison did not kill the case it was written for: %s -> %s" % (label, inv))
    sys.exit(1)
