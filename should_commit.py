#!/usr/bin/env python3
"""Decide whether docs/data is worth a commit. Exit 0 to commit, 1 to skip.

Every check rewrites latest.json, because `checked_at` moves whether or not
USC changed anything. Left alone that produces a commit per run — hundreds a
month, none of which say anything — and buries the handful of commits that
record an actual schedule change.

So: commit when something meaningful differs from what is already committed,
and otherwise only often enough that the "last checked" stamp on the site
doesn't look abandoned.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "docs" / "data"
# How stale the committed timestamp may get while nothing is changing.
MAX_SILENCE = timedelta(hours=24)
# Fields that move on every check and say nothing about the schedule.
#
# latest.json stamps the time; stats.json counts the check. Both tick whether
# or not USC touched anything, so both have to be excluded — leaving either in
# means a commit per run, which is the thing this file exists to prevent.
NOISE = {
    "docs/data/latest.json": {"checked_at", "conditional_304"},
    "docs/data/stats.json": {
        "checks_total",
        "checks_with_today_covered",
        # derived from the counters above, so it moves with them
        "coverage_rate",
    },
    "docs/data/history.json": set(),
}


def committed(path: str) -> dict | list | None:
    try:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            capture_output=True, text=True, check=True,
        ).stdout
        return json.loads(blob)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def strip(value, path: str):
    """Drop the per-check bookkeeping so only real differences remain."""
    noise = NOISE.get(path, set())
    if not isinstance(value, dict) or not noise:
        return value
    return {k: v for k, v in value.items() if k not in noise}


def significant(current, previous, path: str = "docs/data/latest.json") -> bool:
    if previous is None:
        return True
    return strip(current, path) != strip(previous, path)


def main() -> int:
    latest = json.loads((DATA / "latest.json").read_text())
    previous = committed("docs/data/latest.json")

    if significant(latest, previous):
        print("schedule content differs from HEAD — committing")
        return 0

    for name in ("history.json", "stats.json"):
        path = f"docs/data/{name}"
        current = json.loads((DATA / name).read_text())
        if significant(current, committed(path), path):
            print(f"{name} differs from HEAD — committing")
            return 0

    if previous is None or "checked_at" not in previous:
        print("no committed timestamp to compare — committing")
        return 0

    age = datetime.now().astimezone() - datetime.fromisoformat(previous["checked_at"])
    if age > MAX_SILENCE:
        print(f"nothing changed, but the committed check is {age} old — refreshing")
        return 0

    print(f"only the timestamp moved ({age} since the last commit) — skipping")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
