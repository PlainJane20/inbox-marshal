"""
Executes the standardized List-Unsubscribe mechanism (RFC 8058) — the same
thing Gmail's own "Unsubscribe" button uses. Deliberately does NOT parse
arbitrary unsubscribe links out of email bodies; only the standardized
header is trusted, because a hand-parsed link from email HTML is exactly
the kind of thing a malicious sender can spoof to look legitimate.

Only ever called for emails already classified as "marketing_spam", and
only after the user has explicitly confirmed — see run_agent.py. Sending
an unsubscribe request is a real, non-reversible action against a
third-party service, not something this tool ever does silently.
"""

import base64
import re

import requests


def parse_list_unsubscribe(header_value: str, post_header: str = "") -> dict:
    """Returns {"method": "http"|"mailto"|None, "target": str}."""
    if not header_value:
        return {"method": None, "target": None}

    urls = re.findall(r"<([^>]+)>", header_value)
    http_url = next((u for u in urls if u.startswith("http")), None)
    mailto = next((u for u in urls if u.startswith("mailto:")), None)

    # One-click (RFC 8058) requires the List-Unsubscribe-Post header to be
    # present — without it, the HTTP link may require additional user
    # interaction on the sender's page and shouldn't be auto-POSTed.
    if http_url and "one-click" in post_header.lower():
        return {"method": "http", "target": http_url}
    if mailto:
        return {"method": "mailto", "target": mailto}
    return {"method": None, "target": None}


def execute_http_unsubscribe(url: str) -> bool:
    try:
        resp = requests.post(url, timeout=10, headers={"List-Unsubscribe": "One-Click"})
        return resp.status_code < 400
    except requests.RequestException:
        return False


def execute_mailto_unsubscribe(service, mailto_url: str) -> bool:
    """Sends the unsubscribe email via the Gmail API (requires gmail.send)."""
    address = mailto_url.replace("mailto:", "").split("?")[0]
    message = f"To: {address}\r\nSubject: unsubscribe\r\n\r\nunsubscribe"
    raw = base64.urlsafe_b64encode(message.encode()).decode()
    try:
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except Exception:
        return False
