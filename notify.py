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
        day = date.fromisoformat(iso)
        parts = []
        if gone:
            parts.append("removed " + ", ".join(f"{clock(a)}-{clock(b)}" for a, b in gone))
        if new:
            parts.append("added " + ", ".join(f"{clock(a)}-{clock(b)}" for a, b in new))
        lines.append(f"  {WEEKDAYS[day.weekday()]} {iso}: " + "; ".join(parts))

    if fresh and not lines:
        lines.append(f"  A new week is up: {fresh[0]} to {fresh[-1]}.")
    elif fresh:
        lines.append(f"  Also newly posted: {fresh[0]} to {fresh[-1]}.")
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


def summarize(latest: dict, history: list[dict] | None = None) -> tuple[str, str]:
    """A subject line and a body someone can act on without opening anything."""
    history = history or []
    cov = latest["coverage"]
    through = cov.get("posted_through") or "nothing"

    changes = describe_change(latest, history)
    warning = mid_week(latest)

    if warning:
        subject = f"Swim hours changed mid-week — posted through {through}"
    elif changes and changes[0].lstrip().startswith("A new week"):
        subject = f"New swim week posted — through {through}"
    elif changes:
        subject = f"Swim hours changed — {len(changes)} day(s) differ"
    else:
        subject = f"Swim hours updated — posted through {through}"

    lines = []
    if warning:
        lines += [warning, ""]
    if changes:
        lines += ["What changed since the last posting:", *changes, ""]
    lines.append(f"Full schedule (through {through}):")
    if latest["parsed"].get("updated_label"):
        lines.append(f"They stamped it {latest['parsed']['updated_label']}.")
    lines.append("")

    # (start minute, label) so the day reads in clock order — sorting the
    # rendered strings puts "6am" after "4pm".
    by_date: dict[str, list[tuple[int, str]]] = {}
    for pool, rows in latest["parsed"]["pools"].items():
        for row in rows:
            if not row.get("date") or not row["windows"]:
                continue
            for w in row["windows"]:
                by_date.setdefault(row["date"], []).append(
                    (w[0], f"{clock(w[0])}-{clock(w[1])} {pool}")
                )
    for iso in sorted(by_date):
        ordered = [label for _, label in sorted(by_date[iso])]
        lines.append(f"  {iso}   " + " · ".join(ordered))
    if not by_date:
        lines.append("  (no open swim windows in this posting)")

    health = latest.get("parse_health", {})
    if health.get("status") not in (None, "ok"):
        lines += ["", f"Note: the parser reported '{health['status']}' on this check."]

    site = env("SITE_URL")
    if site:
        lines += ["", site]
    return subject, "\n".join(lines)


def send_email(subject: str, body: str) -> str:
    to = [a.strip() for a in env("NOTIFY_EMAIL_TO").split(",") if a.strip()]
    host, user, password = env("SMTP_HOST"), env("SMTP_USER"), env("SMTP_PASS")
    if not (to and host and user and password):
        return "email: not configured, skipped"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env("SMTP_FROM", user)
    msg["To"] = ", ".join(to)
    msg.set_content(body)

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


def send_push(subject: str, body: str) -> str:
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

    payload = json.dumps({
        "title": "Swim hours updated",
        "body": body.splitlines()[0],
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

    if args.test:
        subject, body = summarize(latest, history)
        print("test mode — sending regardless of change, marker left alone")
        print(send_email(f"[test] {subject}", body))
        print(send_push(f"[test] {subject}", body))
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
    print(send_email(subject, body))
    print(send_push(subject, body))
    STATE.write_text(json.dumps({"content_hash": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
