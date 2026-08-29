#!/usr/bin/env python3
"""Fetch Gmail message bodies, stripped, outside the context window.

`inbox-triage` used to read bodies through the Gmail MCP server, which returns
the raw payload. One Indeed message came back at 55,491 characters -- large
enough to overflow the tool-result cap and spill to disk -- of which around
1,700 were words. Across a run that was ~100-140k tokens spent on markup.

This does the same fetch over Bash and prints only what a reader would see, so
the HTML never enters the context at all. Batch the ids: one invocation per ~30
messages amortises the per-call overhead that made even short messages costly.

    python3 scripts/read_mail.py --account primary <id> <id> ...
    python3 scripts/read_mail.py --account alt --format json <id>

Reuses the OAuth refresh tokens the Gmail MCP server already holds in
~/.gmail-mcp/. No new auth flow, and nothing is written back to the mailbox.
"""

import argparse
import base64
import json
import os
import sys
import warnings

# google.api_core warns about the Python version on every import. The point
# of this script is to keep its output small.
warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.triage_rules import strip_html, strip_quoted_chain  # noqa: E402

MCP_DIR = os.path.expanduser("~/.gmail-mcp")
OAUTH_KEYS = os.path.join(MCP_DIR, "gcp-oauth.keys.json")

# The two inboxes keep separate token files; `gmail_alt` overrides
# GMAIL_CREDENTIALS_PATH to the second one in .mcp.json.
ACCOUNTS = {
    "primary": os.path.join(MCP_DIR, "credentials.json"),
    "alt": os.path.join(MCP_DIR, "credentials-alt.json"),
}

WANTED_HEADERS = ("From", "To", "Subject", "Date")


def _service(account):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = ACCOUNTS[account]
    if not os.path.exists(token_path):
        raise SystemExit(f"no credentials for account '{account}' at {token_path}")

    with open(token_path, encoding="utf-8") as fh:
        token = json.load(fh)
    with open(OAUTH_KEYS, encoding="utf-8") as fh:
        keys = json.load(fh)
    app = keys.get("installed") or keys.get("web") or {}

    creds = Credentials(
        token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        token_uri=app.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=app.get("client_id"),
        client_secret=app.get("client_secret"),
        scopes=(token.get("scope") or "").split() or None,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _walk(part):
    """Yield every leaf part, depth-first."""
    if not part:
        return
    subparts = part.get("parts")
    if subparts:
        for sub in subparts:
            yield from _walk(sub)
    else:
        yield part


def _decode(part):
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data.encode("ascii") + b"==")
    return raw.decode("utf-8", errors="replace")


def extract_body(payload):
    """Prefer text/plain; fall back to text/html through the stripper.

    Multipart/alternative carries both, and the plain part is what the sender's
    client generated rather than what we can salvage from markup -- so it is
    both cheaper and more faithful. Some senders ship only HTML.
    """
    plain, htmls = [], []
    for part in _walk(payload):
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            plain.append(_decode(part))
        elif mime == "text/html":
            htmls.append(_decode(part))

    if any(p.strip() for p in plain):
        return strip_html("\n".join(plain))
    if htmls:
        return strip_html("\n".join(htmls))
    return ""


def fetch(service, message_id):
    msg = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()
    payload = msg.get("payload") or {}
    headers = {
        h["name"].title(): h["value"]
        for h in payload.get("headers", [])
        if h.get("name", "").title() in WANTED_HEADERS
    }
    body = strip_quoted_chain(extract_body(payload))
    return {
        "id": msg.get("id", message_id),
        "thread_id": msg.get("threadId", ""),
        "labels": msg.get("labelIds", []),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "body": body,
    }


def render(rec):
    return "\n".join(
        [
            "=" * 60,
            f"Message ID: {rec['id']}",
            f"Thread ID: {rec['thread_id']}",
            f"From: {rec['from']}",
            f"Subject: {rec['subject']}",
            f"Date: {rec['date']}",
            f"Labels: {', '.join(rec['labels'])}",
            "-" * 60,
            rec["body"],
        ]
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--account", choices=sorted(ACCOUNTS), default="primary")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("ids", nargs="+", metavar="MESSAGE_ID")
    args = ap.parse_args(argv)

    service = _service(args.account)

    out, failures = [], 0
    for message_id in args.ids:
        try:
            out.append(fetch(service, message_id))
        except Exception as exc:  # one bad id must not abort the batch
            failures += 1
            out.append({"id": message_id, "error": f"{type(exc).__name__}: {exc}"})

    if args.format == "json":
        print(json.dumps(out, indent=2))
    else:
        for rec in out:
            if "error" in rec:
                print(f"{'=' * 60}\nMessage ID: {rec['id']}\nERROR: {rec['error']}")
            else:
                print(render(rec))

    return 1 if failures == len(args.ids) else 0


if __name__ == "__main__":
    sys.exit(main())
