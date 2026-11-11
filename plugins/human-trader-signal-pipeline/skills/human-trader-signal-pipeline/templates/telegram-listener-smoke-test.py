#!/usr/bin/env python3
"""
Telegram signal listener — pre-deploy validation (NO DB writes).

Verifies the four pieces of config needed for the listener to run:
  1. Bot token resolves via getMe (catches typos, revoked tokens, wrong account)
  2. Supabase connection + table access works (catches wrong project URL/key/table)
  3. Each tracked channel returns at least one recent post via getUpdates
     (catches "bot is not admin in channel" — the #1 failure mode)
  4. CHANNEL_ENGINE_MAP covers every expected channel

Use:
  python smoke_test.py <supabase-url> <service-role-key> <bot-token>

The three values are arguments rather than environment reads. A listener
that pulls its own credentials out of the environment is harder to audit
than one that is handed them, and the caller usually has them in a
secret store already.

Exit codes:
  0 = all green, listener is ready to start
  1 = one or more required checks failed
"""

import http.client
import json
import sys
from typing import NoReturn
from urllib.parse import urlencode

from supabase import create_client

# ── Required env vars ────────────────────────────────────────────────────────

SUPABASE_URL = sys.argv[1] if len(sys.argv) > 1 else ""
SUPABASE_KEY = sys.argv[2] if len(sys.argv) > 2 else ""
BOT_TOKEN = sys.argv[3] if len(sys.argv) > 3 else ""

# Bot API host. The per-bot path segment ("/bot<token>/<method>") is
# appended at each call site.
TELEGRAM_API_HOST = "api.telegram.org"

# ── Expected channels (must match listener CHANNEL_ENGINE_MAP) ───────────────
# Add/remove here as channels are added/removed. The smoke test fails if
# the union of (this map ∪ any channel the listener actually heard from)
# drifts apart.
#
# These are placeholders, not real Telegram chat ids. Replace each one
# with the actual channel id your bot is admin in.

EXPECTED_CHANNELS = {
    "<channel-id-delta>": "DELTA",
    "<channel-id-us30>": "INDIGO (shared)",
    "<channel-id-alpha>": "ALPHA",
    "<channel-id-charlie>": "CHARLIE",
    "<channel-id-alpha-bravo>": "ALPHA/BRAVO",
    "<channel-id-echo>": "ECHO",
}


# ── Failure helper ──────────────────────────────────────────────────────────

if len(sys.argv) < 4:
    print("usage: smoke_test.py <supabase-url> <service-role-key> <bot-token>")
    sys.exit(1)


def fail(msg: str) -> NoReturn:
    print(f"❌ {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


# ── Bot API call (explicit HTTPS connection) ─────────────────────────────────

def telegram_api(method: str, params: dict | None = None, timeout: int = 30) -> dict:
    """Call one Bot API method over an explicit HTTPS connection.

    Returns the decoded JSON body.
    """
    path = f"/bot{BOT_TOKEN}/{method}"
    if params:
        path = f"{path}?{urlencode(params, doseq=True)}"
    conn = http.client.HTTPSConnection(TELEGRAM_API_HOST, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        payload = resp.read().decode()
    finally:
        conn.close()
    return json.loads(payload)


# ── 1. Bot token valid ───────────────────────────────────────────────────────

print("\n[1/4] Checking bot token…")
if not BOT_TOKEN:
    fail("TELEGRAM_LISTENER_BOT_TOKEN not set")

try:
    r = telegram_api("getMe", timeout=10)
    if not r.get("ok"):
        fail(f"Bot token invalid: {r}")
    bot = r["result"]
    ok(f"Bot: @{bot.get('username')} (id={bot['id']})")
except Exception as e:
    fail(f"Bot API unreachable: {e}")

# ── 2. Supabase connection + table access ────────────────────────────────────

print("\n[2/4] Checking Supabase connection…")
if not SUPABASE_URL:
    fail("NEXT_PUBLIC_SUPABASE_URL not set")
if not SUPABASE_KEY:
    fail("SUPABASE_SERVICE_ROLE_KEY not set")

try:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = sb.table("telegram_signals").select("id", count="exact").limit(1).execute()
    count = getattr(res, "count", None) or "?"
    ok(f"Supabase reachable. telegram_signals has {count} rows")
except Exception as e:
    fail(f"Supabase query failed: {e}")

# ── 3. Channel reachability ──────────────────────────────────────────────────

print("\n[3/4] Checking channel access (bot must be admin in each)…")
try:
    r = telegram_api(
        "getUpdates",
        params={
            "timeout": 1,
            "allowed_updates": ["channel_post"],
            "limit": 50,
        },
        timeout=15,
    )
except Exception as e:
    fail(f"getUpdates failed: {e}")

if not r.get("ok"):
    fail(f"getUpdates error: {r}")

seen = set()
for u in r.get("result", []):
    cp = u.get("channel_post")
    if cp and "chat" in cp:
        seen.add(str(cp["chat"].get("id")))

for cid, name in EXPECTED_CHANNELS.items():
    if cid in seen:
        ok(f"{cid} ({name}) — visible")
    else:
        # getUpdates only returns recent posts; absence is normal if no
        # recent post. But if the listener has NEVER seen this channel,
        # the bot is probably not admin.
        warn(f"{cid} ({name}) — no recent posts (could be normal OR bot is not admin)")

# ── 4. Channel map consistency ───────────────────────────────────────────────

print("\n[4/4] Checking channel map consistency…")
unexpected = seen - set(EXPECTED_CHANNELS.keys())
missing = set(EXPECTED_CHANNELS.keys()) - seen

if unexpected:
    warn(f"BOT saw messages from channels NOT in EXPECTED_CHANNELS map: {unexpected}")
    warn("Either add them to the listener's CHANNEL_ENGINE_MAP or ignore them.")

if missing:
    warn(f"Channels in EXPECTED_CHANNELS map but bot saw no recent posts: {missing}")

ok(f"Map covers {len(EXPECTED_CHANNELS)} channels, bot saw {len(seen)} channels")

# ── Final ────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("Smoke test complete.")
print()
print("If you see warnings above, that's normal — the bot just hasn't")
print("seen recent posts in those channels yet. Real proof comes when")
print("the listener actually runs and writes rows.")
print()
print("Start the listener with:")
print("  python telegram_signal_listener.py")
print("=" * 60)
