# wst — Wealthsimple holdings overview

Local-first portfolio overview for Wealthsimple: per-account % weights,
cross-account aggregates, and bucket (sector/theme) groupings — the views the
Wealthsimple app doesn't give you. Runs entirely on your machine; your
credentials never leave it.

> Unofficial API, read-only. Not affiliated with Wealthsimple. Wealthsimple can
> change its private API at any time, which would break this until updated.

## Install

```bash
git clone https://github.com/<you>/wealthsimple-holdings-overview
cd wealthsimple-holdings-overview
pip install -e .
```

## One-time login

```bash
WS_USERNAME='you@example.com' WS_PASSWORD='...' wst login
# if Wealthsimple asks for 2FA:
WS_USERNAME='...' WS_PASSWORD='...' WS_OTP='123456' wst login
```

This requests a **read-only** OAuth scope and stores only the session tokens at
`~/.config/wst/session.json` (0600). Your password is never written to disk.

## Usage

```bash
wst accounts                          # list your accounts (ids, types)
wst buckets --init                    # create ~/.config/wst/buckets.json from the template
wst buckets --autofill                # auto-classify holdings from shipped defaults
wst buckets --review                  # interactively classify the rest, one keystroke each
wst overview                          # every holding with % weights, per account + aggregate
wst overview --accounts tfsa,rrsp     # any subset: match by id, type, or description text
wst overview --group sector           # roll up by your buckets
wst overview --group sector --per-account
wst overview --reconcile               # holdings vs account NLV (coverage check)
wst pie -o holdings.html              # interactive pie chart — hover for detail, click to drill in
```

**AI invoke:** if you're using this with an AI assistant, just ask it to run
these commands — e.g. *"show me my sector breakdown"* or *"regenerate the pie
chart"*. The commands are the interface.

## Buckets

`wst buckets --init` copies `buckets.example.json` to
`~/.config/wst/buckets.json`. Map each ticker to whatever bucket you think in —
sectors, themes, strategies:

```json
{ "NVDA": "AI / semis", "JNJ": "Healthcare", "CASH.TO": "Cash-like" }
```

You don't start from zero: `wst buckets --autofill` pre-classifies your
holdings from the defaults shipped with the tool (all S&P 500 constituents
mapped to GICS sectors, plus ~70 common ETFs), and `wst buckets --review`
walks you through whatever is left — company name and a suggestion shown,
Enter to accept, or type your own bucket. The objective layer (sector) is
automated; the theme layer (your "Big tech vs SaaS" judgment) stays yours.

Symbols you haven't mapped show up as `Unclassified` so you can classify them.

## Config

`~/.config/wst/config.json` (all optional):

```json
{
  "exclude_accounts": ["non-registered-XXXX"],
  "scopes": {
    "personal": ["tfsa-XXXX", "rrsp-XXXX"],
    "family": ["non-registered-YYYY"]
  }
}
```

- `exclude_accounts`: ids hidden from `all` and fuzzy matchers (an explicitly
  named id still works).
- `scopes`: named account groups. Use with `wst overview --accounts personal`,
  and the pie chart renders one tab per scope.

## Caveats

- **Read-only by design.** The login scope is pinned to
  `invest.read trade.read tax.read`; the tool cannot trade, transfer, or
  withdraw.
- **Managed accounts are partially invisible.** Wealthsimple's API omits
  managed-portfolio positions, so those accounts may show $0 or under-report.
  `--reconcile` exposes the gap.
- **Residual cash is not a holding** and is excluded from weights; the
  coverage line from `--reconcile` tells you how much is missing.
- **Unofficial API.** This uses Wealthsimple's private GraphQL endpoints via
  the `ws-api` library. It works today; if Wealthsimple changes things, update
  the `ws-api` dependency.
