#!/usr/bin/env python3
"""swimwatch backfill — recover pre-redesign schedules from the Wayback Machine.

USC moved this content in mid-2026. The current URL has no archive captures at
all; the page it replaced does, back to late 2024. That older page states the
same schedule in a different shape, so it needs its own parser:

    current                       archived
    Comp Pool                     Week of 3/23/26-3/29/26
    Mon, 8/17: Closed             Monday, 3/23:
    Tue, 8/18: 12pm-1pm             6am-8am Dive Pool
    Dive Pool                       12pm-2pm Comp Pool
    Mon, 8/17: 5pm-6pm            Tuesday, 3/24:
                                    ...

Grouped by day with the pool named per window, rather than by pool with one row
per day. Same information, transposed — so this transposes it back and emits
rows in exactly the shape scrape.py writes.

What this CANNOT recover is post lag. Captures land roughly monthly, so "when
did they put this up" is unknowable to within weeks. Every entry produced here
is marked origin="wayback" and build_stats censors it out of the lag median.

Usage:  python backfill.py [--dry-run] [--since YYYYMMDD]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from pathlib import Path

import scrape

# The page that carried rec swim hours before the 2026 redesign.
LEGACY_URL = (
    "recsports.usc.edu/rec-facilities-page/"
    "additional-facility-information/hours-of-operation"
)
CDX = "https://web.archive.org/cdx/search/cdx"
# id_ suffix asks for the original bytes, without the Wayback toolbar injection.
SNAPSHOT = "https://web.archive.org/web/{ts}id_/https://{url}"
# Rec swim hours first appear on this page in late 2024; earlier captures of it
# have no swim section at all (checked every capture back to 2019).
DEFAULT_SINCE = "20241001"

# Bump when a change alters what the legacy parser extracts.
VERSION = "1.0.0"

# The archived page is Beaver Builder; each facility is one accordion item.
# That container is the section boundary — far more reliable than "walk until
# the next h2", which on this page runs past into basketball and tennis.
ACCORDION = "fl-accordion-item"

WEEK_RE = re.compile(r"week\s+of\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*[-–—]\s*"
                     r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", re.I)
# "Monday, 3/23:", "Saturday 8/9:", "Saturday11/23:" — the date is optional and
# so is every separator around it. All three spellings are real.
DAY_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*,?\s*"
    r"(?:(\d{1,2})/(\d{1,2}))?\s*:?\s*(.*)$", re.I)
# Tolerant of "6-8am" (meridiem only on the end) and "12pm- 1:30 pm" (the page
# breaks that one across lines).
RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\.?\s*[-–—]\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m?\.?", re.I)
# "12pm-2pm Comp Pool" and "11am-2pm @ Comp Pool" both occur.
POOL_RE = re.compile(r"@?\s*((?:comp(?:etition)?|dive|uytengsu|ped)\s*pool)\s*$", re.I)
CLOSED_RE = re.compile(r"\b(closed|n/?a|no\s+\w+\s+rec\s+swim|no\s+rec\s+swim)\b", re.I)

# Windows the page states without naming a pool.
UNATTRIBUTED = "Unattributed"
# Label used when the whole week is closed and no pool is ever named.
CLOSED_WEEK_POOL = "Uytengsu"
# Start of the trailing metadata block; see parse_legacy_block.
TRAILER_RE = re.compile(r"^\*?\s*updated\b", re.I)
# Prose that legitimately appears among the rows and is not a parse failure.
NOTE_RE = re.compile(
    r"(game\s*day|see\s+ped|maintenance|meet|tournament|holiday|practice|"
    r"schedule|notice|subject\s+to\s+change|first[- ]come|lap\s+swim|"
    r"please\s+note|lanes?\s+are)", re.I)

DAY_INDEX = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}


def canonical_pool(name: str) -> str:
    """'Competition Pool' and 'Comp Pool' are the same pool; the page uses both."""
    n = re.sub(r"\s+", " ", name).strip().title()
    n = re.sub(r"^Competition Pool$", "Comp Pool", n, flags=re.I)
    return n


def parse_range(text: str) -> list[int] | None:
    """'6-8am' -> [360,480]. Returns None if it isn't a time range."""
    m = RANGE_RE.search(text)
    if not m:
        return None
    sh, sm, smer, eh, em, emer = m.groups()
    emer = emer.lower()
    end = int(eh) % 12 * 60 + int(em or 0) + (720 if emer == "p" else 0)
    if smer:
        start = int(sh) % 12 * 60 + int(sm or 0) + (720 if smer.lower() == "p" else 0)
    else:
        # No meridiem on the start: assume it shares the end's, and fall back to
        # the other one if that would make the range run backwards. "6-8am" is
        # am-am; "11-1pm" has to be am-pm.
        start = int(sh) % 12 * 60 + int(sm or 0) + (720 if emer == "p" else 0)
        if start >= end:
            start = int(sh) % 12 * 60 + int(sm or 0) + (0 if emer == "p" else 720)
    return [start, end] if end > start else None


