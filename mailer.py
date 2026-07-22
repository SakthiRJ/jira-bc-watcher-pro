"""SMTP mailer with a dry-run mode that prints instead of sending.

Callers pass a complete HTML body (see emailfmt). DRY_RUN prints to the console
so you can test without real delivery.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from config import Config


class Mailer:
    def __init__(self, config: Config):
        self.config = config

    def send(self, subject: str, body_html: str) -> None:
        if self.config.dry_run:
            self._print(subject, body_html)
            return
        self._smtp_send(subject, body_html)

    def _print(self, subject: str, body_html: str) -> None:
        import os, sys
        # Save HTML to file - avoids Windows cp1252 emoji encoding issues on the console
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dry_run_email.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"<!-- Subject: {subject} -->\n")
            f.write(body_html)
        enc = sys.stdout.encoding or "utf-8"
        def safe(s: str) -> str:
            return s.encode(enc, errors="replace").decode(enc)
        print("=" * 78)
        print("[DRY_RUN] Would send email")
        print(f"  From : {self.config.smtp_from or '(SMTP_FROM not set)'}")
        print(f"  To   : {', '.join(self.config.recipients) or '(EMAIL_RECIPIENTS not set)'}")
        print(f"  Subj : {safe(subject)}")
        print(f"  HTML : {out_path}")
        print("=" * 78)

    def _smtp_send(self, subject: str, body_html: str) -> None:
        msg = EmailMessage()
        name, addr = parseaddr(self.config.smtp_from)
        msg["From"] = formataddr((name or "Jira BC Watcher", addr or self.config.smtp_user))
        msg["To"] = ", ".join(self.config.recipients)
        msg["Subject"] = subject
        msg.set_content("This update is best viewed in an HTML-capable email client.")
        msg.add_alternative(body_html, subtype="html")

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=30) as server:
            if self.config.smtp_use_tls:
                server.starttls()
            if self.config.smtp_user:
                server.login(self.config.smtp_user, self.config.smtp_password)
            server.send_message(msg)
