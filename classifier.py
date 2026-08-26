"""
Claude-based email classification via a forced tool call — structured
output, not prose to re-parse. The category directly determines what
action gets taken later (run_agent.py), so precision here matters more
than in almost any other agent in this style of tool: a misclassified
"malicious_spam" that's actually a real bank alert would get archived out
of sight, which is a real, tangible harm to the user, not just an
annoying miscategorization.
"""

import anthropic

CLASSIFY_TOOL = {
    "name": "classify_email",
    "description": "Classify this email and extract relevant structured fields.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "malicious_spam", "marketing_spam", "payment_receipt",
                    "subscription_bill", "security_alert", "needs_attention", "leave_alone",
                ],
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reasoning": {"type": "string", "description": "One sentence on why this category, citing specific content"},
            "vendor": {"type": "string", "description": "For receipts/bills only: the merchant/service name"},
            "amount": {"type": "string", "description": "For receipts/bills only: the charged amount with currency symbol, e.g. '$14.99'"},
            "billing_frequency": {"type": "string", "enum": ["one_time", "monthly", "annual", "unknown"]},
            "order_number": {"type": "string", "description": "The order/confirmation/tracking number if the email states one, exactly as written — leave out entirely if none is present, don't guess"},
        },
        "required": ["category", "confidence", "reasoning"],
    },
}

SYSTEM_PROMPT = """You are classifying a personal email for an inbox
organization tool. Be conservative — a wrong "malicious_spam" or
"marketing_spam" call means this email gets archived out of the person's
sight, so when genuinely uncertain, prefer "needs_attention" or
"leave_alone" over guessing toward a more aggressive category.

Categories:
- malicious_spam: phishing, scams, fake urgency ("your account will be
  closed"), fake delivery/invoice notices with a suspicious link, anything
  impersonating a real company to extract credentials or payment. NEVER
  suggest unsubscribing from these — clicking anything in a malicious email
  confirms the address is active and invites more.
- marketing_spam: legitimate newsletters, promotions, marketing email from
  a real company/list the person may have signed up for once and no longer
  wants. Safe to unsubscribe from via a real List-Unsubscribe mechanism.
- payment_receipt: a one-time purchase confirmation or receipt.
- subscription_bill: a recurring subscription charge or bill notice.
- security_alert: a genuine account security notification (new sign-in,
  password changed, 2FA code) from a real service the person actually
  uses — NOT a phishing email impersonating one. This is high-signal, keep
  it visible, never archive it.
- needs_attention: appears to be a real, personal, non-automated email
  that likely needs a human response.
- leave_alone: anything else — don't touch it.

If this is a receipt or bill, extract vendor/amount/billing_frequency, and
order_number if the email states one exactly (order #, confirmation #,
tracking #). If it's any other category, leave those fields out entirely
rather than guessing values.
"""


def classify_email(email: dict, api_key: str, model: str = "claude-sonnet-5") -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    content = f"""From: {email['sender']}
Subject: {email['subject']}
Has List-Unsubscribe header: {bool(email.get('list_unsubscribe'))}

Body (truncated):
{email['body'] or email['snippet']}
"""

    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_email"},
        messages=[{"role": "user", "content": content}],
    )

    valid_categories = set(CLASSIFY_TOOL["input_schema"]["properties"]["category"]["enum"])

    for block in msg.content:
        if block.type == "tool_use" and block.name == "classify_email":
            result = block.input
            # Same lesson, confirmed repeatedly across this body of work: a
            # forced schema does not guarantee every field is populated or
            # correctly typed. An absent or invalid "category" must fail
            # safe to the least destructive option, never the most
            # aggressive one — this is a case where guessing wrong is
            # actively worse than not guessing at all.
            if not isinstance(result, dict) or result.get("category") not in valid_categories:
                return {"category": "leave_alone", "confidence": "low",
                        "reasoning": "Malformed classifier output — failing safe to leave_alone."}
            return result

    return {"category": "leave_alone", "confidence": "low", "reasoning": "No tool call returned — failing safe."}
