"""SMTP delivery for WardenIQ sign-in OTP emails."""
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

SUBJECT = "Your WardenIQ login verification code"
OTP_VALID_MINUTES = 10


def is_gmail(host: str) -> bool:
    """True if the SMTP host is Gmail / Google Workspace, which requires an
    authenticated App Password (not a normal account password)."""
    h = (host or "").strip().lower()
    return h.endswith(("gmail.com", "googlemail.com"))


def normalize_smtp_password(host: str, password: str) -> str:
    """Gmail App Passwords are displayed as four space-separated groups
    ('abcd efgh ijkl mnop') but must be sent without the spaces. Strip spaces for
    Gmail hosts; leave other providers' passwords untouched."""
    if password and is_gmail(host):
        return password.replace(" ", "")
    return password or ""


def _recipient_name(to_email: str, name: str = "") -> str:
    if name:
        return name.strip()
    return (to_email or "").split("@")[0] or "there"


def _plain_body(code: str, to_email: str, name: str = "") -> str:
    recipient = _recipient_name(to_email, name)
    return (
        f"Hi {recipient},\n\n"
        f"Your WardenIQ One-Time Password is: {code}\n\n"
        f"This OTP is valid for {OTP_VALID_MINUTES} minutes.\n"
        "Please do not share this code with anyone.\n\n"
        "If you did not request this login, you can safely ignore this email.\n\n"
        "Best regards,\n"
        "WardenIQ Team"
    )


def _html_body(code: str, to_email: str, name: str = "") -> str:
    recipient = escape(_recipient_name(to_email, name))
    # Render the raw digits (no spaces) — the box below uses letter-spacing for the
    # visual gap, so copying the code yields clean digits with no embedded spaces.
    otp = escape(code.strip())

    return f"""\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(SUBJECT)}</title>
</head>
<body style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
  <div style="display:none;max-height:0;overflow:hidden;color:transparent;">
    Your WardenIQ login verification code is {escape(code)}.
  </div>

  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f7fb;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5eaf3;">
          <tr>
            <td style="background:#12387f;padding:32px 36px;">
              <div style="font-size:28px;font-weight:700;color:#ffffff;line-height:1.2;">WardenIQ</div>
              <div style="font-size:13px;color:#dbeafe;margin-top:8px;">Secure Access Verification</div>
            </td>
          </tr>

          <tr>
            <td style="padding:36px;">
              <h1 style="margin:0 0 24px;font-size:26px;line-height:1.3;text-align:center;color:#2563eb;">
                Your OTP for WardenIQ Login
              </h1>

              <p style="margin:0 0 16px;font-size:15px;line-height:1.7;color:#374151;">
                Hi {recipient},
              </p>

              <p style="margin:0 0 28px;font-size:15px;line-height:1.7;color:#4b5563;">
                To verify your identity and continue signing in to your WardenIQ account, please use the One-Time Password below.
              </p>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5fb;border-radius:14px;">
                <tr>
                  <td align="center" style="padding:32px 20px;">
                    <div style="font-size:24px;font-weight:700;color:#1f2937;margin-bottom:18px;">
                      Your One-Time Password
                    </div>
                    <div style="display:inline-block;background:#2563eb;color:#ffffff;font-size:34px;font-weight:700;letter-spacing:10px;padding:14px 28px;border-radius:10px;">
                      {otp}
                    </div>
                    <div style="font-size:13px;color:#6b7280;margin-top:18px;">
                      This OTP is valid for <strong>{OTP_VALID_MINUTES} minutes</strong>.
                    </div>
                  </td>
                </tr>
              </table>

              <div style="margin-top:24px;padding:16px 18px;background:#fffbeb;border:1px solid #fbbf24;border-radius:12px;color:#92400e;font-size:14px;line-height:1.6;">
                Please do not share this code with anyone for security reasons. If you did not request this login, you can safely ignore this email.
              </div>

              <p style="margin:30px 0 0;font-size:15px;line-height:1.7;color:#374151;">
                Best regards,<br>
                <strong>WardenIQ Team</strong>
              </p>
              <p style="margin:8px 0 0;font-size:13px;color:#9ca3af;">
                Thank you for using WardenIQ.
              </p>
            </td>
          </tr>

          <tr>
            <td align="center" style="background:#071a44;padding:22px 28px;color:#cbd5e1;font-size:12px;line-height:1.6;">
              This is an automated message. Please do not reply.<br>
              © 2026 WardenIQ. All rights reserved.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _send(cfg: dict, to_email: str, subject: str, plain: str, html: str = None):
    """Low-level SMTP send. Returns (sent: bool, error: str)."""
    host = (cfg or {}).get("host")
    if not host:
        return False, "smtp not configured"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("from") or cfg.get("user") or "wardeniq@localhost"
    msg["To"] = to_email
    msg.set_content(plain)
    if html:
        msg.add_alternative(html, subtype="html")
    port = int(cfg.get("port") or (465 if cfg.get("ssl") else 587))
    user, pw = cfg.get("user"), cfg.get("password", "")
    try:
        if cfg.get("ssl"):
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as s:
                if user:
                    s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                if cfg.get("tls", True):
                    s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, pw)
                s.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)


def send_otp(cfg: dict, to_email: str, code: str, recipient_name: str = ""):
    """Send the OTP via SMTP. Returns (sent: bool, error: str)."""
    return _send(cfg, to_email, SUBJECT,
                 _plain_body(code, to_email, recipient_name),
                 _html_body(code, to_email, recipient_name))


def _invite_plain(link: str, inviter: str, role: str, workspace: str, name: str = "") -> str:
    hi = f"Hi {name}," if name else "Hi,"
    by = f"{inviter} has invited you" if inviter else "You've been invited"
    return (f"{hi}\n\n{by} to join {workspace} as a {role}.\n\n"
            f"Accept your invitation here:\n{link}\n\n"
            "This link expires in 7 days. If you didn't expect this, you can ignore this email.")


_ROLE_BLURB = {
    "viewer": "Browse projects, features, test cases and coverage (read-only).",
    "editor": "Create and edit features, test cases, and run generation.",
    "admin":  "Full access — manage users, settings, and everything above.",
}


def _invite_html(link: str, inviter: str, role: str, workspace: str, name: str = "") -> str:
    from html import escape as _e
    hi = f"Hi {_e(name)}," if name else "Hi there,"
    who = _e(inviter) if inviter else "An administrator"
    blurb = _ROLE_BLURB.get((role or "").lower(), "")
    # Table-based, inline-styled layout for broad email-client compatibility.
    return f"""\
