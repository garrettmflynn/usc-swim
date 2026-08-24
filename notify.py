#!/usr/bin/env python3
"""Tell people the swim schedule changed.

Runs after scrape.py in the watcher. Sends only when the posted content hash
actually moved — a check that finds nothing new is not news, and a notifier
that cries every hour gets muted, which is the same as not having one.

Two channels, on purpose:

  email      works for everyone with no setup on their device
  web push   nicer, but each device has to be enrolled by hand, because the
             site is static and there is no server to register subscriptions

Both are optional. Missing configuration is skipped quietly rather than
failing the run — a notifier must never be the reason the dataset stops.

Configuration, all via environment (GitHub Actions secrets):
  NOTIFY_EMAIL_TO        comma-separated recipients
  SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS
  VAPID_PRIVATE_KEY      base64url, pairs with the key built into the app
  VAPID_SUBJECT          e.g. mailto:you@example.com
  PUSH_SUBSCRIPTIONS     JSON array of PushSubscription objects
  SITE_URL               link included in the notification
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

DATA = Path(__file__).parent / "docs" / "data"
STATE = Path(__file__).parent / ".notified.json"

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def clock(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    suffix = "am" if hour < 12 else "pm"
    return f"{hour % 12 or 12}{f':{minute:02d}' if minute else ''}{suffix}"


def windows_by_date(parsed: dict) -> dict[str, set[tuple[int, int]]]:
    out: dict[str, set[tuple[int, int]]] = {}
    for rows in parsed.get("pools", {}).values():
        for row in rows:
            if not row.get("date") or "outside_posted_week" in row.get("flags", []):
                continue
            out.setdefault(row["date"], set()).update(
                (w[0], w[1]) for w in row["windows"]
            )
    return out


def describe_change(latest: dict, history: list[dict]) -> list[str]:
    """What moved since the schedule we last announced.

    A notification that only says "the schedule changed" makes you open the app
    to find out whether it matters. The thing worth waking someone for is the
    delta — a lost 6am, or an edit landing mid-week under a plan they already
    made.
    """
    previous = None
    for entry in reversed(history[:-1]):
        if entry.get("content_hash") != latest.get("content_hash"):
            previous = entry
            break
    if previous is None:
        return []

    before = windows_by_date(previous["parsed"])
    after = windows_by_date(latest["parsed"])

    # Only dates the two postings share can have *changed*. Dates that appear
    # in just one of them are the week rolling over, and reporting a whole new
    # week as "added everything, removed everything" buries the one line that
    # actually matters.
    shared = sorted(set(before) & set(after))
    fresh = sorted(set(after) - set(before))

    lines: list[str] = []
    for iso in shared:
        gone = sorted(before[iso] - after[iso])
        new = sorted(after[iso] - before[iso])
        if not gone and not new:
            continue
        parts = []
        if gone:
            parts.append("removed " + ", ".join(f"{clock(a)}-{clock(b)}" for a, b in gone))
        if new:
            parts.append("added " + ", ".join(f"{clock(a)}-{clock(b)}" for a, b in new))
        lines.append(f"  {pretty(iso)}: " + "; ".join(parts))

    if fresh and not lines:
        lines.append(f"  A new week is up: {pretty(fresh[0])} to {pretty(fresh[-1])}.")
    elif fresh:
        lines.append(f"  Also newly posted: {pretty(fresh[0])} to {pretty(fresh[-1])}.")
    return lines


def mid_week(latest: dict) -> str | None:
    """Flag an edit that lands after its own week has already started."""
    dates = sorted(windows_by_date(latest["parsed"]))
    if not dates:
        return None
    first = date.fromisoformat(dates[0])
    monday = first - timedelta(days=first.weekday())
    today = datetime.now().date()
    day_in = (today - monday).days
    if 1 <= day_in <= 6 and monday <= today:
        return (
            f"This landed on {WEEKDAYS[today.weekday()]}, "
            f"day {day_in + 1} of the week it covers — a mid-week change."
        )
    return None


def day_rows(latest: dict) -> list[tuple[str, list[str]]]:
    """(iso date, ["6am-8am Dive Pool", ...]) in clock order, days with hours."""
    by_date: dict[str, list[tuple[int, str]]] = {}
    closed: set[str] = set()
    for pool, rows in latest["parsed"]["pools"].items():
        for row in rows:
            if not row.get("date") or "outside_posted_week" in row.get("flags", []):
                continue
            if row["windows"]:
                for w in row["windows"]:
                    by_date.setdefault(row["date"], []).append(
                        (w[0], f"{clock(w[0])}-{clock(w[1])} {pool}")
                    )
            elif row.get("closed") is True:
                closed.add(row["date"])

    out = []
    for iso in sorted(set(by_date) | closed):
        labels = [label for _, label in sorted(by_date.get(iso, []))]
        out.append((iso, labels))
    return out


def headline(latest: dict, changes: list[str], warning: str | None) -> str:
    """One sentence someone can act on without opening anything."""
    through = latest["coverage"].get("posted_through") or "nothing"
    if warning:
        return "They changed a week that had already started"
    if changes and changes[0].lstrip().startswith("A new week"):
        return f"Next week is up, through {pretty(through)}"
    if changes:
        n = len(changes)
        return f"{n} day{'' if n == 1 else 's'} changed on the posted week"
    return f"Schedule updated, through {pretty(through)}"


def pretty(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%a %-d %b")
    except ValueError:
        return iso


def summarize(latest: dict, history: list[dict] | None = None) -> tuple[str, str]:
    """Subject and plain-text body. See render_html for the formatted version."""
    history = history or []
    changes = describe_change(latest, history)
    warning = mid_week(latest)
    head = headline(latest, changes, warning)

    lines = [head, ""]
    if warning:
        lines += [warning, ""]
    # For a brand-new week the only "change" is that it exists, which the
    # headline already said. Repeating it as a section is noise.
    if changes and not changes[0].lstrip().startswith("A new week"):
        lines += ["What changed", *changes, ""]

    lines.append("The week as posted")
    for iso, labels in day_rows(latest):
        day = date.fromisoformat(iso).strftime("%a %-d %b")
        lines.append(f"  {day:<11}  " + (" · ".join(labels) if labels else "closed"))

    if latest["parsed"].get("updated_label"):
        lines += ["", f"USC stamped it {pretty(latest['parsed']['updated_label'])}."]

    health = latest.get("parse_health", {})
    if health.get("status") not in (None, "ok"):
        lines += ["", f"Heads up: the parser reported '{health['status']}' on this "
                      "check, so the hours above may be incomplete."]

    site = env("SITE_URL")
    if site:
        lines += ["", site]
    return f"{head} — Uytengsu rec swim", "\n".join(lines)


def render_html(latest: dict, history: list[dict] | None = None) -> str:
    """The same thing, laid out so it can be read at a glance on a phone.

    Table-based and inline-styled on purpose: mail clients strip stylesheets
    and most still lay out with tables. Colours are chosen to stay legible if
    a client inverts them for dark mode rather than relying on a media query
    many of them ignore.
    """
    history = history or []
    changes = describe_change(latest, history)
    warning = mid_week(latest)
    head = headline(latest, changes, warning)
    site = env("SITE_URL")

    ink, muted, rule, accent, warn = "#0f1a1c", "#5c7a82", "#dde5e3", "#0f5f6b", "#a3302f"

    def esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    parts = [
        f'<div style="margin:0;padding:24px 12px;background:#f2f5f4;'
        f'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;">',
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="max-width:520px;margin:0 auto;background:#ffffff;'
        f'border-radius:14px;overflow:hidden;">',
        f'<tr><td style="padding:22px 24px 6px;">'
        f'<div style="font:600 11px/1.4 ui-monospace,Menlo,monospace;'
        f'letter-spacing:.14em;text-transform:uppercase;color:{accent};">'
        f'Uytengsu rec swim</div>'
        f'<div style="font:700 21px/1.3 -apple-system,Segoe UI,Roboto,sans-serif;'
        f'color:{ink};padding-top:6px;">{esc(head)}</div></td></tr>',
    ]

    if warning:
        parts.append(
            f'<tr><td style="padding:12px 24px 0;">'
            f'<div style="background:#fdeceb;border-left:3px solid {warn};'
            f'border-radius:0 6px 6px 0;padding:10px 12px;'
            f'font:400 13px/1.5 -apple-system,sans-serif;color:{warn};">'
            f'{esc(warning)}</div></td></tr>')

    if changes and not changes[0].lstrip().startswith("A new week"):
        rows = "".join(
            f'<div style="font:400 13px/1.6 ui-monospace,Menlo,monospace;'
            f'color:{ink};padding:3px 0;">{esc(c.strip())}</div>'
            for c in changes)
        parts.append(
            f'<tr><td style="padding:18px 24px 0;">'
            f'<div style="font:600 11px/1.4 ui-monospace,Menlo,monospace;'
            f'letter-spacing:.12em;text-transform:uppercase;color:{muted};'
            f'padding-bottom:6px;">What changed</div>{rows}</td></tr>')

    day_html = []
    for iso, labels in day_rows(latest):
        day = date.fromisoformat(iso).strftime("%a %-d %b")
        value = (
            " &middot; ".join(esc(l) for l in labels)
            if labels
            else f'<span style="color:{muted};">closed</span>'
        )
        day_html.append(
            f'<tr><td style="padding:7px 0;border-top:1px solid {rule};'
            f'font:600 13px/1.4 -apple-system,sans-serif;color:{ink};'
            f'white-space:nowrap;vertical-align:top;width:96px;">{day}</td>'
            f'<td style="padding:7px 0 7px 10px;border-top:1px solid {rule};'
            f'font:400 13px/1.5 ui-monospace,Menlo,monospace;color:{ink};">'
            f'{value}</td></tr>')

    parts.append(
        f'<tr><td style="padding:18px 24px 4px;">'
        f'<div style="font:600 11px/1.4 ui-monospace,Menlo,monospace;'
        f'letter-spacing:.12em;text-transform:uppercase;color:{muted};'
        f'padding-bottom:2px;">The week as posted</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%">{"".join(day_html)}</table></td></tr>')

    health = latest.get("parse_health", {})
    if health.get("status") not in (None, "ok"):
        parts.append(
            f'<tr><td style="padding:14px 24px 0;">'
            f'<div style="background:#fdf3e3;border-radius:6px;padding:10px 12px;'
            f'font:400 12px/1.5 -apple-system,sans-serif;color:#8a5a06;">'
            f'The parser reported &ldquo;{esc(health["status"])}&rdquo; on this '
            f'check, so these hours may be incomplete.</div></td></tr>')

    stamped = latest["parsed"].get("updated_label")
    footer = f"USC stamped it {pretty(stamped)}." if stamped else ""
    link = (
        f'<a href="{esc(site)}" style="color:{accent};text-decoration:none;'
        f'font-weight:600;">Open the app</a>' if site else "")
    parts.append(
        f'<tr><td style="padding:18px 24px 22px;">'
        f'<div style="border-top:1px solid {rule};padding-top:12px;'
        f'font:400 12px/1.5 -apple-system,sans-serif;color:{muted};">'
        f'{esc(footer)} {link}</div></td></tr>')

    parts += ["</table>", "</div>"]
    return "".join(parts)


def send_email(subject: str, body: str, html: str | None = None) -> str:
    to = [a.strip() for a in env("NOTIFY_EMAIL_TO").split(",") if a.strip()]
    host, user, password = env("SMTP_HOST"), env("SMTP_USER"), env("SMTP_PASS")
    if not (to and host and user and password):
        return "email: not configured, skipped"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env("SMTP_FROM", user)
    msg["To"] = ", ".join(to)
    msg.set_content(body)
    if html:
        # Clients that can't render it fall back to the plain text above.
        msg.add_alternative(html, subtype="html")

    port = int(env("SMTP_PORT", "587"))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls()
                s.login(user, password)
                s.send_message(msg)
    except Exception as exc:
        return f"email: FAILED ({exc})"
    return f"email: sent to {len(to)} recipient(s)"


def send_push(title: str, detail: str) -> str:
    subs_raw = env("PUSH_SUBSCRIPTIONS")
    private = env("VAPID_PRIVATE_KEY")
    if not (subs_raw and private):
        return "push: not configured, skipped"

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return "push: pywebpush not installed, skipped"

    try:
        subs = json.loads(subs_raw)
    except json.JSONDecodeError as exc:
        return f"push: PUSH_SUBSCRIPTIONS is not valid JSON ({exc})"
    if isinstance(subs, dict):
        subs = [subs]

    # The body used to be body.splitlines()[0], which after the change-summary
    # was added became the bare label "What changed" — a heading with nothing
    # under it. Push has one line; spend it on the news, not a section title.
    payload = json.dumps({
        "title": title,
        "body": detail,
        "url": env("SITE_URL", "./"),
        "tag": "swimwatch-change",
    })

    sent = gone = failed = 0
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=private,
                vapid_claims={"sub": env("VAPID_SUBJECT", "mailto:swimwatch@example.com")},
                timeout=30,
            )
            sent += 1
        except WebPushException as exc:
            # 404/410 mean the browser dropped the subscription; that device
            # needs re-enrolling, and it is not an error worth failing on.
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                gone += 1
            else:
                failed += 1
                print(f"push: {exc}", file=sys.stderr)
    return f"push: {sent} sent, {gone} expired, {failed} failed"


def main() -> int:
    ap = argparse.ArgumentParser(description="Announce a schedule change.")
    ap.add_argument("--test", action="store_true",
                    help="send now regardless of whether anything changed, and "
                         "leave the change marker untouched")
    args = ap.parse_args()

    latest_path = DATA / "latest.json"
    if not latest_path.exists():
        print("no latest.json — nothing to notify about")
        return 0
    latest = json.loads(latest_path.read_text())
    history_path = DATA / "history.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []

    digest = latest.get("content_hash")
    previous = None
    if STATE.exists():
        try:
            previous = json.loads(STATE.read_text()).get("content_hash")
        except json.JSONDecodeError:
            previous = None

    changes = describe_change(latest, history)
    warning = mid_week(latest)
    head = headline(latest, changes, warning)
    # One line for the push: the first concrete change if there is one, else
    # what the week actually holds.
    if changes and not changes[0].lstrip().startswith("A new week"):
        detail = changes[0].strip()
    else:
        rows = day_rows(latest)
        open_days = sum(1 for _, labels in rows if labels)
        detail = f"{open_days} of {len(rows)} days have swim hours"

    if args.test:
        subject, body = summarize(latest, history)
        print("test mode — sending regardless of change, marker left alone")
        print(send_email(f"[test] {subject}", body, render_html(latest, history)))
        print(send_push(f"[test] {head}", detail))
        return 0

    if previous == digest:
        print(f"no change since {previous} — not notifying")
        return 0
    if previous is None and env("NOTIFY_ON_FIRST_RUN", "").lower() not in ("1", "true", "yes"):
        # First run has nothing to compare against; announcing it would just be
        # noise on setup. Record the baseline and stay quiet.
        STATE.write_text(json.dumps({"content_hash": digest}, indent=2))
        print(f"first run, baseline recorded ({digest}) — not notifying")
        return 0

    subject, body = summarize(latest, history)
    print(send_email(subject, body, render_html(latest, history)))
    print(send_push(head, detail))
    STATE.write_text(json.dumps({"content_hash": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
