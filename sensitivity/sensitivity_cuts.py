"""Three cuts of one statistic, and two baselines for it.

The statistic is the within-group spread: fix parent, paper, target, assay,
readout and surrogate class, let the position of the backbone replacement move,
and take the largest ratio over the smallest inside that group.

The cuts answer a question asked in the forum thread this came from. Is the
headline sensitive to the measurements a person transcribed from a scanned
table, or to the removal of whole groups that contain one?

  inclusive             every admissible pair
  group-clean           drop any group holding a human-transcribed value
  measurement-filtered  drop only those values, rebuild the groups, and
                        reapply the minimum-position requirement

The baselines answer the other one. How much of the rise in the median as the
minimum position count increases is an extreme taken over more draws?

  position-matched  restrict every group to the same number of positions
  pooled            draw as many ratios at random from the pooled set as the
                    group holds. This breaks the group structure entirely and
                    mixes classes and targets, so it is a ceiling for an
                    unstructured draw and not a null model for position.

Counts are taken after removing rows identical in every column. See
duplicate_rows.py for why that matters.

Usage:  python sensitivity_cuts.py [--dataset DIR] [--out DIR] [--seed N]
"""
import argparse, collections, csv, io, os, random, statistics, sys

GROUP_COLS = ("group_id", "target", "assay", "readout", "unit_B")
MARKS = ("unresolved", "text_says", "not_verified")


