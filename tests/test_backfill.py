"""Legacy (pre-redesign) parser, and the parse-health signal.

Every fixture here is a real Wayback capture trimmed to its accordion item.
They were chosen because each one broke something: windows with no pool named,
a time range split across three lines, a week where everything is closed, and
the ordinary case that has to keep working while the others are handled.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backfill
import scrape

F = Path(__file__).parent


def load(name):
    return (F / f"fixture_legacy_{name}.html").read_text()


def parse_one(name, captured):
    """Extract, split, and parse the first week of a capture."""
    section = backfill.extract_legacy_section(load(name))
    weeks = backfill.split_weeks(section, captured)
    pools, unconsumed = backfill.parse_legacy_block(weeks[0][1], weeks[0][0])
    return weeks[0][0], pools, unconsumed, section


# ------------------------------------------------------------------ extraction

def test_section_is_scoped_to_the_accordion_item():
    """The archived page runs basketball and tennis past the swim section."""
    section = backfill.extract_legacy_section(load("typical_week")).lower()
    assert "rec swim hours" in section
    assert "basketball" not in section
    assert "pickleball" not in section
    # accordion chrome is not content
    assert "expand" not in section.splitlines()


def test_missing_section_raises():
    with pytest.raises(LookupError):
        backfill.extract_legacy_section("<html><body><p>nothing</p></body></html>")


# ---------------------------------------------------------------- week parsing

def test_typical_week_parses_two_pools_cleanly():
    start, pools, unconsumed, _ = parse_one("typical_week", date(2026, 3, 23))
    assert start == date(2026, 3, 23)
    assert sorted(pools) == ["Comp Pool", "Dive Pool"]
    assert all(len(v) == 7 for v in pools.values())
    assert unconsumed == []


def test_updated_label_survives_being_split_across_lines():
    """The page emits '*Updated' and '1/12/25' as separate lines."""
    section = backfill.extract_legacy_section(load("typical_week"))
    assert backfill.updated_label(section, date(2026, 3, 23)) == "2026-03-23"


def test_trailing_updated_stamp_does_not_steal_the_last_row():
    """Regression: '*Updated' glued onto Sunday and broke pool attribution."""
    _, pools, _, _ = parse_one("typical_week", date(2026, 3, 23))
    assert "Unattributed" not in pools
    sunday = next(r for r in pools["Comp Pool"] if r["weekday"] == "Sun")
    assert sunday["windows"] == [[660, 840]]  # 11am-2pm


def test_a_capture_can_post_more_than_one_week():
    section = backfill.extract_legacy_section(load("two_weeks_linebreak"))
    weeks = backfill.split_weeks(section, date(2024, 11, 19))
    assert [w[0] for w in weeks] == [date(2024, 11, 11), date(2024, 11, 18)]


def test_time_range_broken_across_lines_is_recovered():
    """The page renders '12pm-', '1:30', 'pm Comp Pool' on three lines.

    Parsing line-by-line dropped the window AND marked the day closed.
    """
    section = backfill.extract_legacy_section(load("two_weeks_linebreak"))
    week_start, body = backfill.split_weeks(section, date(2024, 11, 19))[0]
    pools, _ = backfill.parse_legacy_block(body, week_start)
    sat = next(r for r in pools["Comp Pool"] if r["weekday"] == "Sat")
    assert sat["windows"] == [[720, 810]]   # 12:00pm - 1:30pm
    assert sat["closed"] is False


def test_competition_pool_and_comp_pool_are_one_pool():
    section = backfill.extract_legacy_section(load("two_weeks_linebreak"))
    week_start, body = backfill.split_weeks(section, date(2024, 11, 19))[1]
    pools, _ = backfill.parse_legacy_block(body, week_start)
    assert sorted(pools) == ["Comp Pool", "Dive Pool"]


def test_a_pool_the_page_never_mentions_is_unknown_not_closed():
    """Silence about a pool is not a statement that it is closed."""
    section = backfill.extract_legacy_section(load("two_weeks_linebreak"))
    week_start, body = backfill.split_weeks(section, date(2024, 11, 19))[0]
    pools, _ = backfill.parse_legacy_block(body, week_start)
    sunday = next(r for r in pools["Dive Pool"] if r["weekday"] == "Sun")
    assert sunday["windows"] == []
    assert sunday["closed"] is None                 # not False, not True
    assert "not_mentioned" in sunday["flags"]


def test_an_explicitly_closed_week_is_closed_not_unknown():
    _, pools, _, _ = parse_one("week_all_closed", date(2025, 8, 7))
    rows = [r for v in pools.values() for r in v]
    assert len(rows) == 7
    assert all(r["closed"] is True for r in rows)
    assert all(r["windows"] == [] for r in rows)


# ------------------------------------------------------------- time range edge

@pytest.mark.parametrize(
    "text,expected",
    [
        ("6-8am", [360, 480]),              # meridiem only on the end
        ("6am-8am", [360, 480]),
        ("11am-12pm", [660, 720]),
        ("12pm-2pm", [720, 840]),
        ("11-1pm", [660, 780]),             # start must flip to am
        ("6:00am-7:00am", [360, 420]),
        ("12pm-1:30pm", [720, 810]),
        ("4pm-6pm", [960, 1080]),
        ("nonsense", None),
        ("Closed", None),
    ],
)
def test_parse_range(text, expected):
    assert backfill.parse_range(text) == expected


# ----------------------------------------------------------------- parse health

def _health(name, captured):
    start, pools, unconsumed, section = parse_one(name, captured)
    return scrape.parse_health({"pools": pools}, unconsumed)


def test_a_clean_week_reports_ok():
    assert _health("typical_week", date(2026, 3, 23))["status"] == "ok"


def test_an_all_closed_week_is_ok_not_failed():
    """Zero windows is a real schedule. Zero rows is a broken parser."""
    h = _health("week_all_closed", date(2025, 8, 7))
    assert h["status"] == "ok"
    assert h["rows"] == 7 and h["windows"] == 0


def test_windows_with_no_pool_named_are_degraded():
    h = _health("weekhdr_unattributed", date(2024, 10, 12))
    assert h["status"] == "degraded"
    assert h["unattributed_windows"] > 0


def test_nothing_parsed_is_failed():
    assert scrape.parse_health({"pools": {}})["status"] == "failed"


def test_a_source_typo_does_not_read_as_a_broken_parser():
    """A wrong date is the page's fault; it must not say 'fix the parser'."""
    parsed = {"pools": {"P": [
        {"windows": [[360, 480]], "flags": ["outside_posted_week"]},
        {"windows": [[360, 480]], "flags": []},
    ]}}
    h = scrape.parse_health(parsed, [])
    assert h["status"] == "ok"          # parser worked fine
    assert h["anomaly_rows"] == 1       # but the anomaly is still reported


def test_not_mentioned_is_not_an_anomaly():
    parsed = {"pools": {"P": [{"windows": [], "flags": ["not_mentioned"]}]}}
    h = scrape.parse_health(parsed, [])
    assert h["anomaly_rows"] == 0
    assert h["status"] == "ok"


def test_unrecognised_lines_are_reported_verbatim():
    parsed = {"pools": {"P": [{"windows": [[1, 2]], "flags": []}]}}
    h = scrape.parse_health(parsed, ["Aqua Zumba 5pm-6pm", "Masters 7am"])
    assert h["status"] == "degraded"
    assert h["unconsumed_total"] == 2
    assert "Aqua Zumba 5pm-6pm" in h["unconsumed"]
