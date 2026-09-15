"""Gate an extraction against the rows it declined to take.

The identity is  extracted + excluded == total_rows, per source table.

Three outcomes, and the third is the point of the thing:

  PASS   (exit 0)  every source is measured and the identity closes
  FAIL   (exit 1)  some source is measured and the identity does not close
  REVIEW (exit 2)  some source cannot be decided, and nothing failed

REVIEW exists so that "we never wrote the denominator down" cannot be reported as
either a pass or a failure. A missing denominator resolves to `unavailable`, never
to zero, because zero is what an empty sum gives you and it would close the
identity by accident.

States, after Lutar (ai4science.discourse.group/t/.../348):

  measured     the denominator was recorded and the arithmetic was done
  reported     completeness was asserted but no denominator was recorded
  unknown      we looked and could not determine it (recoverable in principle)
  unavailable  the input needed to determine it does not exist any more

Usage:  python ledger_gate.py [exclusions.tsv]
"""
import io, os, sys, csv

MEASURED_OK = "measured:closes"
MEASURED_BAD = "measured:open"
REPORTED = "reported"
UNAVAILABLE = "unavailable"


def classify(row):
    """Return (state, unaccounted_or_None). Never returns a pass for a missing total."""
    total = (row.get("total_rows") or "").strip()
    extracted = (row.get("extracted") or "").strip()
    excluded = (row.get("excluded") or "").strip()
    claim = (row.get("claim") or "").strip()

    if total == "":
        # No denominator. This is the case the gate exists for.
        return (REPORTED if claim == "complete" else UNAVAILABLE), None

    total_n = int(total)
    got = int(extracted or 0) + int(excluded or 0)
    if got == total_n:
        return MEASURED_OK, 0
    return MEASURED_BAD, total_n - got


def main(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh, delimiter="\t")]
    if not rows:
        print("ledger is empty; refusing to report a pass")
        return 2

    counts = {}
    print("%-10s %-18s %-14s %s" % ("pmid", "source", "state", "note"))
    for r in rows:
        state, gap = classify(r)
        counts[state] = counts.get(state, 0) + 1
        note = ""
        if state == MEASURED_BAD:
            note = "%d row(s) unaccounted for" % gap
        elif state in (REPORTED, UNAVAILABLE):
            note = r.get("reason", "")
        print("%-10s %-18s %-14s %s" % (r["pmid"], r["source_table"], state, note[:60]))

    print("")
    for k in (MEASURED_OK, MEASURED_BAD, REPORTED, UNAVAILABLE):
        print("  %-16s %d" % (k, counts.get(k, 0)))

    n_sources = len(rows)
    decidable = counts.get(MEASURED_OK, 0) + counts.get(MEASURED_BAD, 0)
    print("\n  denominator recorded for %d of %d sources" % (decidable, n_sources))

    if counts.get(MEASURED_BAD, 0):
        print("\nFAIL: the identity does not close where it could be evaluated")
        return 1
    if counts.get(REPORTED, 0) or counts.get(UNAVAILABLE, 0):
        print("\nREVIEW: nothing failed, and not everything could be checked")
        return 2
    print("\nPASS")
    return 0


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else
                  os.path.join(here, "exclusions.tsv")))