def rd(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def num(s):
    try:
        v = float(s)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def dedup(rows):
    seen, out = set(), []
    for r in rows:
        k = tuple(sorted(r.items()))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def gkey(r):
    return tuple((r.get(c) or "").strip() for c in GROUP_COLS)


def groups(rows, minpos):
    k = collections.defaultdict(list)
    for r in rows:
        v = num(r.get("fold_B_over_A"))
        if v:
            k[gkey(r)].append((v, (r.get("position") or "").strip(), r))
    return {kk: vv for kk, vv in sorted(k.items()) if len({x[1] for x in vv}) >= minpos}


def summary(gs):
    sp = sorted(max(x[0] for x in vv) / min(x[0] for x in vv) for vv in gs.values())
    return len(gs), statistics.median(sp), sp[-1], sum(len(vv) for vv in gs.values())


def band(meds):
    meds.sort()
    return statistics.median(meds), meds[int(0.025 * len(meds))], meds[int(0.975 * len(meds))]


def matched(gs, npos, rnd, iters):
    meds = []
    keys = sorted(gs.keys())
    for _ in range(iters):
        sp = []
        for k in keys:
            byp = collections.defaultdict(list)
            for val, pos, _r in gs[k]:
                byp[pos].append(val)
            poss = sorted(byp)
            if len(poss) < npos:
                continue
            vals = [min(byp[q]) for q in rnd.sample(poss, npos)]
            sp.append(max(vals) / min(vals))
        if sp:
            meds.append(statistics.median(sp))
    return band(meds)


def pooled(gs, pool, rnd, iters):
    meds = []
    keys = sorted(gs.keys())
    for _ in range(iters):
        sp = []
        for k in keys:
            vals = rnd.sample(pool, len(gs[k]))
            sp.append(max(vals) / min(vals))
        assert len(sp) == len(keys), (len(sp), len(keys))
        meds.append(statistics.median(sp))
    return band(meds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=".")
    ap.add_argument("--out", default=None, help="write the id tables here")
    ap.add_argument("--seed", type=int, default=20260917)
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--gate", default=None,
                    help="module:function returning the admissible subset, default every pair")
    a = ap.parse_args()

    pairs = rd(os.path.join(a.dataset, "pairs.tsv"))
    if a.gate:
        mod, fn = a.gate.split(":")
        sys.path.insert(0, a.dataset)
        pairs = getattr(__import__(mod), fn)(pairs, why="sensitivity_cuts", quiet=True)
    rows = dedup(pairs)
    print("pairs %d rows, %d after removing rows identical in every column" % (len(pairs), len(rows)))
    numeric = [r for r in rows if num(r.get("fold_B_over_A"))]
    print("  %d = %d with a ratio + %d without" % (len(rows), len(numeric), len(rows) - len(numeric)))

    vpath = os.path.join(a.dataset, "verification.tsv")
    tier = {}
    if os.path.exists(vpath):
        for x in rd(vpath):
            tier.setdefault((x["pmid"].strip(), x["compound"].strip(), x["target"].strip()),
                            set()).add(x["status"])

    def tiers_of(r):
        out = set()
        for c in (r.get("cmpd_A"), r.get("cmpd_B")):
            for pm in (r.get("pmid") or "").split("+"):
                out |= tier.get((pm.strip(), (c or "").strip(), (r.get("target") or "").strip()), set())
        return out

    def has_eye(r):
        return "FOUND_EYE" in tiers_of(r)

    cuts = {}
    for minpos in (2, 4):
        inc = groups(rows, minpos)
        eye_groups = {k for k, vv in inc.items() if any(has_eye(x[2]) for x in vv)}
        gc = {k: vv for k, vv in inc.items() if k not in eye_groups}
        mf = groups([r for r in rows if not has_eye(r)], minpos)
        cuts[minpos] = (inc, gc, mf, eye_groups)
        for name, gs in (("inclusive", inc), ("group-clean", gc), ("measurement-filtered", mf)):
            n, med, mx, npairs = summary(gs)
            print("  >=%d positions  %-21s groups %3d  pairs %4d  median %7.1f  max %9.1f"
                  % (minpos, name, n, npairs, med, mx))

    rnd = random.Random(a.seed)
    inc2, inc4 = cuts[2][0], cuts[4][0]
    pool = sorted(num(r["fold_B_over_A"]) for r in numeric)
    print("")
    print("position-matched (seed %d, %d iterations)" % (a.seed, a.iters))
    print("  the >=4 groups held at 4 positions   median %.1f  (observed %.1f)"
          % (matched(inc4, 4, rnd, a.iters)[0], summary(inc4)[1]))
    print("  all groups held at 2 positions       median %.1f" % matched(inc2, 2, rnd, a.iters)[0])
    print("  the >=4 groups held at 2 positions   median %.1f" % matched(inc4, 2, rnd, a.iters)[0])
    p4, p2 = pooled(inc4, pool, rnd, a.iters), pooled(inc2, pool, rnd, a.iters)
    print("pooled draws of the same size from %d ratios" % len(pool))
    print("  >=4  observed %.1f  vs pooled %.1f (95%% of iterations %.1f to %.1f)"
          % (summary(inc4)[1], p4[0], p4[1], p4[2]))
    print("  >=2  observed %.1f  vs pooled %.1f (95%% of iterations %.1f to %.1f)"
          % (summary(inc2)[1], p2[0], p2[1], p2[2]))

    if a.out:
        os.makedirs(a.out, exist_ok=True)
        path = os.path.join(a.out, "groups_human_transcribed.tsv")
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter="\t", lineterminator="\n")
            w.writerow(["min_positions"] + list(GROUP_COLS) + ["positions", "pairs", "spread"])
            for minpos in (2, 4):
                inc, _gc, _mf, eye_groups = cuts[minpos]
                for k in sorted(eye_groups):
                    vv = inc[k]
                    w.writerow([minpos] + list(k) + [len({x[1] for x in vv}), len(vv),
                                                     "%.1f" % (max(x[0] for x in vv) / min(x[0] for x in vv))])
        path2 = os.path.join(a.out, "pairs_dual_state.tsv")
        with io.open(path2, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter="\t", lineterminator="\n")
            w.writerow(["pmid", "group_id", "position", "cmpd_A", "cmpd_B", "target", "issue_flags"])
            for r in rows:
                if num(r.get("fold_B_over_A")):
                    continue
                fl = sorted({x for x in (r.get("flags") or "").split(";")
                             if any(t in x for t in MARKS)})
                if fl:
                    w.writerow([r["pmid"], r["group_id"], r["position"], r["cmpd_A"], r["cmpd_B"],
                                r["target"], ";".join(fl)])
        print("")
        print("wrote %s and %s" % (os.path.basename(path), os.path.basename(path2)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
