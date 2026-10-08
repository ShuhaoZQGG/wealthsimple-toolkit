"""Config, account discovery, and holdings fetching. No hardcoded accounts."""

import json
import os

from .auth import load_api, die

CONFIG_DIR = os.path.expanduser("~/.config/wst")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
BUCKETS_FILE = os.path.join(CONFIG_DIR, "buckets.json")


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {}
    cfg.setdefault("exclude_accounts", [])
    cfg.setdefault("scopes", {})
    return cfg


def load_buckets():
    try:
        with open(BUCKETS_FILE) as f:
            data = json.load(f)
        data.pop("_note", None)
        return data
    except FileNotFoundError:
        return {}


def load_defaults():
    """Shipped auto-classification: S&P 500 -> GICS sector + common ETFs."""
    import importlib.resources as res

    try:
        text = res.files("wst").joinpath("defaults.json").read_text()
    except (FileNotFoundError, ModuleNotFoundError):
        # dev fallback: repo checkout without install
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "defaults.json")) as f:
            text = f.read()
    data = json.loads(text)
    data.pop("_note", None)
    return data


def slim_account(a):
    return {
        k: a.get(k)
        for k in ("id", "description", "number", "type", "accountType",
                  "status", "currency")
        if k in a
    }


def list_accounts(open_only=True):
    api = load_api()
    return [slim_account(a) for a in api.get_accounts(open_only=open_only)]


def _matches(acct, matcher):
    m = matcher.lower()
    return (
        m == (acct.get("id") or "").lower()
        or m in (acct.get("description") or "").lower()
        or m in (acct.get("type") or "").lower()
    )


def resolve_accounts(spec, config):
    """Return (accounts, scope_label). spec: 'all', a saved scope name, or a
    comma-separated list of id / type / description-substring matchers."""
    accounts = list_accounts(open_only=True)
    excluded = set(config.get("exclude_accounts", []))
    spec = (spec or "all").strip()

    scopes = config.get("scopes", {})
    scope_names = {k.lower(): k for k in scopes}
    if spec.lower() in scope_names:
        wanted = set(scopes[scope_names[spec.lower()]])
        chosen = [a for a in accounts if a["id"] in wanted]
        return chosen, scope_names[spec.lower()]

    if spec.lower() == "all":
        chosen = [a for a in accounts if a["id"] not in excluded]
        return chosen, "all accounts"

    matchers = [p.strip() for p in spec.split(",") if p.strip()]
    chosen, seen = [], set()
    for m in matchers:
        hits = [a for a in accounts if _matches(a, m)]
        if not hits:
            die(f"no open account matches '{m}'. Run `wst accounts` to list them.")
        for a in hits:
            # An explicitly named id bypasses exclude_accounts; fuzzy matches don't.
            if a["id"] in excluded and m.lower() != (a["id"] or "").lower():
                continue
            if a["id"] not in seen:
                seen.add(a["id"])
                chosen.append(a)
    return chosen, spec


def fetch_positions(currency="CAD"):
    api = load_api()
    return api.do_graphql_query(
        "FetchIdentityPositions",
        {
            "identityId": api.get_token_info().get("identity_canonical_id"),
            "currency": currency,
            "filter": {"securityIds": None},
            "includeAccountData": True,
            "includeSecurity": True,
        },
        "identity.financials.current.positions.edges",
        "array",
    )


def _money(node, key):
    try:
        return float(node[key]["amount"])
    except (KeyError, TypeError, ValueError):
        return 0.0


def normalize_rows(positions, account_ids, buckets):
    """Flatten positions into per-holding rows for the selected accounts."""
    rows = []
    wanted = set(account_ids)
    for p in positions:
        node = p.get("node", p)
        aids = [a.get("id") for a in (node.get("accounts") or [])]
        aid = next((i for i in aids if i in wanted), None)
        if aid is None:
            continue
        st = (node.get("security") or {}).get("stock") or {}
        sym = st.get("symbol") or (node.get("security") or {}).get("securityType", "?")
        name = st.get("name") or sym
        val = _money(node, "totalValue")
        book = _money(node, "bookValue")
        pnl = _money(node, "unrealizedReturns")
        rows.append(
            {
                "account_id": aid,
                "sym": sym,
                "name": name,
                "value": val,
                "pnl_pct": (pnl / book * 100) if book else 0.0,
                "sector": buckets.get(sym, "Unclassified"),
            }
        )
    return rows


def account_nlv(account_id, currency="CAD"):
    api = load_api()
    res = api.get_identity_current_financials(currency, account_ids=[account_id])
    return _extract_nlv(res)


def _extract_nlv(fin):
    if isinstance(fin, dict):
        for key in ("netLiquidationValueV2", "netLiquidationValue",
                    "net_liquidation_value", "nlv", "totalValue", "netWorth"):
            v = fin.get(key)
            if isinstance(v, dict) and "amount" in v:
                return float(v["amount"])
            if isinstance(v, (int, float)):
                return float(v)
        for v in fin.values():
            r = _extract_nlv(v)
            if r:
                return r
    elif isinstance(fin, list):
        for v in fin:
            r = _extract_nlv(v)
            if r:
                return r
    return 0.0


def display_label(accounts):
    """Human labels for accounts, deduplicated."""
    labels = {}
    seen = {}
    for a in accounts:
        base = a.get("description") or a.get("type") or a["id"]
        label = base
        n = 2
        while label in seen:
            label = f"{base} ({a.get('currency', '')} #{n})"
            n += 1
        seen[label] = a["id"]
        labels[a["id"]] = label
    return labels
