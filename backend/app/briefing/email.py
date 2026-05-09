"""Weekly brief email delivery — dormant by default.

This module is NOT called automatically by the orchestrator. Briefs are
delivered as PDFs on disk (data/briefs/) unless SMTP is explicitly configured.

To enable email delivery, set all SMTP_* env vars and BRIEF_RECIPIENTS in
.env.local, then call send_brief_email(brief_row) manually or wire it back
into the orchestrator for your deployment.

Config (env vars / .env.local):
    SMTP_HOST        — required to activate; delivery is skipped if absent
    SMTP_PORT        — default 587
    SMTP_USER        — SMTP login user
    SMTP_PASSWORD    — SMTP login password
    SMTP_FROM        — From address
    BRIEF_RECIPIENTS — comma-separated recipient addresses
"""

from __future__ import annotations

import asyncio
import smtplib
import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.models.brief import WeeklyBrief

log = structlog.get_logger(__name__)

# Minimal markdown→HTML transform sufficient for the brief's formatting.
# We don't pull in a full MD library — the brief uses only headers, bold, bullets.
_REPLACEMENTS = [
    # Section headers
    ("### ", "<h3>", "\n", "</h3>"),
    ("## ", "<h2>", "\n", "</h2>"),
    ("# ", "<h1>", "\n", "</h1>"),
]


def _md_to_html(text: str) -> str:
    """Very lightweight markdown → HTML for email rendering."""
    import re

    lines = []
    in_ul = False
    for raw in text.splitlines():
        line = raw

        # Fenced code blocks — wrap in pre
        if line.startswith("```"):
            lines.append(
                "<pre>" if not line[3:].strip() else f"<pre class='lang-{line[3:].strip()}'>"
            )
            continue

        # ATX headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if in_ul:
                lines.append("</ul>")
                in_ul = False
            level = len(m.group(1))
            content = _inline_md(m.group(2))
            lines.append(f"<h{level}>{content}</h{level}>")
            continue

        # Bullet points
        if re.match(r"^[-*]\s+", line):
            if not in_ul:
                lines.append("<ul>")
                in_ul = True
            content = _inline_md(line[2:].strip())
            lines.append(f"  <li>{content}</li>")
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$", line.strip()):
            if in_ul:
                lines.append("</ul>")
                in_ul = False
            lines.append("<hr>")
            continue

        # Empty line
        if not line.strip():
            if in_ul:
                lines.append("</ul>")
                in_ul = False
            lines.append("<br>")
            continue

        if in_ul:
            lines.append("</ul>")
            in_ul = False

        lines.append(f"<p>{_inline_md(line)}</p>")

    if in_ul:
        lines.append("</ul>")

    return "\n".join(lines)


def _inline_md(text: str) -> str:
    """Apply inline formatting: **bold**, *italic*, `code`, [score] brackets."""
    import re

    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    # Score badges like [0.87] → amber span
    text = re.sub(r"\[(\d+\.\d+)\]", r"<span class='score'>[\1]</span>", text)
    return text


def _build_html(brief: WeeklyBrief) -> str:
    body_html = _md_to_html(brief.brief_text)
    week = brief.week_ending.strftime("%-d %B %Y")
    cost = f"${brief.cost_usd:.4f}"

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>White Star — Weekly Brief {week}</title>
    <style>
      body {{
        background: #0e0e0e; color: #e2e2e2;
        font-family: 'Georgia', serif; font-size: 15px; line-height: 1.65;
        margin: 0; padding: 0;
      }}
      .wrap {{ max-width: 680px; margin: 0 auto; padding: 40px 24px 64px; }}
      .header {{
        border-bottom: 1px solid #2a2a2a;
        padding-bottom: 16px; margin-bottom: 32px;
        display: flex; align-items: baseline; justify-content: space-between;
      }}
      .wordmark {{
        font-style: italic; font-size: 22px; font-weight: 400;
        color: #e2e2e2; letter-spacing: 0.01em;
      }}
      .tagline {{
        font-family: 'Courier New', monospace; font-size: 9px;
        font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase;
        color: #555;
      }}
      h1 {{ font-size: 20px; font-weight: 400; color: #e2e2e2; margin-top: 0; }}
      h2 {{ font-size: 16px; font-weight: 600; color: #c9922a; margin-top: 32px; }}
      h3 {{ font-size: 14px; font-weight: 600; color: #a0a0a0;
            text-transform: uppercase; letter-spacing: 0.08em; margin-top: 24px; }}
      h4 {{ font-size: 13px; color: #888; margin-top: 16px; }}
      p {{ margin: 8px 0; color: #c8c8c8; }}
      ul {{ margin: 8px 0 16px 20px; padding: 0; }}
      li {{ margin: 4px 0; color: #c8c8c8; }}
      code {{
        font-family: 'Courier New', monospace; font-size: 12px;
        background: #1a1a1a; padding: 1px 5px; border-radius: 2px; color: #c9922a;
      }}
      pre {{
        background: #1a1a1a; padding: 12px 16px; border-radius: 2px;
        font-family: 'Courier New', monospace; font-size: 11px;
        overflow-x: auto; color: #a0a0a0;
      }}
      hr {{ border: none; border-top: 1px solid #2a2a2a; margin: 24px 0; }}
      .score {{ color: #c9922a; font-family: 'Courier New', monospace; font-size: 12px; }}
      strong {{ color: #e2e2e2; }}
      .footer {{
        border-top: 1px solid #2a2a2a; margin-top: 48px; padding-top: 16px;
        font-family: 'Courier New', monospace; font-size: 10px; color: #444;
      }}
    </style>
    </head>
    <body>
    <div class="wrap">
      <div class="header">
        <span class="wordmark">White Star</span>
        <span class="tagline">Market Intelligence</span>
      </div>
      {body_html}
      <div class="footer">
        Generated {week} &nbsp;·&nbsp; {brief.model_id} &nbsp;·&nbsp; {cost} API cost
      </div>
    </div>
    </body>
    </html>
    """)


def _build_plain(brief: WeeklyBrief) -> str:
    """Plain-text fallback — just the raw markdown."""
    week = brief.week_ending.strftime("%-d %B %Y")
    return f"WHITE STAR — WEEKLY BRIEF — {week}\n\n{brief.brief_text}"


def _send_sync(
    recipients: list[str],
    subject: str,
    html_body: str,
    plain_body: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if smtp_user:
            server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, recipients, msg.as_bytes())


async def send_brief_email(brief: WeeklyBrief) -> bool:
    """Send the brief to configured recipients. Returns True on success.

    Safe to call even if SMTP is unconfigured — logs a warning and returns False.
    """
    from app.core.config import settings

    recipients = settings.get_brief_recipients()
    if not recipients:
        log.info("brief_email_skipped", reason="no_recipients_configured")
        return False
    if not settings.smtp_host:
        log.info("brief_email_skipped", reason="no_smtp_host_configured")
        return False

    week = brief.week_ending.strftime("%-d %B %Y")
    subject = f"White Star — Weekly Brief — {week}"
    html_body = _build_html(brief)
    plain_body = _build_plain(brief)

    try:
        await asyncio.to_thread(
            _send_sync,
            recipients,
            subject,
            html_body,
            plain_body,
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
        )
        log.info("brief_email_sent", recipients=recipients, week=str(brief.week_ending))
        return True
    except Exception:
        log.exception("brief_email_failed", week=str(brief.week_ending))
        return False