<!doctype html>
<html>
<body style="margin:0;padding:0;background:#eef2f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f7;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 30px rgba(15,23,42,.08);">
        <!-- brand header -->
        <tr><td style="background:#0f1a2b;padding:22px 28px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:.3px;">
              warden<span style="color:#1ce5b2;">IQ</span>
            </td>
            <td style="padding-left:10px;font-size:11px;color:#8aa0b8;text-transform:uppercase;letter-spacing:1px;">Engineering Intelligence</td>
          </tr></table>
        </td></tr>
        <!-- body -->
        <tr><td style="padding:32px 28px 8px;">
          <h1 style="margin:0 0 14px;font-size:22px;line-height:1.3;color:#0f172a;">You're invited to join {_e(workspace)}</h1>
          <p style="margin:0 0 6px;color:#475569;font-size:15px;">{hi}</p>
          <p style="margin:0 0 20px;color:#475569;font-size:15px;line-height:1.5;">
            <b>{who}</b> has invited you to <b>{_e(workspace)}</b> with the role of
            <span style="display:inline-block;background:#eaf3fb;color:#1c7ec2;border:1px solid #cfe6f7;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;text-transform:capitalize;">{_e(role)}</span>.
          </p>
          {"<p style='margin:0 0 22px;color:#64748b;font-size:13px;line-height:1.5;'>"+_e(blurb)+"</p>" if blurb else ""}
          <!-- CTA button (bulletproof) -->
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="border-radius:10px;background:#1c7ec2;">
              <a href="{_e(link)}" style="display:inline-block;padding:13px 26px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px;">Accept invitation &rarr;</a>
            </td>
          </tr></table>
          <p style="margin:22px 0 0;color:#94a3b8;font-size:12px;line-height:1.5;">
            This invitation expires in <b>7 days</b>. If you weren't expecting it, you can safely ignore this email.
          </p>
        </td></tr>
        <!-- fallback url -->
        <tr><td style="padding:0 28px 26px;">
          <p style="margin:16px 0 6px;color:#94a3b8;font-size:11px;">Button not working? Paste this link into your browser:</p>
          <p style="margin:0;word-break:break-all;"><a href="{_e(link)}" style="color:#1c7ec2;font-size:11px;">{_e(link)}</a></p>
        </td></tr>
        <!-- footer -->
        <tr><td style="background:#f8fafc;border-top:1px solid #eef2f7;padding:16px 28px;">
          <p style="margin:0;color:#94a3b8;font-size:11px;">Sent by {_e(workspace)} · This is an automated message, please don't reply.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_invite(cfg: dict, to_email: str, link: str, inviter: str = "",
                role: str = "viewer", workspace: str = "WardenIQ", recipient_name: str = ""):
    """Send an invitation LINK email (no OTP code). Returns (sent, error)."""
    subject = f"You're invited to {workspace}"
    return _send(cfg, to_email, subject,
                 _invite_plain(link, inviter, role, workspace, recipient_name),
                 _invite_html(link, inviter, role, workspace, recipient_name))


def validate_config(cfg: dict):
    """Open the SMTP connection and authenticate without sending a message."""
    host = (cfg or {}).get("host")
    if not host:
        return False, "smtp not configured"

    port = int(cfg.get("port") or (465 if cfg.get("ssl") else 587))
    user, pw = cfg.get("user"), cfg.get("password", "")

    try:
        if cfg.get("ssl"):
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as s:
                if user:
                    s.login(user, pw)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                if cfg.get("tls", True):
                    s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, pw)
        return True, ""
    except Exception as e:
        return False, str(e)