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
    from getpass import getpass

    ws_api = _lib()
    username = os.environ.get("WS_USERNAME", "").strip()
    if not username:
        username = input("Wealthsimple username (email): ").strip()
    if not username:
        die("no username given")
    password = os.environ.get("WS_PASSWORD", "")
    if not password:
        # getpass, not input(): input() echoes the password to the terminal.
        password = getpass("Wealthsimple password: ")
    otp = os.environ.get("WS_OTP") or None

    def attempt(otp_answer):
        ws_api.WealthsimpleAPI.login(
            username,
            password,
            otp_answer,
            persist_session_fct=persist_session,
            scope=READ_ONLY_SCOPE,
        )

    try:
        attempt(otp)
    except ws_api.OTPRequiredException:
        if otp is not None:
            die("Wealthsimple wants a 2FA code: re-run with WS_OTP set.", code=2)
        otp = input("2FA code: ").strip()
        try:
            attempt(otp)
        except ws_api.OTPRequiredException:
            die("2FA code was rejected or expired.", code=2)
        except ws_api.LoginFailedException as e:
            die(f"login failed: {e}")
    except ws_api.LoginFailedException as e:
        die(f"login failed: {e}")
    # Prove the stored session actually works for API calls.
    api = load_api()
    n = len(api.get_accounts())
    if getattr(args, "export_session", None):
        # Re-read: the API load above may have refreshed the token and re-persisted it.
        with open(SESSION_FILE) as f:
            stored = f.read()
        fd = os.open(args.export_session, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(stored)
        os.chmod(args.export_session, 0o600)
        print(f"Session also written to {args.export_session} (mode 0600).")
    print(json.dumps({"ok": True, "session": SESSION_FILE, "open_accounts": n}))