def segments(body: str) -> list[str]:
    """Split a day's text into candidate window phrases."""
    body = re.sub(r"\s+", " ", body).strip()
    # Rejoin ranges the page broke mid-number: "12pm- 1:30 pm" -> "12pm-1:30pm"
    body = re.sub(r"([-–—])\s+", r"\1", body)
    body = re.sub(r"(\d)\s+([ap])\.?\s*m\b", r"\1\2m", body, flags=re.I)
    return [s for s in re.split(r"[;\n]|(?<=Pool)\s+(?=\d)", body) if s.strip()]


def parse_legacy_block(text: str, week_start: date) -> tuple[dict[str, list[dict]], list[str]]:
    """Transpose one week's day-grouped text into {pool: [row per day]}.

    Also returns the segments it could not account for. A scraper that quietly
    drops what it doesn't understand looks healthy right up until the page
    changes shape, so anything that is neither a time range nor a closure
    notice comes back to the caller instead of being discarded.
    """
    body_by_day: dict[int, list[str]] = {}
    current: int | None = None

    # Everything from "*Updated" on is document metadata, and updated_label()
    # reads it separately. The page sometimes breaks it across two lines
    # ("*Updated" / "1/12/25"), so match the marker rather than the whole
    # stamp — otherwise it glues onto the last day and breaks attribution.
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if TRAILER_RE.match(ln.strip()):
            lines = lines[:i]
            break

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = DAY_RE.match(line)
        if m:
            name, _mm, _dd, rest = m.groups()
            current = DAY_INDEX[name.lower()]
            body_by_day.setdefault(current, [])
            line = rest.strip()
            if not line:
                continue
        if current is None:
            continue  # preamble before the first day header
        body_by_day[current].append(line)

    windows_by_day: dict[int, list[tuple[str, list[int]]]] = {}
    closed_days: set[int] = set()
    unconsumed: list[str] = []

    for idx, lines in body_by_day.items():
        windows_by_day[idx] = []
        # Join before segmenting: the page splits ranges across lines
        # ("12pm-" / "1:30" / "pm Comp Pool"), so per-line parsing loses them.
        for seg in segments(" ".join(lines)):
            seg = seg.strip(" .,;*")
            if not seg:
                continue
            window = parse_range(seg)
            if window is None:
                if CLOSED_RE.search(seg):
                    closed_days.add(idx)
                elif not NOTE_RE.search(seg):
                    unconsumed.append(seg)
                continue
            pm = POOL_RE.search(seg)
            pool = canonical_pool(pm.group(1)) if pm else UNATTRIBUTED
            windows_by_day[idx].append((pool, window))

    pools_seen = sorted({p for v in windows_by_day.values() for p, _ in v})
    if not pools_seen and body_by_day:
        # A week with every day closed still names no pool. That is a posted
        # schedule, not a broken parse — emit the days so it reads as closed
        # rather than as zero rows, which is what a dead parser looks like.
        pools_seen = [CLOSED_WEEK_POOL]
    out: dict[str, list[dict]] = {p: [] for p in pools_seen}
    for idx in sorted(body_by_day):
        d = week_start + timedelta(days=idx)
        raw = re.sub(r"\s+", " ", " ".join(body_by_day[idx])).strip()
        for pool in pools_seen:
            windows = [w for p, w in windows_by_day[idx] if p == pool]
            # Three states, not two. The page naming one pool's hours says
            # nothing about the other pool, and recording that silence as
            # "closed" invents a fact the source never stated.
            if windows:
                closed = False
            elif idx in closed_days:
                closed = True
            else:
                closed = None
            out[pool].append({
                "weekday": d.strftime("%a"),
                "date": d.isoformat(),
                # The page's own words. A day can be closed for reasons the
                # parser will never model ("*Home Football Game Day"), so keep
                # the text rather than reducing it to a boolean.
                "raw": raw or "Closed",
                "windows": windows,
                "closed": closed,
                "flags": [] if closed is not None else ["not_mentioned"],
            })
    scrape.flag_anomalies(out)
    return out, unconsumed


