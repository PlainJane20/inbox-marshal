---
name: inbox-marshal
description: Runs the Inbox Marshal Gmail cleanup tool on demand — scans the inbox for spam, receipts, subscriptions/bills, and security alerts, and files them into real Gmail folders (archive + label, never delete). Use this whenever the user asks to run their inbox scan, clean up their email, check their email for spam, tidy their inbox, do their daily/weekly email cleanup, or run inbox marshal — even in casual phrasing like "can you clean out the junk in my gmail" or "check my inbox for spam again." Do NOT use this for general email tasks like drafting, sending, replying to a specific email, or answering questions about the content of a particular email — this skill only triggers the Inbox Marshal filing tool itself, nothing else.
---

# Inbox Marshal — on-demand run

This skill lives inside the Inbox Marshal repository itself. Before
running anything, find the repository root — the directory containing
`run_agent.py`, `config.yaml`, and this `.claude/` folder — and run all
commands from there.

Inbox Marshal classifies recent mail with Claude and files it into real
Gmail labels — it never permanently deletes anything; the strongest action
it ever takes is archive + label. The user reviews and deletes from the
actual Gmail folder themselves, on their own terms. Keep that safety model
in mind throughout: this skill's job is to run the tool and report back
clearly, not to work around any of its guardrails.

## Running a normal cleanup

This is the default for any general "run my inbox scan" / "clean up my
email" request — it's non-destructive and never blocks on a prompt, so
just run it:

```bash
source venv/bin/activate
python3 run_agent.py --auto
```

This archives spam and labels receipts/bills/security-alerts automatically.
It never sends an unsubscribe request and never deletes anything — those
are separate, higher-stakes actions that stay manual (see below).

After it finishes, report back conversationally:
- How many items were filed, broken out by category (e.g. "6 spam archived,
  2 receipts labeled, 13 security alerts labeled")
- The full **"Needs your attention"** list, verbatim, every time. These are
  intentionally never auto-filed — they're the emails that actually need a
  human read (personal correspondence, unresolved requests, real
  decisions), and burying that list defeats the point of running this at
  all.

If credentials are missing (`credentials.json`, `token.json`, or `.env` not
found in the repo), don't try to create them — tell the user to follow the
Setup section in the README, since that involves their own Google Cloud
project and can't be automated from here.

## If the user also wants to unsubscribe

Only do this when the user explicitly asks for it — e.g. "run my inbox
scan and unsubscribe from the marketing stuff," not implied by a plain
"clean up my email." Unsubscribing sends a real request to a third party,
which is a different risk tier than filing mail into a folder, so it needs
its own explicit ask and its own explicit confirmation:

```bash
python3 run_agent.py --apply
```

This runs interactively. When it reaches the label/archive confirmation,
answer `y` (that part is the same safe filing as `--auto`). When it then
lists senders with a real unsubscribe mechanism and asks "Unsubscribe from
all of these? [y/N]" — **stop and show the user that exact sender list in
chat first.** Only answer `y` to that prompt after they've actually said
yes to it. Never pre-confirm this step on their behalf, even if they asked
you to "clean up and unsubscribe" up front — the specific list of senders
is the thing they're actually approving, and that list doesn't exist until
the scan runs.

## What this skill must never do

- Never delete anything directly via the Gmail API, and never suggest a
  workaround to make `--auto` or `--apply` delete instead of archive. The
  archive-only behavior is a deliberate safety property of the tool, not a
  limitation to route around.
- Never invent or approve an unsubscribe list on the user's behalf.
- Never modify `config.yaml`'s `trusted_domains` list without the user
  explicitly telling you what to add — that list is a hard safety floor
  independent of the classifier, and it should only ever grow by the
  user's own explicit instruction.
