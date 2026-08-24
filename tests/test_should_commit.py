"""The gate that decides whether a check is worth a commit.

Without it every run commits, because `checked_at` moves whether or not USC
changed anything — hundreds of empty commits a month, burying the few that
record a real schedule change.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import should_commit


def snapshot(**over):
    base = {
        "checked_at": "2026-08-23T20:00:00-07:00",
        "content_hash": "abc123",
        "conditional_304": False,
        "coverage": {"today_covered": True},
    }
    base.update(over)
    return base


# ------------------------------------------------------------- significance

def test_a_new_content_hash_is_significant():
    assert should_commit.significant(snapshot(content_hash="different"), snapshot())


def test_changed_coverage_is_significant():
    assert should_commit.significant(
        snapshot(coverage={"today_covered": False}), snapshot()
    )


def test_a_moved_timestamp_alone_is_not_significant():
    assert not should_commit.significant(
        snapshot(checked_at="2026-08-23T21:00:00-07:00"), snapshot()
    )


def test_a_304_flag_flip_alone_is_not_significant():
    """Whether a check was served from cache says nothing about the schedule."""
    assert not should_commit.significant(snapshot(conditional_304=True), snapshot())


def test_nothing_committed_yet_is_significant():
    assert should_commit.significant(snapshot(), None)


# ------------------------------------------------------------------- gating

@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A fake docs/data plus a controllable notion of what's committed."""
    data = tmp_path / "docs" / "data"
    data.mkdir(parents=True)
    monkeypatch.setattr(should_commit, "DATA", data)

    state: dict[str, object] = {}
    monkeypatch.setattr(should_commit, "committed", lambda path: state.get(path))

    def write(latest, history=None, stats=None):
        import json
        (data / "latest.json").write_text(json.dumps(latest))
        (data / "history.json").write_text(json.dumps(history if history is not None else []))
        (data / "stats.json").write_text(json.dumps(stats if stats is not None else {}))

    return write, state


def test_commits_when_the_schedule_changed(repo):
    write, state = repo
    state["docs/data/latest.json"] = snapshot()
    state["docs/data/history.json"] = []
    state["docs/data/stats.json"] = {}
    write(snapshot(content_hash="new"))
    assert should_commit.main() == 0


def test_skips_when_only_the_timestamp_moved(repo):
    write, state = repo
    recent = datetime.now().astimezone() - timedelta(hours=2)
    state["docs/data/latest.json"] = snapshot(checked_at=recent.isoformat())
    state["docs/data/history.json"] = []
    state["docs/data/stats.json"] = {}
    write(snapshot(checked_at=datetime.now().astimezone().isoformat()))
    assert should_commit.main() == 1


def test_commits_when_history_grew(repo):
    """A new snapshot in the dataset is the whole point of the project."""
    write, state = repo
    now = datetime.now().astimezone().isoformat()
    state["docs/data/latest.json"] = snapshot(checked_at=now)
    state["docs/data/history.json"] = []
    state["docs/data/stats.json"] = {}
    write(snapshot(checked_at=now), history=[{"content_hash": "abc123"}])
    assert should_commit.main() == 0


def test_refreshes_a_stale_timestamp_even_with_no_change(repo):
    """Otherwise a quiet week makes the site look abandoned."""
    write, state = repo
    stale = datetime.now().astimezone() - timedelta(hours=30)
    state["docs/data/latest.json"] = snapshot(checked_at=stale.isoformat())
    state["docs/data/history.json"] = []
    state["docs/data/stats.json"] = {}
    write(snapshot(checked_at=datetime.now().astimezone().isoformat()))
    assert should_commit.main() == 0


def test_commits_when_nothing_is_committed_yet(repo):
    write, state = repo
    write(snapshot())
    assert should_commit.main() == 0


def test_a_bumped_check_counter_alone_is_not_significant():
    """stats.json counts every check, so its counters tick without news.

    Missed on the first pass: the gate held on latest.json and then committed
    anyway because stats.json had incremented.
    """
    before = {"checks_total": 8, "coverage_rate": 0.5, "changes_total": 3,
              "checks_with_today_covered": 4, "median_post_lag_hours": 12.0}
    after = {**before, "checks_total": 9, "coverage_rate": 0.444,
             "checks_with_today_covered": 4}
    assert not should_commit.significant(after, before, "docs/data/stats.json")


def test_a_new_recorded_schedule_is_significant_in_stats():
    before = {"checks_total": 8, "changes_total": 3, "median_post_lag_hours": 12.0}
    after = {"checks_total": 9, "changes_total": 4, "median_post_lag_hours": 12.0}
    assert should_commit.significant(after, before, "docs/data/stats.json")


def test_a_moved_post_lag_median_is_significant():
    before = {"checks_total": 8, "changes_total": 3, "median_post_lag_hours": 12.0}
    after = {"checks_total": 9, "changes_total": 3, "median_post_lag_hours": 36.0}
    assert should_commit.significant(after, before, "docs/data/stats.json")


def test_skips_when_only_the_check_counters_moved(repo):
    write, state = repo
    now = datetime.now().astimezone().isoformat()
    state["docs/data/latest.json"] = snapshot(checked_at=now)
    state["docs/data/history.json"] = []
    state["docs/data/stats.json"] = {"checks_total": 8, "coverage_rate": 0.5,
                                     "changes_total": 3}
    write(snapshot(checked_at=now), stats={"checks_total": 9,
                                           "coverage_rate": 0.444,
                                           "changes_total": 3})
    assert should_commit.main() == 1
