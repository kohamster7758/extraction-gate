# -*- coding: utf-8 -*-
"""Prove that every check can go red, and that a clean set goes green.

A checker that has never been seen to fail is not evidence of anything. False
red is visible the moment it happens. False green is never visible. So each
check here gets its own poisoned row, and the test asserts that the check
fires on it and that nothing fires on the clean set.
"""
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


def ids(fails):
    """Check ids only. Continuation lines are indented and carry no id."""
    out = set()
    for f in fails:
        m = re.match(r"^(C\d+)", f)
        if m:
            out.add(m.group(1))
    return out


def main():
    tmp = tempfile.mkdtemp(prefix="extraction-gate-")
    results = []

    def case(cid, rows, expect, snap=None, **kw):
        fails = run(rows, tmp, snap=snap, **kw)
        got = ids(fails)
        ok = (expect in got) if expect else (not got)
        results.append((cid, ok, sorted(got), fails[:2]))
        return ok

    import gate as g

    # green: nothing fires on a clean set
    case("clean", clean_rows(), None)

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

    shutil.rmtree(tmp, ignore_errors=True)

    print()
    width = max(len(c) for c, *_ in results)
    bad = 0
    for cid, ok, got, sample in results:
        print("  %-7s %-*s  fired: %s" % ("PASS" if ok else "FAIL", width, cid,
                                          ",".join(got) or "(none)"))
        if not ok:
            bad += 1
            for s in sample:
                print("          %s" % s)
    print()
    print("  %d/%d" % (len(results) - bad, len(results)))
    if bad:
        print("  a check that cannot be seen to fail is not a check")
        return 1
    print("  every check fired on its own poison, and none fired on the clean set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
