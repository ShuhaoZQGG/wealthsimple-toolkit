"""Text-table overviews: per-account weights, aggregates, sector rollups."""

from collections import defaultdict


def fmt(v):
    return f"${v:,.0f}"


def cmd_overview(args, accounts, scope_label, rows, labels, nlv=None):
    by_acct = defaultdict(list)
    for r in rows:
        by_acct[r["account_id"]].append(r)
    grand = sum(r["value"] for r in rows)
    unclassified = sorted({r["sym"] for r in rows if r["sector"] == "Unclassified"})

    for a in accounts:
        aid = a["id"]
        acct_rows = sorted(by_acct.get(aid, []), key=lambda r: -r["value"])
        total = sum(r["value"] for r in acct_rows)
        share = total / grand * 100 if grand else 0
        print(f"=== {labels[aid]} — {fmt(total)} ({share:.1f}% of shown scope) ===")
        if args.group == "stock" or not args.per_account:
            if args.group == "stock":
                print(f"{'Sym':<10}{'Name':<32}{'Value':>12}{'%acct':>7}{'P&L%':>8}")
                for r in acct_rows:
                    print(
                        f"{r['sym']:<10}{r['name'][:30]:<32}{fmt(r['value']):>12}"
                        f"{r['value']/total*100 if total else 0:>6.1f}%"
                        f"{r['pnl_pct']:>+7.1f}%"
                    )
        if args.group == "sector" or args.per_account:
            if args.group == "stock" and args.per_account:
                print()
            buckets = defaultdict(float)
            for r in acct_rows:
                buckets[r["sector"]] += r["value"]
            print("-- by bucket --")
            for b, v in sorted(buckets.items(), key=lambda kv: -kv[1]):
                print(f"  {b:<22}{fmt(v):>12}{v/total*100 if total else 0:>6.1f}%")
        if nlv and nlv.get(aid):
            cov = total / nlv[aid] * 100 if nlv[aid] else 0
            print(
                f"  [holdings cover {cov:.0f}% of account NLV "
                f"({fmt(nlv[aid])}); rest = cash / non-visible positions]"
            )
        print()

    print(f"=== AGGREGATE ({len(accounts)} accounts — {scope_label}) — {fmt(grand)} ===")
    if args.group == "stock":
        agg = defaultdict(float)
        for r in rows:
            agg[r["sym"]] += r["value"]
        print(f"{'Sym':<10}{'Value':>12}{'%tot':>7}")
        for sym, v in sorted(agg.items(), key=lambda kv: -kv[1]):
            print(f"{sym:<10}{fmt(v):>12}{v/grand*100 if grand else 0:>6.1f}%")
    else:
        buckets = defaultdict(lambda: {"value": 0.0, "names": set()})
        for r in rows:
            b = buckets[r["sector"]]
            b["value"] += r["value"]
            b["names"].add(r["sym"])
        print(f"{'Bucket':<24}{'Value':>12}{'%tot':>7}  Holdings")
        for b, d in sorted(buckets.items(), key=lambda kv: -kv[1]["value"]):
            names = ", ".join(sorted(d["names"])[:6])
            if len(d["names"]) > 6:
                names += f" +{len(d['names'])-6} more"
            print(
                f"{b:<24}{fmt(d['value']):>12}"
                f"{d['value']/grand*100 if grand else 0:>6.1f}%  {names}"
            )
    print()
    if unclassified:
        print(f"Unclassified symbols (not in buckets.json): {', '.join(unclassified)}")
        print("Add them to ~/.config/wst/buckets.json.\n")
    print(
        "Note: residual cash is not a holding and is excluded above. "
        "Wealthsimple's API also omits managed-account positions; "
        "use --reconcile to see the coverage gap per account."
    )