# ------------------------------------------------------------------ extraction

def extract_legacy_section(html: str) -> str:
    """Normalized text of the Rec Swim block from an archived capture."""
    soup = BeautifulSoup(html, "html.parser")  # lxml chokes on some captures
    start = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if scrape.SECTION_START.search(tag.get_text(" ", strip=True)):
            start = tag
            break
    if start is None:
        raise LookupError("no Rec Swim Hours heading in this capture")

    scope = start.find_parent(class_=ACCORDION)
    if scope is None:  # layout predates the accordion — fall back to the h2 rule
        parts = [str(start)]
        for tag in start.find_all_next():
            if tag.name in ("h1", "h2"):
                break
            if tag.name in scrape.CONTENT_TAGS and not tag.find_parent(scrape.CONTENT_TAGS):
                parts.append(str(tag))
        scope = BeautifulSoup("\n".join(parts), "html.parser")

    text = unicodedata.normalize("NFKC", scope.get_text("\n"))
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    # "Expand"/"Collapse" are the accordion's own controls, not content.
    drop = {"expand", "collapse"}
    return "\n".join(ln for ln in lines if ln and ln.lower() not in drop)


def split_weeks(text: str, captured: date) -> list[tuple[date, str]]:
    """One capture can post several weeks. Return (week_start, text) per week.

    The week header is sometimes its own line ("Week of 11/11/24-11/17/24") and
    sometimes folded into the heading ("Rec Swim Hours week of 10/7/24-10/13/24").
    Both are just a line containing WEEK_RE, so both are handled here.
    """
    lines = text.splitlines()
    marks = [(i, WEEK_RE.search(ln)) for i, ln in enumerate(lines)]
    marks = [(i, m) for i, m in marks if m]
    if not marks:
        return []
    out = []
    for n, (i, m) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(lines)
        month, day = m.group(1).split("/")[:2]
        start = scrape.infer_year(int(month), int(day), captured,
                                  (m.group(1).split("/") + [None])[2])
        if start is None:
            continue
        # The page labels the week by its Monday, but trust the date, not the label.
        start -= timedelta(days=start.weekday())
        out.append((start, "\n".join(lines[i + 1:end])))
    return out


def updated_label(text: str, captured: date) -> str | None:
    m = scrape.UPDATED_RE.search(text)
    if not m:
        return None
    d = scrape.infer_year(int(m.group(1)), int(m.group(2)), captured, m.group(3))
    return d.isoformat() if d else None


# --------------------------------------------------------------------- wayback

CACHE_DIR = Path(__file__).parent / ".wayback-cache"


def _get(url: str, params: dict | None = None, tries: int = 4):
    """The archive 504s and rate-limits freely. Back off rather than give up."""
    delay = 2.0
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, params=params,
                             headers={"User-Agent": scrape.CONTACT}, timeout=120)
            if r.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} from the archive")
            r.raise_for_status()
            return r
        except Exception as exc:
            if attempt == tries:
                raise
            print(f"    {exc} — retry {attempt}/{tries - 1} in {delay:.0f}s",
                  file=sys.stderr)
            time.sleep(delay)
            delay *= 2


