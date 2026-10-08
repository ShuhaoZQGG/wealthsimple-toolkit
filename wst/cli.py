"""wst — local-first Wealthsimple holdings overview (unofficial API, read-only)."""

import argparse
import json
import os
import shutil

from .auth import cmd_login
from .data import (
    load_config,
    load_buckets,
    load_defaults,
    list_accounts,
    resolve_accounts,
    fetch_positions,
    normalize_rows,
    account_nlv,
    display_label,
    CONFIG_DIR,
    CONFIG_FILE,
    BUCKETS_FILE,
)
from .overview import cmd_overview
from .html import cmd_pie

EXAMPLE_BUCKETS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "buckets.example.json")


def cmd_accounts(args):
    accts = list_accounts(open_only=not args.all)
    print(json.dumps(accts, indent=2))


def cmd_buckets(args):
    if args.init:
        os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
        if os.path.exists(BUCKETS_FILE) and not args.force:
            print(f"{BUCKETS_FILE} already exists (use --force to overwrite).")
            return
        shutil.copy(EXAMPLE_BUCKETS, BUCKETS_FILE)
        print(f"Created {BUCKETS_FILE} — edit it to map your symbols to buckets.")
    elif args.autofill:
        cmd_autofill(args)
    elif args.review:
        cmd_review(args)
    else:
        print(json.dumps(load_buckets(), indent=2))


def save_buckets(buckets):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    if os.path.exists(BUCKETS_FILE):
        shutil.copy(BUCKETS_FILE, BUCKETS_FILE + ".bak")
    with open(BUCKETS_FILE, "w") as f:
        json.dump(buckets, f, indent=1, sort_keys=True)
    os.chmod(BUCKETS_FILE, 0o600)


def holding_symbols(currency="CAD"):
    """All symbols currently held (any open account) with company names."""
    positions = fetch_positions(currency)
    out = {}
    for p in positions:
        node = p.get("node", p)
        st = (node.get("security") or {}).get("stock") or {}
        sym = st.get("symbol") or (node.get("security") or {}).get("securityType", "?")
        if sym not in out:
            out[sym] = st.get("name") or sym
    return out


def cmd_autofill(args):
    buckets = load_buckets()
    defaults = load_defaults()
    syms = holding_symbols(args.currency)
    filled, unknown = [], []
    for sym in sorted(syms):
        if sym in buckets:
            continue
        if sym in defaults:
            buckets[sym] = defaults[sym]
            filled.append(sym)
        else:
            unknown.append(sym)
    save_buckets(buckets)
    print(f"Auto-filled {len(filled)} symbols from shipped defaults.")
    if unknown:
        print(f"Still unclassified ({len(unknown)}): {', '.join(unknown)}")
        print("Run `wst buckets --review` to classify them interactively.")


def cmd_review(args):
    buckets = load_buckets()
    defaults = load_defaults()
    syms = holding_symbols(args.currency)
    todo = [(s, syms[s]) for s in sorted(syms) if s not in buckets]
    if not todo:
        print("Nothing unclassified — every holding has a bucket.")
        return
    print(f"{len(todo)} unclassified symbols. Enter=accept suggestion, "
          f"type a bucket, s=skip, q=quit.\n")
    seen_buckets = sorted(set(buckets.values()) | set(defaults.values()))
    for sym, name in todo:
        suggestion = defaults.get(sym, "")
        prompt = f"{sym} — {name}"
        if suggestion:
            prompt += f"  [suggested: {suggestion}]"
        prompt += "\nExisting buckets: " + ", ".join(seen_buckets[:12])
        if len(seen_buckets) > 12:
            prompt += f" (+{len(seen_buckets)-12} more)"
        prompt += "\nbucket> "
        try:
            ans = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nStopped — progress saved.")
            break
        if ans.lower() == "q":
            break
        if ans.lower() == "s":
            continue
        bucket = ans or suggestion
        if not bucket:
            print("  skipped (no bucket given).")
            continue
        buckets[sym] = bucket
        if bucket not in seen_buckets:
            seen_buckets.append(bucket)
            seen_buckets.sort()
        save_buckets(buckets)
        print(f"  {sym} -> {bucket}")
    print("Done.")


def _common(args):
    config = load_config()
    accounts, scope_label = resolve_accounts(args.accounts, config)
    if not accounts:
        print("wst: no accounts in scope.", )
        raise SystemExit(1)
    buckets = load_buckets()
    positions = fetch_positions(args.currency)
    rows = normalize_rows(positions, [a["id"] for a in accounts], buckets)
    labels = display_label(accounts)
    return config, accounts, scope_label, rows, labels


def cmd_overview_wrap(args):
    config, accounts, scope_label, rows, labels = _common(args)
    nlv = None
    if args.reconcile:
        nlv = {a["id"]: account_nlv(a["id"], args.currency) for a in accounts}
    cmd_overview(args, accounts, scope_label, rows, labels, nlv)


def cmd_pie_wrap(args):
    config, accounts, scope_label, rows, labels = _common(args)
    cmd_pie(args, accounts, scope_label, rows, labels, config)


def main():
    ap = argparse.ArgumentParser(
        prog="wst",
        description="Local-first Wealthsimple holdings overview (unofficial API, read-only).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="one-time login (WS_USERNAME/WS_PASSWORD/WS_OTP env vars)")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("accounts", help="list accounts")
    p.add_argument("--all", action="store_true", help="include closed accounts")
    p.set_defaults(func=cmd_accounts)

    p = sub.add_parser("buckets", help="manage the symbol->bucket map")
    p.add_argument("--init", action="store_true",
                   help=f"create {BUCKETS_FILE} from the example template")
    p.add_argument("--autofill", action="store_true",
                   help="auto-classify unmapped holdings from shipped defaults "
                        "(S&P 500 GICS sectors + common ETFs)")
    p.add_argument("--review", action="store_true",
                   help="interactively classify remaining unmapped symbols")
    p.add_argument("--force", action="store_true", help="overwrite existing buckets file")
    p.add_argument("--currency", default="CAD")
    p.set_defaults(func=cmd_buckets)

    p = sub.add_parser("overview", help="text-table overview: weights, aggregates, sectors")
    p.add_argument("--accounts", default="all",
                   help="'all' (default), a saved scope name from config.json, "
                        "or comma-separated id/type/description matchers (e.g. 'tfsa,rrsp')")
    p.add_argument("--group", choices=["stock", "sector"], default="stock")
    p.add_argument("--per-account", action="store_true",
                   help="with --group sector: also show the sector split per account")
    p.add_argument("--reconcile", action="store_true",
                   help="compare holdings totals to financials NLV per account")
    p.add_argument("--currency", default="CAD")
    p.set_defaults(func=cmd_overview_wrap)

    p = sub.add_parser("pie", help="interactive pie-chart HTML page")
    p.add_argument("--accounts", default="all",
                   help="same account selector as 'overview'")
    p.add_argument("--currency", default="CAD")
    p.add_argument("-o", "--output", default="holdings.html",
                   help="output HTML file (default: holdings.html)")
    p.set_defaults(func=cmd_pie_wrap)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
