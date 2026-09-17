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

and one more, added 2026-09-17 on his suggestion:

  conflict:claimed_total_disagrees
               the source states a numeric total and it disagrees with the
               observed one. Neither value wins here. A person has to look.

Precedence, once a denominator is itself disputed (Lutar, t348/10): `conflict`
outranks `measured:open`. The size of a gap is not interpretable while the
total it is measured against is in dispute, so the gap is still recorded but it
does not decide the terminal state.

Usage:  python ledger_gate.py [exclusions.tsv] [--receipt PATH]
                              [--source-commit VALUE]

The receipt is a small JSON record of the decision, written on any outcome, so
that a caller does not have to scrape this output. It declares itself as
`extraction-gate-receipt/v0` with `schema_stability: experimental`, so a
consumer can refuse a version it does not know: the corpus it describes is not
public until 1 November 2026 and these field names may still move. They already
have once, between the first receipt and this one.

`--source-commit` records what the caller says was executed. It is kept as a
claim, not as identity. `evaluator_sha256` is computed from the file that ran
and is the authoritative one, because the two disagree exactly when the working
tree has been edited.
"""
import hashlib, io, json, os, sys, csv

MEASURED_OK = "measured:closes"
MEASURED_BAD = "measured:open"
REPORTED = "reported"
UNAVAILABLE = "unavailable"
CONFLICT = "conflict:claimed_total_disagrees"

RECEIPT_VERSION = 0


def classify(row):
    """Return (state, unaccounted_or_None). Never returns a pass for a missing total."""
    total = (row.get("total_rows") or "").strip()
    extracted = (row.get("extracted") or "").strip()
    excluded = (row.get("excluded") or "").strip()
    claim = (row.get("claim") or "").strip()
    claimed = (row.get("claimed_total_rows") or "").strip()

    if total == "":
        # No denominator. This is the case the gate exists for.
        return (REPORTED if claim == "complete" else UNAVAILABLE), None

    total_n = int(total)
    if claimed != "" and int(claimed) != total_n:
        # A stated total against an observed one. Preferring either silently is
        # the failure this state exists to prevent.
        return CONFLICT, int(claimed) - total_n

    got = int(extracted or 0) + int(excluded or 0)
    if got == total_n:
        return MEASURED_OK, 0
    return MEASURED_BAD, total_n - got


def sha256_of(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def main(path, receipt_path=None, source_commit=None):
    with io.open(path, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh, delimiter="\t")]
    if not rows:
        print("ledger is empty; refusing to report a pass")
        return 2

    counts = {}
    unaccounted = 0
    print("%-10s %-18s %-32s %s" % ("pmid", "source", "state", "note"))
    for r in rows:
        state, gap = classify(r)
        counts[state] = counts.get(state, 0) + 1
        note = ""
        if state == MEASURED_BAD:
            note = "%d row(s) unaccounted for" % gap
            unaccounted += gap
        elif state == CONFLICT:
            note = "stated total differs from the observed one by %d" % gap
        elif state in (REPORTED, UNAVAILABLE):
            note = r.get("reason", "")
        print("%-10s %-18s %-32s %s" % (r["pmid"], r["source_table"], state, note[:60]))

    print("")
    for k in (MEASURED_OK, MEASURED_BAD, CONFLICT, REPORTED, UNAVAILABLE):
        print("  %-32s %d" % (k, counts.get(k, 0)))

    n_sources = len(rows)
    decidable = counts.get(MEASURED_OK, 0) + counts.get(MEASURED_BAD, 0)
    print("\n  denominator recorded for %d of %d sources" % (decidable, n_sources))

    if counts.get(CONFLICT, 0):
        # A disputed denominator outranks an open one: the gap is not
        # interpretable while the total it is measured against is in dispute.
        decision, code, cause = "FAIL", 1, "claimed_total_conflict"
        why = "a stated total disagrees with the observed one"
    elif counts.get(MEASURED_BAD, 0):
        decision, code, cause = "FAIL", 1, "identity_open"
        why = "the identity does not close where it could be evaluated"
    elif counts.get(REPORTED, 0) or counts.get(UNAVAILABLE, 0):
        decision, code, cause = "REVIEW", 2, "unresolved"
        why = "nothing failed, and not everything could be checked"
    else:
        decision, code, cause = "PASS", 0, "none"
        why = ""
    print("\n%s%s" % (decision, ": " + why if why else ""))

    if receipt_path:
        receipt = {
            "schema": "extraction-gate-receipt/v%d" % RECEIPT_VERSION,
            "schema_stability": "experimental",
            "decision": decision,
            "terminal_cause": cause,
            "write_authorized": decision == "PASS",
            "sources_total": n_sources,
            "measured_closing": counts.get(MEASURED_OK, 0),
            "measured_open": counts.get(MEASURED_BAD, 0),
            "claimed_total_conflicts": counts.get(CONFLICT, 0),
            "reported": counts.get(REPORTED, 0),
            "unavailable": counts.get(UNAVAILABLE, 0),
            "denominator_recorded": decidable,
            "unaccounted_rows": unaccounted,
            "ledger_sha256": sha256_of(path),
            "evaluator_sha256": sha256_of(os.path.abspath(__file__)),
            "evaluator_identity_authority": "evaluator_sha256",
        }
        if source_commit:
            receipt["source_commit"] = source_commit
            receipt["source_commit_authority"] = "claim by the caller, not verified here"
            receipt["working_tree_state"] = "unavailable"
        with io.open(receipt_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(receipt, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print("receipt -> %s" % receipt_path)
    return code


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]

    def take(flag):
        if flag in args:
            i = args.index(flag)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return None

    receipt = take("--receipt")
    commit = take("--source-commit")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(main(args[0] if args else os.path.join(here, "exclusions.tsv"), receipt, commit))
