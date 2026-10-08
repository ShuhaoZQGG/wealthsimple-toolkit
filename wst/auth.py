"""Session handling. Credentials are only ever read from env vars for the
one-time `wst login` and are never written to disk or logs."""

import json
import os
import sys

SESSION_DIR = os.path.expanduser("~/.config/wst")
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")
READ_ONLY_SCOPE = "invest.read trade.read tax.read"


def _lib():
    try:
        from ws_api import (  # noqa: F401
            WealthsimpleAPI,
            WSAPISession,
            ManualLoginRequired,
            OTPRequiredException,
            LoginFailedException,
        )
        import ws_api

        return ws_api
    except ImportError:
        print(
            "wst: error: the 'ws-api' package is not installed. "
            "Run: pip install -e .",
            file=sys.stderr,
        )
        sys.exit(1)


def die(msg, code=1):
    print(f"wst: error: {msg}", file=sys.stderr)
    sys.exit(code)


def persist_session(sess_json, username):
    os.makedirs(SESSION_DIR, mode=0o700, exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        f.write(sess_json)
    os.chmod(SESSION_FILE, 0o600)


def load_api():
    ws_api = _lib()
    if not os.path.exists(SESSION_FILE):
        die(f"no session. Run `wst login` first (WS_USERNAME / WS_PASSWORD env vars).")
    with open(SESSION_FILE) as f:
        sess = ws_api.WSAPISession.from_json(f.read())
    try:
        return ws_api.WealthsimpleAPI.from_token(sess, persist_session)
    except ws_api.ManualLoginRequired as e:
        die(f"session invalid ({e}). Run `wst login` again.")
    except Exception as e:
        die(f"could not reach Wealthsimple ({e}). Retry; re-login only if it persists.")


def cmd_login(args):
    ws_api = _lib()
    username = os.environ.get("WS_USERNAME", "").strip()
    password = os.environ.get("WS_PASSWORD", "")
    otp = os.environ.get("WS_OTP") or None
    if not username or not password:
        die(
            "set WS_USERNAME and WS_PASSWORD env vars, then re-run. "
            "Add WS_OTP if Wealthsimple asks for a 2FA code."
        )
    try:
        ws_api.WealthsimpleAPI.login(
            username,
            password,
            otp,
            persist_session_fct=persist_session,
            scope=READ_ONLY_SCOPE,
        )
    except ws_api.OTPRequiredException:
        die("Wealthsimple wants a 2FA code: re-run with WS_OTP set.", code=2)
    except ws_api.LoginFailedException as e:
        die(f"login failed: {e}")
    print(json.dumps({"ok": True, "session": SESSION_FILE}))
