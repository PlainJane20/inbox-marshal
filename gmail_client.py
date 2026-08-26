"""Gmail read/organize operations — fetching, labeling, archiving. No
sending or deleting logic lives here; see unsubscribe.py for the one
send-capable action, which is gated separately."""

import base64
import re
from datetime import datetime, timedelta, timezone


def fetch_recent_messages(service, lookback_days: int) -> list:
    """
    Deliberately does NOT restrict to `in:inbox`. Real-world testing found
    that Gmail's own tab categorization (Promotions/Social/Updates) often
    strips the INBOX label from marketing mail even while the user still
    considers it inbox clutter — an `in:inbox` query silently missed real
    spam (Groupon, Target promotional mail) that only carried a
    CATEGORY_PROMOTIONS label. Gmail's default search (no `in:` qualifier)
    already excludes Spam and Trash, which is exactly the scope this tool
    actually wants: everything that isn't already fully out of sight.
    """
    after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    query = f"after:{after}"

    messages = []
    page_token = None
    while True:
        resp = service.users().messages().list(userId="me", q=query, pageToken=page_token, maxResults=100).execute()
        messages.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return messages


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _extract_body_snippet(payload: dict, max_chars: int = 1500) -> str:
    """Pulls plain-text body content, falling back through multipart parts."""
    def walk(part):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        for sub in part.get("parts", []):
            result = walk(sub)
            if result:
                return result
        return ""

    text = walk(payload)
    return text[:max_chars]


def get_message_detail(service, msg_id: str) -> dict:
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = msg["payload"].get("headers", [])
    sender = _get_header(headers, "From")
    domain_match = re.search(r"@([\w.-]+)", sender)

    return {
        "id": msg_id,
        "sender": sender,
        "sender_domain": domain_match.group(1) if domain_match else "",
        "subject": _get_header(headers, "Subject"),
        "snippet": msg.get("snippet", ""),
        "body": _extract_body_snippet(msg["payload"]),
        "list_unsubscribe": _get_header(headers, "List-Unsubscribe"),
        "list_unsubscribe_post": _get_header(headers, "List-Unsubscribe-Post"),
    }


def ensure_label(service, label_name: str) -> str:
    """Returns the label ID, creating the label (and any parent path segments
    Gmail's '/' nesting implies) if it doesn't already exist."""
    resp = service.users().labels().list(userId="me").execute()
    for label in resp.get("labels", []):
        if label["name"] == label_name:
            return label["id"]

    created = service.users().labels().create(
        userId="me",
        body={"name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    return created["id"]


def apply_label_and_archive(service, msg_id: str, label_id: str):
    """Archives (removes INBOX) and applies the given label. Never deletes."""
    service.users().messages().modify(
        userId="me", id=msg_id,
        body={"addLabelIds": [label_id], "removeLabelIds": ["INBOX"]},
    ).execute()


def apply_label_only(service, msg_id: str, label_id: str):
    """Labels without archiving — used for security alerts and payment
    receipts/subscriptions, which should stay visible in the inbox."""
    service.users().messages().modify(
        userId="me", id=msg_id,
        body={"addLabelIds": [label_id]},
    ).execute()