def snapshots(since: str) -> list[tuple[str, str]]:
    """(timestamp, digest) for archived captures, newest content only."""
    rows = _get(CDX, {
        "url": LEGACY_URL, "output": "json", "fl": "timestamp,digest",
        "filter": "statuscode:200", "collapse": "digest",
    }).json()[1:]
    return [(ts, dig) for ts, dig in rows if ts >= since]


def fetch_snapshot(ts: str) -> str:
    """Captures are immutable, so cache them on disk and never refetch."""
    CACHE_DIR.mkdir(exist_ok=True)
    cached = CACHE_DIR / f"{ts}.html"
    if cached.exists():
        return cached.read_text()
    text = _get(SNAPSHOT.format(ts=ts, url=LEGACY_URL)).text
    cached.write_text(text)
    return text


def build_entries(since: str, dry_run: bool = False) -> tuple[list[dict], list[dict]]:
    """Return (history entries, per-capture parse reports)."""
    entries, reports = [], []
    seen_hashes = set()
    for ts, _digest in snapshots(since):
        captured = datetime.strptime(ts[:8], "%Y%m%d").date()
        stamp = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=scrape.TZ)
        try:
            html = fetch_snapshot(ts)
            section = extract_legacy_section(html)
        except Exception as exc:
            reports.append({"capture": ts, "status": "failed", "reason": str(exc)[:200]})
            print(f"  {ts}  FAILED  {exc}", file=sys.stderr)
            continue

        weeks = split_weeks(section, captured)
        if not weeks:
            reports.append({"capture": ts, "status": "failed",
                            "reason": "no week header found in the section"})
            print(f"  {ts}  FAILED  no week header", file=sys.stderr)
            continue

        label = updated_label(section, captured)
        for week_start, body in weeks:
            pools, unconsumed = parse_legacy_block(body, week_start)
            parsed = {"updated_label": label, "pools": pools}
            health = scrape.parse_health(parsed, unconsumed)
            digest = hashlib.sha256(
                json.dumps(pools, sort_keys=True).encode()).hexdigest()[:16]
            reports.append({"capture": ts, "week_of": week_start.isoformat(),
                            "status": health["status"], **health})
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            entries.append({
                "checked_at": stamp.isoformat(),
                "content_hash": digest,
                "parsed": parsed,
                "coverage": scrape.coverage(parsed, stamp),
                "parse_health": health,
                # Provenance matters for the stats: a capture time is not a
                # post time, so these can never contribute a post-lag figure.
                "origin": "wayback",
                "generator": {**scrape.generator(), "tool": "backfill.py",
                              "version": VERSION},
                "captured_at": stamp.isoformat(),
                "source": SNAPSHOT.format(ts=ts, url=LEGACY_URL),
            })
            print(f"  {ts}  week of {week_start}  {health['status']:8} "
                  f"rows={health['rows']} windows={health['windows']}")
        time.sleep(0.4)  # the archive is a donation; don't hammer it
    return entries, reports


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default=DEFAULT_SINCE,
                    help="earliest capture timestamp, YYYYMMDD")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report, write nothing")
    args = ap.parse_args()

    print(f"backfilling from {args.since} via the Wayback Machine")
    entries, reports = build_entries(args.since, args.dry_run)
    bad = [r for r in reports if r["status"] != "ok"]
    print(f"\n{len(entries)} entries, {len(reports)} weeks parsed, "
          f"{len(bad)} not clean")
    for r in bad:
        print(f"  {r['status']:8} {r.get('week_of') or r['capture']}: "
              f"{r.get('reason') or r.get('unconsumed')}")
    if args.dry_run:
        return 0

    path = scrape.DATA / "history.json"
    history = scrape.load(path, [])
    live = [h for h in history if h.get("origin") != "wayback"]
    merged = sorted(entries + live, key=lambda h: h["checked_at"])
    path.write_text(json.dumps(merged, indent=2))
    checks = scrape.load(scrape.CACHE, {}).get("checks", {"total": 0, "covered": 0})
    (scrape.DATA / "stats.json").write_text(
        json.dumps(scrape.build_stats(merged, checks), indent=2))
    print(f"\nwrote {len(merged)} history entries -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
