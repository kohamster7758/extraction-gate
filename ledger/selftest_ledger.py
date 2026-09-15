"""Poison the ledger gate and check that it goes red.

The failure this file exists for is the one that cannot be seen from outside: an
empty denominator being read as zero, so that 0 + 0 == 0 closes the identity and a
source nobody measured is reported as a pass. That is the only way this gate can
lie, so it gets its own poison and is checked first.

False red announces itself. False green never does, so a check that has not been
watched to fail is not evidence of anything.
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger_gate import classify, MEASURED_OK, MEASURED_BAD, REPORTED, UNAVAILABLE

CASES = [
    # (name, row, expected_state, expected_gap)
    ("empty denominator must never close",
     {"total_rows": "", "extracted": "0", "excluded": "0", "claim": ""},
     UNAVAILABLE, None),
    ("empty denominator with a completeness claim is reported, not measured",
     {"total_rows": "", "extracted": "7", "excluded": "0", "claim": "complete"},
     REPORTED, None),
    ("a real zero table does close",
     {"total_rows": "0", "extracted": "0", "excluded": "0", "claim": "complete"},
     MEASURED_OK, 0),
    ("a closing table closes",
     {"total_rows": "7", "extracted": "7", "excluded": "0", "claim": ""},
     MEASURED_OK, 0),
    ("a short table is open, by the right amount",
     {"total_rows": "11", "extracted": "7", "excluded": "0", "claim": ""},
     MEASURED_BAD, 4),
    ("exclusions count toward the identity",
     {"total_rows": "11", "extracted": "7", "excluded": "4", "claim": ""},
     MEASURED_OK, 0),
    ("a completeness claim cannot rescue a short table",
     {"total_rows": "6", "extracted": "5", "excluded": "0", "claim": "complete"},
     MEASURED_BAD, 1),
]

def run(fn, label, quiet=False):
    """Run every case against fn. Return the list of case names that went red."""
    red = []
    for name, row, want_state, want_gap in CASES:
        got_state, got_gap = fn(row)
        ok = (got_state == want_state) and (got_gap == want_gap)
        if not ok:
            red.append(name)
        if not quiet:
            print("%-4s %-62s -> %s" % ("ok" if ok else "RED", name, got_state))
    return red


# 1. the real implementation must be green on every case
red = run(classify, "clean")
if red:
    print("\nselftest FAILED on the real implementation: %d of %d"
          % (len(red), len(CASES)))
    sys.exit(1)

# 2. every case must go red under a bug it is supposed to catch, and the bug that
#    matters here is reading an empty denominator as zero. A case that stays green
#    under its own poison is not testing anything.
def read_empty_as_zero(row):
    r = dict(row)
    r["total_rows"] = r["total_rows"] or "0"
    return classify(r)


def ignore_exclusions(row):
    r = dict(row)
    r["excluded"] = "0"
    return classify(r)


POISONS = [("empty denominator read as zero", read_empty_as_zero),
           ("exclusions dropped", ignore_exclusions)]

print("")
covered = set()
for label, fn in POISONS:
    caught = run(fn, label, quiet=True)
    covered |= set(caught)
    print("poison: %-32s caught %d case(s)" % (label, len(caught)))
    if not caught:
        print("  a poison that nothing catches means the suite is not watching this")
        sys.exit(1)

untested = [n for n, _, _, _ in CASES if n not in covered]
print("")
print("selftest passed: %d of %d green on the real code." % (len(CASES), len(CASES)))
print("%d of %d have been watched to go red under an injected bug." %
      (len(covered), len(CASES)))
for n in untested:
    print("  untested by any poison here: %s" % n)
