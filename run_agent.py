#!/usr/bin/env python3
"""
Inbox Marshal — spam cleanup + receipt/subscription organization for Gmail.

Usage:
  python run_agent.py --scan              # dry run — shows what would happen, changes nothing
  python run_agent.py --apply             # scans, shows the plan, asks to confirm, then executes
                                           # (includes the interactive unsubscribe step)
  python run_agent.py --auto              # for scheduled/unattended runs (e.g. launchd, 3x/day):
                                           # files spam/receipts automatically, no prompts,
                                           # NEVER unsubscribes, posts a macOS notification + report file

Safety model:
  - Never permanently deletes anything, in any mode. The strongest action is
    archive + label — the labels are real Gmail folders you browse and
    delete from yourself, on your own terms, using Gmail's own UI.
  - Unsubscribe only ever runs via --apply's explicit, per-sender
    confirmation. --auto never sends anything to anyone.
  - Domains in config.yaml's trusted_domains are never touched, regardless
    of what the classifier says — a hard floor independent of the model.
  - Every batch of actions is shown in full before --apply executes.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv(Path(__file__).parent / ".env")

from gmail_auth import get_gmail_service
from gmail_client import (apply_label_and_archive, apply_label_only,
                           ensure_label, fetch_recent_messages, get_message_detail)
from classifier import classify_email
from unsubscribe import execute_http_unsubscribe, execute_mailto_unsubscribe, parse_list_unsubscribe
from notify import send_macos_notification

console = Console()

ARCHIVE_CATEGORIES = {"malicious_spam", "marketing_spam"}
LABEL_ONLY_CATEGORIES = {"payment_receipt", "subscription_bill", "security_alert"}
ACTION_DESC = {
    "malicious_spam": "Archive + label (no unsubscribe)",
    "marketing_spam": "Archive + label, unsubscribe if a real mechanism exists (--apply only)",
    "payment_receipt": "Label only, stays in inbox",
    "subscription_bill": "Label only, stays in inbox",
    "security_alert": "Label only, stays in inbox — never archived",
    "needs_attention": "No action — flagged for you",
    "leave_alone": "No action",
}


def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)


def is_trusted(email: dict, trusted_domains: list) -> bool:
    return any(email["sender_domain"].endswith(d) for d in trusted_domains)


def scan(service, cfg: dict, api_key: str) -> dict:
    console.print(f"[bold cyan]Fetching last {cfg['lookback_days']} days of mail...[/]")
    message_refs = fetch_recent_messages(service, cfg["lookback_days"])
    console.print(f"  {len(message_refs)} messages found")

    plan = {cat: [] for cat in ["malicious_spam", "marketing_spam", "payment_receipt",
                                 "subscription_bill", "security_alert", "needs_attention", "leave_alone"]}
    for ref in message_refs:
        email = get_message_detail(service, ref["id"])
        if is_trusted(email, cfg["trusted_domains"]):
            plan["leave_alone"].append({**email, "classification": {"category": "leave_alone", "reasoning": "trusted domain"}})
            continue
        classification = classify_email(email, api_key, cfg["claude_model"])
        plan[classification["category"]].append({**email, "classification": classification})
    return plan


def print_report(plan: dict, verbose: bool):
    table = Table(title="Inbox Marshal — Scan Results", show_header=True, header_style="bold dim")
    table.add_column("Category")
    table.add_column("Count", justify="right")
    table.add_column("Action")
    for cat, items in plan.items():
        if items:
            table.add_row(cat, str(len(items)), ACTION_DESC[cat])
    console.print(table)

    if verbose:
        for cat, items in plan.items():
            if not items:
                continue
            console.print(f"\n[bold]{cat}:[/]")
            for e in items:
                reason = e["classification"].get("reasoning", "")
                console.print(f"  - {e['sender']} — \"{e['subject']}\"")
                if reason:
                    console.print(f"      [dim]{reason}[/]")

    subs = [e for e in plan["subscription_bill"] if e["classification"].get("amount")]
    if subs:
        console.print("\n[bold]Subscriptions/bills found:[/]")
        for e in subs:
            c = e["classification"]
            console.print(f"  {c.get('vendor', '?')}: {c.get('amount', '?')} ({c.get('billing_frequency', 'unknown')})")

    orders = [e for e in plan["payment_receipt"] + plan["subscription_bill"] if e["classification"].get("order_number")]
    if orders:
        console.print("\n[bold]Order/confirmation numbers found:[/]")
        for e in orders:
            c = e["classification"]
            console.print(f"  {c.get('vendor', e['sender'])}: order #{c['order_number']} — \"{e['subject']}\"")

    if plan["needs_attention"]:
        console.print("\n[bold yellow]Needs your attention:[/]")
        for e in plan["needs_attention"]:
            console.print(f"  {e['sender']}: {e['subject']}")


def render_markdown_report(plan: dict) -> str:
    lines = [f"# Inbox Marshal Report — {datetime.now().strftime('%A, %B %-d, %Y %-I:%M %p')}", ""]
    for cat, items in plan.items():
        if not items:
            continue
        lines.append(f"## {cat} ({len(items)})")
        for e in items:
            c = e["classification"]
            lines.append(f"- **{e['sender']}** — \"{e['subject']}\"")
            if c.get("order_number"):
                lines.append(f"  - **Order #{c['order_number']}**" + (f" — {c.get('amount')}" if c.get("amount") else ""))
            if c.get("reasoning"):
                lines.append(f"  - {c['reasoning']}")
        lines.append("")
    return "\n".join(lines)


def apply_labels(service, cfg: dict, plan: dict) -> int:
    label_ids = {cat: ensure_label(service, name) for cat, name in cfg["labels"].items()}
    total = 0
    for cat in ARCHIVE_CATEGORIES:
        for e in plan[cat]:
            apply_label_and_archive(service, e["id"], label_ids[cat])
            total += 1
    for cat in LABEL_ONLY_CATEGORIES:
        for e in plan[cat]:
            apply_label_only(service, e["id"], label_ids[cat])
            total += 1
    return total


def main():
    parser = argparse.ArgumentParser(description="Inbox Marshal")
    parser.add_argument("--scan", action="store_true", help="Dry run only")
    parser.add_argument("--apply", action="store_true", help="Scan, then confirm and execute (includes unsubscribe step)")
    parser.add_argument("--auto", action="store_true", help="Unattended: files automatically, never unsubscribes, notifies")
    parser.add_argument("--verbose", action="store_true", help="List every email under each category, not just counts")
    args = parser.parse_args()

    if not any([args.scan, args.apply, args.auto]):
        console.print("[yellow]Specify --scan, --apply, or --auto[/]")
        sys.exit(0)

    cfg = load_config()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]Missing ANTHROPIC_API_KEY[/]")
        sys.exit(1)

    console.print("[bold cyan]Connecting to Gmail...[/]")
    service = get_gmail_service(cfg["credentials_path"], cfg["token_path"])

    plan = scan(service, cfg, api_key)
    print_report(plan, args.verbose)

    if args.scan:
        console.print("\n[dim]Dry run only — nothing was changed. Run with --apply or --auto to execute.[/]")
        return

    if args.auto:
        total = apply_labels(service, cfg, plan)
        report_path = Path(cfg.get("report_path", "~/inbox-marshal-report.md")).expanduser()
        report_path.write_text(render_markdown_report(plan))

        spam_count = len(plan["malicious_spam"]) + len(plan["marketing_spam"])
        receipt_count = len(plan["payment_receipt"]) + len(plan["subscription_bill"])
        attention_count = len(plan["needs_attention"])
        summary = f"{spam_count} spam filed, {receipt_count} receipts labeled, {attention_count} need your attention"

        console.print(f"[green]✓[/] {total} email(s) filed. Report saved to {report_path}")
        if cfg.get("notify_macos", True):
            send_macos_notification("Inbox Marshal", summary)
        return

    # ── --apply ──
    total_actions = sum(len(plan[c]) for c in ARCHIVE_CATEGORIES | LABEL_ONLY_CATEGORIES)
    if total_actions == 0:
        console.print("\n[green]Nothing to do.[/]")
        return

    answer = input(f"\nProceed with {total_actions} label/archive action(s) above? [y/N] ").strip().lower()
    if answer != "y":
        console.print("[yellow]Cancelled — nothing changed.[/]")
        return

    apply_labels(service, cfg, plan)
    console.print(f"[green]✓[/] Applied labels/archived {total_actions} email(s)")

    unsub_candidates = []
    for e in plan["marketing_spam"]:
        parsed = parse_list_unsubscribe(e.get("list_unsubscribe", ""), e.get("list_unsubscribe_post", ""))
        if parsed["method"]:
            unsub_candidates.append((e, parsed))

    if unsub_candidates:
        console.print(f"\n[bold]{len(unsub_candidates)} sender(s) have a real unsubscribe mechanism:[/]")
        for e, _ in unsub_candidates:
            console.print(f"  - {e['sender']}")
        answer = input("Unsubscribe from all of these? [y/N] ").strip().lower()
        if answer == "y":
            for e, parsed in unsub_candidates:
                ok = (execute_http_unsubscribe(parsed["target"]) if parsed["method"] == "http"
                      else execute_mailto_unsubscribe(service, parsed["target"]))
                console.print(f"  {'✓' if ok else '✗'} {e['sender']}")
        else:
            console.print("[yellow]Skipped unsubscribing — mail was still archived/labeled above.[/]")


if __name__ == "__main__":
    main()
