#!/usr/bin/env python3
"""
swimwatch — checks whether USC Rec Sports has posted a swim schedule that
actually covers today, and records how long it takes them to update it.

Run it on a schedule. It writes three files under docs/data/:
  latest.json    the most recent check, fully parsed
  history.json   one entry per *content change* (not per check)
  stats.json     rolled-up timeliness numbers for the dashboard

Only history.json grows. It is the dataset; everything else is derived.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://recsports.usc.edu/rec-facilities/operating-hours/"
CONTACT = "swimwatch (personal schedule monitor; contact: you@example.com)"
TZ = ZoneInfo("America/Los_Angeles")

DATA = Path(__file__).parent / "docs" / "data"
CACHE = Path(__file__).parent / ".cache.json"

SECTION_START = re.compile(r"rec\s+swim\s+hours", re.I)
UPDATED_RE = re.compile(r"updated\s*:?\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", re.I)
ROW_RE = re.compile(
    r"^(Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)[a-z]*\.?,?\s*"
    r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*:\s*(.+)$",
    re.I,
)
TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", re.I)
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

# The block is headings and text, never layout containers. See extract_block.
CONTENT_TAGS = ("h3", "h4", "p", "li", "td", "th")

# Flags that mean the source is wrong, as opposed to a row we simply couldn't
# attribute. Only these count as anomalies; see parse_health.
ANOMALY_FLAGS = {"outside_posted_week", "weekday_date_mismatch", "unparsed_date"}
UNNAMED_POOLS = ("Unlabeled", "Unattributed")

# Prose that belongs in the block and is not a row. Anything that matches
# neither this nor ROW_RE is drift, and parse_health reports it.
NOTE_RE = re.compile(
    r"(rec\s+swim|subject\s+to\s+change|first[- ]come|lanes?\s+are|"
    r"lap\s+swim|please\s+note|updated|check\s+the\s+website|"
    r"hours?$|pool$|week\s+of|game\s*day|maintenance|see\s+ped|"
    r"schedule|notice|holiday|closed)", re.I)


# ---------------------------------------------------------------- fetching

def fetch(etag: str | None, last_modified: str | None) -> tuple[int, str | None, dict]:
    headers = {"User-Agent": CONTACT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    r = requests.get(URL, headers=headers, timeout=30)
    validators = {
        "etag": r.headers.get("ETag"),
        "last_modified": r.headers.get("Last-Modified"),
    }
    if r.status_code == 304:
        return 304, None, validators
    r.raise_for_status()
    return r.status_code, r.text, validators


# ---------------------------------------------------------------- extraction

def extract_block(html: str) -> str:
    """Return the raw HTML of the Rec Swim Hours section only.

    Scoped tightly on purpose: the nav, hero image and footer of this site
    change on their own schedule and would pollute the change log.
    """
    soup = BeautifulSoup(html, "lxml")
    start = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if SECTION_START.search(tag.get_text(" ", strip=True)):
            start = tag
            break
    if start is None:
        raise LookupError("Rec Swim Hours heading not found — the page was restructured")

    parts = [str(start)]
    for tag in start.find_all_next():
        if tag.name in ("h1", "h2"):  # next major section ends the block
            break
        # Emit only content elements, never containers. The live page wraps the
        # whole rest of the page in wp-block divs; emitting one of those both
        # duplicated every row and swallowed the sections past the h2 that is
        # supposed to end the block.
        if tag.name not in CONTENT_TAGS:
            continue
        if tag.find_parent(CONTENT_TAGS) is not None:
            continue  # already captured inside a content element we emitted
        parts.append(str(tag))
    return "\n".join(parts)


def normalize(block_html: str) -> str:
    """Text-only, whitespace-flattened form. This is what gets hashed."""
    text = BeautifulSoup(block_html, "lxml").get_text("\n")
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


# ---------------------------------------------------------------- parsing

def infer_year(month: int, day: int, near: date, explicit: str | None) -> date | None:
    if explicit:
        year = int(explicit)
        year += 2000 if year < 100 else 0
        try:
            return date(year, month, day)
        except ValueError:
            return None
    best = None
    for year in (near.year - 1, near.year, near.year + 1):
        try:
            cand = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((cand - near).days) < abs((best - near).days):
            best = cand
    return best


def parse_windows(value: str) -> tuple[list[list[int]], bool]:
    """'6am-8am, 4pm-6pm' -> [[360,480],[960,1080]] in minutes past midnight."""
    if re.search(r"\b(closed|n/?a|none)\b", value, re.I):
        return [], True
    windows = []
    for chunk in re.split(r"[,;]| and ", value):
        times = TIME_RE.findall(chunk)
        if len(times) != 2:
            continue
        pair = []
        for hour, minute, mer in times:
            h = int(hour) % 12 + (12 if mer.lower() == "p" else 0)
            pair.append(h * 60 + int(minute or 0))
        if pair[1] > pair[0]:
            windows.append(pair)
    return windows, False


def parse_block(block_html: str, today: date) -> dict:
    text = normalize(block_html)
    updated = None
    m = UPDATED_RE.search(text)
    if m:
        d = infer_year(int(m.group(1)), int(m.group(2)), today, m.group(3))
        updated = d.isoformat() if d else None

    pools: dict[str, list[dict]] = {}
    unconsumed: list[str] = []
    current = "Unlabeled"
    for line in text.splitlines():
        row = ROW_RE.match(line)
        if not row:
            if re.search(r"\bpool\b", line, re.I) and len(line) < 40 and ":" not in line:
                current = line.strip()
                pools.setdefault(current, [])
            elif len(line) > 3 and not NOTE_RE.search(line):
                # Neither a row, a pool heading, nor known prose. This is how a
                # page restructure shows up first: not as an exception, but as
                # lines quietly going nowhere.
                unconsumed.append(line)
            continue
        weekday, month, day, year, value = row.groups()
        d = infer_year(int(month), int(day), today, year)
        windows, closed = parse_windows(value)
        pools.setdefault(current, []).append(
            {
                "weekday": weekday[:3].title(),
                "date": d.isoformat() if d else None,
                "raw": value.strip(),
                "windows": windows,
                "closed": closed,
                "flags": [],
            }
        )

    flag_anomalies(pools)
    return {"updated_label": updated, "pools": pools, "unconsumed": unconsumed}


def flag_anomalies(pools: dict[str, list[dict]]) -> None:
    """Mark rows that can't be right, instead of crashing on them.

    The real failure mode here isn't a missing schedule — it's a schedule with
    a typo'd date, which silently reads as a normal week.
    """
    for rows in pools.values():
        dates = [date.fromisoformat(r["date"]) for r in rows if r["date"]]
        if not dates:
            continue
        # Anchor on the week most rows agree on. One typo'd date is the outlier;
        # anchoring on the earliest date would invert that and flag the good rows.
        weeks = [d - timedelta(days=d.weekday()) for d in dates]
        week_start = max(set(weeks), key=lambda w: (weeks.count(w), w))
        week_end = week_start + timedelta(days=6)
        for r in rows:
            if not r["date"]:
                r["flags"].append("unparsed_date")
                continue
            d = date.fromisoformat(r["date"])
            if not (week_start <= d <= week_end):
                r["flags"].append("outside_posted_week")
            if d.strftime("%a") != r["weekday"]:
                r["flags"].append("weekday_date_mismatch")


# ------------------------------------------------------------ parse health

def parse_health(parsed: dict, unconsumed: list[str] | None = None) -> dict:
    """How much of the block did we actually understand?

    Deliberately separates two things that look alike in the data and are not:

      parser health   we failed to read the page      -> someone must fix code
      source anomaly  we read it, they typed it wrong -> nothing to fix here

    Only the first drives `status`. Folding a typo'd date into "degraded" makes
    the signal fire constantly on a page that is simply often wrong, and a
    warning that is always on is one you stop reading.
    """
    if unconsumed is None:
        unconsumed = parsed.get("unconsumed", [])
    pools = parsed.get("pools", {})
    rows = [r for v in pools.values() for r in v]
    windows = sum(len(r["windows"]) for r in rows)
    # "not mentioned" is an ordinary state — the page names one pool's hours and
    # says nothing about the other — so it is not an anomaly.
    anomalies = [r for r in rows if set(r.get("flags", [])) & ANOMALY_FLAGS]
    unattributed = sum(
        len(r["windows"]) for k, v in pools.items()
        for r in v if k in UNNAMED_POOLS)

    if not rows:
        status = "failed"
    elif unconsumed or unattributed:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "pools": len(pools),
        "rows": len(rows),
        "windows": windows,
        "anomaly_rows": len(anomalies),
        "unattributed_windows": unattributed,
        "unconsumed": unconsumed[:12],
        "unconsumed_total": len(unconsumed),
    }


# ---------------------------------------------------------------- coverage

def coverage(parsed: dict, now: datetime) -> dict:
    today = now.date()
    all_dates = [
        date.fromisoformat(r["date"])
        for rows in parsed["pools"].values()
        for r in rows
        if r["date"] and "outside_posted_week" not in r["flags"]
    ]
    if not all_dates:
        return {
            "today": today.isoformat(),
            "today_covered": False,
            "posted_through": None,
            "days_past_end": None,
            "swimmable_today": None,
        }

    posted_through = max(all_dates)
    covered = today in all_dates
    swimmable = None
    if covered:
        swimmable = sum(
            len(r["windows"])
            for rows in parsed["pools"].values()
            for r in rows
            if r["date"] == today.isoformat()
        )
    return {
        "today": today.isoformat(),
        "today_covered": covered,
        "posted_through": posted_through.isoformat(),
        "days_past_end": max(0, (today - posted_through).days),
        "swimmable_today": swimmable,
    }


# ---------------------------------------------------------------- stats

def build_stats(history: list[dict], checks: dict) -> dict:
    """Post lag = time from Monday 00:00 PT until that week first appeared."""
    first_seen: dict[str, str] = {}
    for entry in history:
        dates = [
            r["date"]
            for rows in entry["parsed"]["pools"].values()
            for r in rows
            if r["date"] and "outside_posted_week" not in r["flags"]
        ]
        if not dates:
            continue
        d = date.fromisoformat(min(dates))
        week = (d - timedelta(days=d.weekday())).isoformat()
        first_seen.setdefault(week, entry["checked_at"])

    watching_since = history[0]["checked_at"] if history else None
    lags = []
    for week, seen_at in sorted(first_seen.items()):
        monday = datetime.fromisoformat(week).replace(tzinfo=TZ)
        hours = (datetime.fromisoformat(seen_at) - monday).total_seconds() / 3600
        # If a week was already up when we started, we don't know when it went
        # up — that's a left-censored observation, not a slow post.
        censored = seen_at == watching_since
        lags.append(
            {
                "week_of": week,
                "first_seen": seen_at,
                "lag_hours": round(hours, 1),
                "censored": censored,
            }
        )

    values = sorted(l["lag_hours"] for l in lags if not l["censored"])
    median = values[len(values) // 2] if values else None
    total = checks.get("total", 0)
    return {
        "checks_total": total,
        "changes_total": len(history),
        "checks_with_today_covered": checks.get("covered", 0),
        "coverage_rate": round(checks.get("covered", 0) / total, 3) if total else None,
        "median_post_lag_hours": median,
        "weeks": lags[-12:],
    }


# ---------------------------------------------------------------- main

def load(path: Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    cache = load(CACHE, {})
    now = datetime.now(TZ)

    try:
        status, html, validators = fetch(cache.get("etag"), cache.get("last_modified"))
    except Exception as exc:  # network flake shouldn't poison the dataset
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    history = load(DATA / "history.json", [])
    prior = load(DATA / "latest.json", {})
    checks = cache.get("checks", {"total": 0, "covered": 0})
    checks["total"] += 1

    # The validator cache lives outside git, so it can outlive docs/data (or
    # vice versa). A 304 we can't reuse is not a check — refetch in full.
    if status == 304 and not (history and prior.get("parsed")):
        print("304 but no usable snapshot on disk — refetching", file=sys.stderr)
        try:
            status, html, validators = fetch(None, None)
        except Exception as exc:
            print(f"refetch failed: {exc}", file=sys.stderr)
            return 1

    if status == 304:
        latest = prior
        latest["checked_at"] = now.isoformat()
        latest["coverage"] = coverage(latest["parsed"], now)
        latest["conditional_304"] = True
    else:
        block = extract_block(html)
        parsed = parse_block(block, now.date())
        digest = hashlib.sha256(normalize(block).encode()).hexdigest()[:16]
        latest = {
            "checked_at": now.isoformat(),
            "source": URL,
            "content_hash": digest,
            "conditional_304": False,
            "parsed": parsed,
            "coverage": coverage(parsed, now),
            "parse_health": parse_health(parsed),
            "raw_block": block,  # keep the source of truth for re-parsing later
        }
        if not history or history[-1]["content_hash"] != digest:
            history.append(
                {
                    "checked_at": latest["checked_at"],
                    "content_hash": digest,
                    "parsed": parsed,
                    "coverage": latest["coverage"],
                    "parse_health": latest["parse_health"],
                    "origin": "live",
                }
            )

    if latest["coverage"]["today_covered"]:
        checks["covered"] += 1

    cache.update(
        {
            "etag": validators["etag"] or cache.get("etag"),
            "last_modified": validators["last_modified"] or cache.get("last_modified"),
            "checks": checks,
        }
    )

    (DATA / "latest.json").write_text(json.dumps(latest, indent=2))
    (DATA / "history.json").write_text(json.dumps(history, indent=2))
    (DATA / "stats.json").write_text(json.dumps(build_stats(history, checks), indent=2))
    CACHE.write_text(json.dumps(cache, indent=2))

    health = latest.get("parse_health", {})
    if health.get("status") == "failed":
        print("PARSE FAILED — the block yielded no rows. The page likely moved.",
              file=sys.stderr)
        for ln in health.get("unconsumed", []):
            print(f"  unconsumed: {ln}", file=sys.stderr)
        return 2

    cov = latest["coverage"]
    print(
        f"{now:%Y-%m-%d %H:%M} PT · status {status} · "
        f"today_covered={cov['today_covered']} · posted_through={cov['posted_through']} · "
        f"parse={health.get('status', '?')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
