# -*- coding: utf-8 -*-
"""extraction-gate: mechanical checks that gate the write, not the read.

Every check here exists because a specific failure got through a run that
reported success. The checks run before anything is written. If any check
fails, nothing is written.

Input is a TSV of extracted rows. Required columns:

    row_id   doi   group   label   smiles

Optional columns, each one enabling the checks that use it:

    formula_reported    molecular formula as printed in the source
    stereo_reported     CIP labels as printed, e.g. "1:S,7:R"
    geometry_reported   double bond geometry as printed, e.g. "E" or "Z"
    sequence            residue sequence, for peptides
    target assay readout unit value

Usage
-----
    python gate.py rows.tsv --out clean.tsv --out-root ./build
    python gate.py rows.tsv --out clean.tsv --out-root ./build --snapshot snap.json
    python gate.py rows.tsv --out clean.tsv --out-root ./build --write-snapshot snap.json
    python gate.py rows.tsv --list-checks

Exit status is 0 only when every check passed and the file was written and
read back at the expected size.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

try:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
    from rdkit import RDLogger

    RDLogger.DisableLog("rdApp.*")
except ImportError:  # pragma: no cover
    print("extraction-gate needs rdkit: conda install -c conda-forge rdkit")
    raise

CHECKS = [
    ("C1", "destination", "the path you are about to write is the path you think it is"),
    ("C2", "formula vs source", "rebuilt structure matches the formula printed in the paper"),
    ("C3", "formula vs snapshot", "formula has not drifted since the last accepted run"),
    ("C4", "stereocentres", "assigned CIP labels match the ones printed in the paper"),
    ("C5", "duplicate structures", "one structure does not sit under two labels in one series"),
    ("C6", "sequence collisions", "one sequence does not resolve to two structures in one paper"),
    ("C7", "ring skeleton", "ring profile has not changed while the formula stayed the same"),
    ("C8", "double bond geometry", "every double bond the paper drew is assigned E or Z"),
    ("C9", "external cross-check", "structures reconcile with ChEMBL, keyed on the DOI"),
    ("C10", "exact duplicates", "the same measurement is not stored more than once"),
    ("C11", "label identity", "a printed label is not two different molecules"),
]


# --------------------------------------------------------------------------- helpers
def mol_of(smiles):
    if not smiles:
        return None
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    frags = Chem.GetMolFrags(m, asMols=True, sanitizeFrags=False)
    if len(frags) > 1:  # drop counter-ions, keep the largest fragment
        m = sorted(frags, key=lambda x: x.GetNumHeavyAtoms())[-1]
    return m


def canonical(m):
    return Chem.MolToSmiles(m) if m is not None else None


def formula(m):
    return rdMolDescriptors.CalcMolFormula(m) if m is not None else None


def ring_profile(m):
    """Ring count and sorted ring sizes. Conserved atoms do not conserve rings."""
    if m is None:
        return None
    ri = m.GetRingInfo()
    return "%d:%s" % (ri.NumRings(), ",".join(str(len(r)) for r in sorted(ri.AtomRings(), key=len)))


def cip_string(m):
    if m is None:
        return None
    Chem.AssignStereochemistry(m, cleanIt=True, force=True)
    out = []
    for a in m.GetAtoms():
        if a.HasProp("_CIPCode"):
            out.append("%d:%s" % (a.GetIdx() + 1, a.GetProp("_CIPCode")))
    return ",".join(out)


def double_bond_geometries(m):
    """Stereo of every non-ring double bond between carbons that could carry it."""
    if m is None:
        return []
    out = []
    for b in m.GetBonds():
        if b.GetBondType() != Chem.BondType.DOUBLE or b.IsInRing():
            continue
        if b.GetBeginAtom().GetSymbol() != "C" or b.GetEndAtom().GetSymbol() != "C":
            continue
        s = str(b.GetStereo())
        out.append(s.replace("STEREO", ""))
    return out


def norm_cip(s):
    return ",".join(sorted(x.strip() for x in (s or "").split(",") if x.strip()))


# --------------------------------------------------------------------------- checks
def check_destination(out_path, out_root):
    """C1. The failure this stops: six green checks and nothing written where you looked."""
    fails = []
    ap = os.path.abspath(out_path)
    ar = os.path.abspath(out_root)
    if os.path.commonpath([ap, ar]) != ar:
        fails.append("C1 destination: %s resolves outside the declared root %s" % (ap, ar))
    parent = os.path.dirname(ap)
    if not os.path.isdir(parent):
        fails.append("C1 destination: parent directory does not exist: %s" % parent)
    return fails, ap


def check_formula_vs_source(rows):
    fails = []
    for r in rows:
        want = (r.get("formula_reported") or "").strip()
        if not want:
            continue
        got = formula(r["_mol"])
        if got is None:
            fails.append("C2 %s: structure did not parse" % r["row_id"])
        elif got.replace("+", "").replace("-", "") != want.replace("+", "").replace("-", ""):
            fails.append("C2 %s: formula %s does not match the paper's %s" % (r["row_id"], got, want))
    return fails


def check_formula_vs_snapshot(rows, snap):
    fails = []
    if not snap:
        return fails
    for r in rows:
        prev = (snap.get(r["row_id"]) or {}).get("formula")
        if prev is None:
            continue
        got = formula(r["_mol"])
        if got != prev:
            fails.append("C3 %s: formula changed since the last accepted run, %s to %s"
                         % (r["row_id"], prev, got))
    return fails


def check_stereocentres(rows):
    fails = []
    for r in rows:
        want = norm_cip(r.get("stereo_reported"))
        if not want:
            continue
        got = norm_cip(cip_string(r["_mol"]))
        if got != want:
            fails.append("C4 %s: CIP labels %s do not match the paper's %s"
                         % (r["row_id"], got or "(none)", want))
    return fails


def check_duplicate_structures(rows):
    """C5. One molecule under two labels inside one series is a transcription error."""
    fails = []
    seen = defaultdict(set)
    for r in rows:
        c = canonical(r["_mol"])
        if c:
            seen[(r["doi"], r["group"], c)].add(r["label"])
    for (doi, grp, _c), labels in sorted(seen.items()):
        if len(labels) > 1:
            fails.append("C5 %s / %s: one structure carries %d labels %s"
                         % (doi, grp, len(labels), sorted(labels)))
    return fails


def check_sequence_collisions(rows):
    fails = []
    seq = defaultdict(set)
    for r in rows:
        s = (r.get("sequence") or "").strip()
        c = canonical(r["_mol"])
        if s and c:
            seq[(r["doi"], s)].add(c)
    for (doi, s), structures in sorted(seq.items()):
        if len(structures) > 1:
            fails.append("C6 %s: sequence %s resolves to %d different structures"
                         % (doi, s, len(structures)))
    return fails


def check_ring_skeleton(rows, snap):
    """C7. Atoms were conserved and the ring was not. Formula alone cannot see this."""
    fails = []
    if not snap:
        return fails
    for r in rows:
        prev = snap.get(r["row_id"]) or {}
        if "rings" not in prev:
            continue
        got = ring_profile(r["_mol"])
        if got != prev["rings"]:
            same_formula = formula(r["_mol"]) == prev.get("formula")
            fails.append("C7 %s: ring profile changed %s to %s%s"
                         % (r["row_id"], prev["rings"], got,
                            " while the formula stayed the same" if same_formula else ""))
    return fails


def check_double_bond_geometry(rows):
    """C8. E built where the paper drew Z, and an unassigned bond, both read as valid."""
    fails = []
    for r in rows:
        want = (r.get("geometry_reported") or "").strip().upper()
        if not want:
            continue
        got = [g for g in double_bond_geometries(r["_mol"]) if g != "NONE"]
        unassigned = [g for g in double_bond_geometries(r["_mol"]) if g == "NONE"]
        if not got:
            fails.append("C8 %s: the paper draws %s and no double bond is assigned%s"
                         % (r["row_id"], want,
                            " (%d unassigned)" % len(unassigned) if unassigned else ""))
        elif want not in got:
            fails.append("C8 %s: built %s where the paper draws %s" % (r["row_id"], "/".join(got), want))
    return fails


def check_exact_duplicates(rows):
    """C10. The same measurement stored once per position inflates every repeat count."""
    fails = []
    key = Counter()
    for r in rows:
        if not r.get("value"):
            continue
        key[(r["doi"], r["label"], r.get("target"), r.get("assay"),
             r.get("readout"), r.get("unit"), r.get("value"))] += 1
    dup = {k: n for k, n in key.items() if n > 1}
    if dup:
        extra = sum(n - 1 for n in dup.values())
        fails.append("C10: %d measurement keys are stored more than once, %d rows in excess. "
                     "Collapse them before counting repeats." % (len(dup), extra))
        for k, n in sorted(dup.items())[:5]:
            fails.append("      %s stored %d times" % (" | ".join(str(x) for x in k[:4]), n))
    return fails


def check_label_identity(rows):
    """C11. A printed label is unique inside its own table and nowhere else."""
    fails = []
    within = defaultdict(set)
    across = defaultdict(set)
    for r in rows:
        c = canonical(r["_mol"])
        if not c:
            continue
        within[(r["doi"], r["label"])].add(c)
        across[r["label"]].add((r["doi"], c))
    for (doi, lab), structures in sorted(within.items()):
        if len(structures) > 1:
            fails.append("C11 %s: label %s is %d different molecules inside one report"
                         % (doi, lab, len(structures)))
    for lab, pairs in sorted(across.items()):
        dois = {d for d, _ in pairs}
        structures = {c for _, c in pairs}
        if len(dois) > 1 and len(structures) > 1:
            fails.append("C11 label %s is %d different molecules across %d reports. "
                         "Do not key a cross-report match on it." % (lab, len(structures), len(dois)))
    return fails


def check_chembl(rows, timeout=20):
    """C9. The one check that can see a swap between two structures in the same paper.

    Nothing internal to an extraction can catch activities attached to the wrong
    member of a diastereomer pair. Keyed on the DOI, not the compound name.
    """
    import urllib.parse
    import urllib.request

    fails = []
    by_doi = defaultdict(list)
    for r in rows:
        if r.get("doi"):
            by_doi[r["doi"]].append(r)

    for doi, rs in sorted(by_doi.items()):
        url = ("https://www.ebi.ac.uk/chembl/api/data/document.json?doi__iexact="
               + urllib.parse.quote(doi))
        try:
            with urllib.request.urlopen(url, timeout=timeout) as fh:
                docs = json.load(fh).get("documents", [])
        except Exception as exc:
            fails.append("C9 %s: could not reach ChEMBL (%s)" % (doi, exc))
            continue
        if not docs:
            continue  # not deposited; silence is not evidence either way
        chembl_id = docs[0]["document_chembl_id"]
        url = ("https://www.ebi.ac.uk/chembl/api/data/activity.json?document_chembl_id="
               + chembl_id + "&limit=1000")
        try:
            with urllib.request.urlopen(url, timeout=timeout) as fh:
                acts = json.load(fh).get("activities", [])
        except Exception as exc:
            fails.append("C9 %s: could not read activities (%s)" % (doi, exc))
            continue
        keys = set()
        for a in acts:
            s = a.get("canonical_smiles")
            m = mol_of(s) if s else None
            if m is not None:
                try:
                    keys.add(Chem.MolToInchiKey(m))
                except Exception:
                    pass
        if not keys:
            continue
        for r in rs:
            m = r["_mol"]
            if m is None:
                continue
            try:
                k = Chem.MolToInchiKey(m)
            except Exception:
                continue
            if k not in keys:
                fails.append("C9 %s / %s: structure is not among the %d deposited for this DOI"
                             % (doi, r["label"], len(keys)))
    return fails


# --------------------------------------------------------------------------- driver
def load(path):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    for i, r in enumerate(rows, 1):
        r.setdefault("row_id", "row%d" % i)
        r["_mol"] = mol_of((r.get("smiles") or "").strip())
    return rows


def run_checks(rows, out_path, out_root, snap=None, chembl=False):
    fails, resolved = check_destination(out_path, out_root)
    fails += check_formula_vs_source(rows)
    fails += check_formula_vs_snapshot(rows, snap)
    fails += check_stereocentres(rows)
    fails += check_duplicate_structures(rows)
    fails += check_sequence_collisions(rows)
    fails += check_ring_skeleton(rows, snap)
    fails += check_double_bond_geometry(rows)
    if chembl:
        fails += check_chembl(rows)
    fails += check_exact_duplicates(rows)
    fails += check_label_identity(rows)
    return fails, resolved


def coverage(rows, snap, chembl):
    """How many rows each check could actually look at.

    A blank column is not a pass. A check with nothing to work with has to say
    so, or an empty corpus reports as clean.
    """
    n = len(rows)
    parsed = sum(1 for r in rows if r["_mol"] is not None)
    have = lambda col: sum(1 for r in rows if (r.get(col) or "").strip())
    in_snap = sum(1 for r in rows if snap and r["row_id"] in snap) if snap else 0
    return [
        ("C1", "destination", n, n),
        ("C2", "formula vs source", have("formula_reported"), n),
        ("C3", "formula vs snapshot", in_snap, n),
        ("C4", "stereocentres", have("stereo_reported"), n),
        ("C5", "duplicate structures", parsed, n),
        ("C6", "sequence collisions", have("sequence"), n),
        ("C7", "ring skeleton", in_snap, n),
        ("C8", "double bond geometry", have("geometry_reported"), n),
        ("C9", "external cross-check", have("doi") if chembl else 0, n),
        ("C10", "exact duplicates", have("value"), n),
        ("C11", "label identity", parsed, n),
    ]


def snapshot_of(rows):
    return {r["row_id"]: {"formula": formula(r["_mol"]), "rings": ring_profile(r["_mol"])}
            for r in rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gate an extraction before it is written.")
    ap.add_argument("rows", nargs="?", help="TSV of extracted rows")
    ap.add_argument("--out", help="file to write when every check passes")
    ap.add_argument("--out-root", default=".", help="declared root the output must sit under")
    ap.add_argument("--snapshot", help="JSON from a previously accepted run")
    ap.add_argument("--write-snapshot", help="write a snapshot after a passing run")
    ap.add_argument("--chembl", action="store_true", help="run the external cross-check (network)")
    ap.add_argument("--list-checks", action="store_true")
    a = ap.parse_args(argv)

    if a.list_checks:
        for cid, name, why in CHECKS:
            print("%-4s %-22s %s" % (cid, name, why))
        return 0
    if not a.rows or not a.out:
        ap.error("rows and --out are required")

    rows = load(a.rows)
    snap = json.load(open(a.snapshot, encoding="utf-8")) if a.snapshot else None
    fails, resolved = run_checks(rows, a.out, a.out_root, snap, a.chembl)

    print("extraction-gate: %d rows from %s" % (len(rows), a.rows))
    print("  writing to %s" % resolved)
    blind = [(cid, name) for cid, name, k, _t in coverage(rows, snap, a.chembl) if k == 0]
    for cid, name, k, t in coverage(rows, snap, a.chembl):
        print("    %-4s %-22s %d/%d rows%s" % (cid, name, k, t, "" if k else "   NOTHING TO CHECK"))
    if blind:
        print("  %d check(s) had nothing to work with: %s"
              % (len(blind), ", ".join(c for c, _ in blind)))
    if fails:
        print("  REFUSED, %d finding(s). Nothing was written." % len(fails))
        for f in fails:
            print("    " + f)
        return 1

    cols = [c for c in rows[0].keys() if not c.startswith("_")]
    with open(resolved, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # the write is not believed until it is read back
    with open(resolved, encoding="utf-8", newline="") as fh:
        back = list(csv.DictReader(fh, delimiter="\t"))
    if len(back) != len(rows):
        print("  WROTE THEN FAILED READBACK: %d rows in, %d rows out" % (len(rows), len(back)))
        return 1

    if a.write_snapshot:
        json.dump(snapshot_of(rows), open(a.write_snapshot, "w", encoding="utf-8"), indent=1)
        print("  snapshot written to %s" % a.write_snapshot)
    print("  PASSED all checks, %d rows written and read back." % len(back))
    return 0


if __name__ == "__main__":
    sys.exit(main())
