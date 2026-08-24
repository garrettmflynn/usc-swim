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
# Fields that change on every check and mean nothing on their own.
NOISE = {"checked_at", "conditional_304"}


def committed(path: str) -> dict | list | None:
    try:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            capture_output=True, text=True, check=True,
        ).stdout
        return json.loads(blob)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def significant(current: dict, previous: dict | None) -> bool:
    if previous is None:
        return True
    return {k: v for k, v in current.items() if k not in NOISE} != {
        k: v for k, v in previous.items() if k not in NOISE
    }


def main() -> int:
    latest = json.loads((DATA / "latest.json").read_text())
    previous = committed("docs/data/latest.json")

    if significant(latest, previous):
        print("schedule content differs from HEAD — committing")
        return 0

    for name in ("history.json", "stats.json"):
        if json.loads((DATA / name).read_text()) != committed(f"docs/data/{name}"):
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
