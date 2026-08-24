"""Parser and stats tests.

The fixtures are the point. fixture_week_of_0817 is hand-written and readable;
fixture_live_wpblocks is trimmed from the real page and exists because the real
page nests everything in wp-block divs — the structure that broke extraction.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scrape

FIXTURES = Path(__file__).parent
SIMPLE = (FIXTURES / "fixture_week_of_0817.html").read_text()
LIVE = (FIXTURES / "fixture_live_wpblocks.html").read_text()
MONDAY = date(2026, 8, 17)
THURSDAY = date(2026, 8, 20)


def rows_of(parsed, pool):
    return parsed["pools"][pool]


# ------------------------------------------------------------------ extraction

@pytest.mark.parametrize("html", [SIMPLE, LIVE], ids=["simple", "live"])
def test_extraction_does_not_duplicate_rows(html):
    """Regression: emitting container divs repeated the section verbatim.

    Not a set-uniqueness check — the two pools really do share rows like
    "Sat, 8/22: Closed". The tell is the count, and the repeated headings.
    """
    text = scrape.normalize(scrape.extract_block(html))
    lines = [ln for ln in text.splitlines() if scrape.ROW_RE.match(ln)]
    assert len(lines) == 14                       # 7 days x 2 pools
    assert text.count("Comp Pool") == 1
    assert text.count("Dive Pool") == 1
    # a row unique to one pool must appear exactly once
    assert lines.count("Tue, 8/18: 12pm-1pm") == 1
    assert lines.count("Mon, 8/17: 5pm-6pm") == 1


@pytest.mark.parametrize("html", [SIMPLE, LIVE], ids=["simple", "live"])
def test_extraction_stops_at_the_next_section(html):
    """Regression: an emitted container swallowed everything past the h2."""
    text = scrape.normalize(scrape.extract_block(html)).lower()
    assert "rec swim hours" in text
    assert "basketball" not in text
    assert "court a" not in text


def test_extraction_keeps_both_pools():
    parsed = scrape.parse_block(scrape.extract_block(LIVE), THURSDAY)
    assert list(parsed["pools"]) == ["Comp Pool", "Dive Pool"]
    assert all(len(v) == 7 for v in parsed["pools"].values())


def test_missing_heading_raises_loudly():
    with pytest.raises(LookupError):
        scrape.extract_block("<html><body><h2>Basketball</h2></body></html>")


def test_both_fixtures_agree_on_the_schedule():
    """Different markup, same posted schedule — so parsed rows must match."""
    a = scrape.parse_block(scrape.extract_block(SIMPLE), THURSDAY)
    b = scrape.parse_block(scrape.extract_block(LIVE), THURSDAY)
    assert a["pools"] == b["pools"]
    assert a["updated_label"] == b["updated_label"] == "2026-08-17"


# --------------------------------------------------------------------- parsing

def test_windows_and_closures():
    parsed = scrape.parse_block(scrape.extract_block(SIMPLE), THURSDAY)
    dive = rows_of(parsed, "Dive Pool")
    tue = next(r for r in dive if r["weekday"] == "Tue")
    assert tue["windows"] == [[360, 480], [660, 720], [960, 1080]]
    assert tue["closed"] is False
    mon = next(r for r in rows_of(parsed, "Comp Pool") if r["weekday"] == "Mon")
    assert mon["windows"] == [] and mon["closed"] is True


@pytest.mark.parametrize(
    "value,expected,closed",
    [
        ("6am-8am", [[360, 480]], False),
        ("12pm-1pm", [[720, 780]], False),      # noon, not midnight
        ("12am-1am", [[0, 60]], False),         # midnight, not noon
        ("6:30am-8:15am", [[390, 495]], False),
        ("6am-8am and 4pm-6pm", [[360, 480], [960, 1080]], False),
        # USC writes these three ways in a single week, and the & forms were
        # silently dropped until 2026-08-24.
        ("6am-8am & 4pm-6pm", [[360, 480], [960, 1080]], False),
        ("6am-8am, 11am-12pm & 4pm-6pm",
         [[360, 480], [660, 720], [960, 1080]], False),
        ("6am-8am, 11am-12pm, & 4pm-6pm",
         [[360, 480], [660, 720], [960, 1080]], False),
        ("6am-8am; 4pm-6pm", [[360, 480], [960, 1080]], False),
        ("Closed", [], True),
        ("N/A", [], True),
        ("closed for maintenance", [], True),
        ("8pm-6am", [], False),                 # inverted: dropped, not negative
    ],
)
def test_parse_windows(value, expected, closed):
    assert scrape.parse_windows(value) == (expected, closed)


@pytest.mark.parametrize("prefix", ["Mon", "Tues", "Thurs", "THU", "Wed."])
def test_row_regex_accepts_weekday_spellings(prefix):
    assert scrape.ROW_RE.match(f"{prefix}, 8/17: 6am-8am")


def test_infer_year_picks_the_nearest_january():
    """A 1/2 row seen in late December belongs to next year, not this one."""
    assert scrape.infer_year(1, 2, date(2026, 12, 28), None) == date(2027, 1, 2)
    assert scrape.infer_year(12, 28, date(2027, 1, 2), None) == date(2026, 12, 28)


def test_infer_year_honours_an_explicit_two_digit_year():
    assert scrape.infer_year(8, 17, date(2030, 1, 1), "26") == date(2026, 8, 17)


def test_infer_year_returns_none_on_an_impossible_date():
    assert scrape.infer_year(2, 30, date(2026, 3, 1), "26") is None


# -------------------------------------------------------------------- anomalies

def test_typod_date_is_the_outlier_not_the_anchor():
    """Sun 8/16 is last week's Sunday. Six good rows must outvote it."""
    parsed = scrape.parse_block(scrape.extract_block(SIMPLE), THURSDAY)
    comp = rows_of(parsed, "Comp Pool")
    bad = [r for r in comp if r["flags"]]
    assert len(bad) == 1
    assert bad[0]["date"] == "2026-08-16"
    assert bad[0]["flags"] == ["outside_posted_week"]


def test_weekday_date_mismatch_is_flagged():
    pools = {"P": [
        {"weekday": "Mon", "date": "2026-08-17", "flags": []},
        {"weekday": "Tue", "date": "2026-08-18", "flags": []},
        {"weekday": "Fri", "date": "2026-08-19", "flags": []},  # 8/19 is a Wed
    ]}
    scrape.flag_anomalies(pools)
    assert pools["P"][2]["flags"] == ["weekday_date_mismatch"]
    assert not pools["P"][0]["flags"] and not pools["P"][1]["flags"]


def test_unparsed_date_is_flagged_not_dropped():
    pools = {"P": [
        {"weekday": "Mon", "date": "2026-08-17", "flags": []},
        {"weekday": "Tue", "date": None, "flags": []},
    ]}
    scrape.flag_anomalies(pools)
    assert pools["P"][1]["flags"] == ["unparsed_date"]
    assert len(pools["P"]) == 2


# --------------------------------------------------------------------- coverage

def _at(d, hour=9):
    return datetime(d.year, d.month, d.day, hour, tzinfo=scrape.TZ)


def test_coverage_counts_only_windows_for_today():
    parsed = scrape.parse_block(scrape.extract_block(SIMPLE), THURSDAY)
    cov = scrape.coverage(parsed, _at(date(2026, 8, 18)))  # Tue
    assert cov["today_covered"] is True
    assert cov["swimmable_today"] == 4       # comp 1 + dive 3
    assert cov["posted_through"] == "2026-08-22"
    assert cov["days_past_end"] == 0


def test_coverage_is_false_past_the_end_of_the_posted_week():
    parsed = scrape.parse_block(scrape.extract_block(SIMPLE), THURSDAY)
    cov = scrape.coverage(parsed, _at(date(2026, 8, 25)))
    assert cov["today_covered"] is False
    assert cov["days_past_end"] == 3


def test_coverage_ignores_the_out_of_week_row():
    """8/16 is posted but flagged, so it must not count as coverage."""
    parsed = scrape.parse_block(scrape.extract_block(SIMPLE), THURSDAY)
    cov = scrape.coverage(parsed, _at(date(2026, 8, 16)))
    assert cov["today_covered"] is False


def test_coverage_with_nothing_parsed():
    cov = scrape.coverage({"pools": {}}, _at(THURSDAY))
    assert cov == {
        "today": "2026-08-20", "today_covered": False, "posted_through": None,
        "days_past_end": None, "swimmable_today": None,
    }


# ------------------------------------------------------------------------ stats

def _entry(checked_at, first_date):
    d = date.fromisoformat(first_date)
    return {
        "checked_at": checked_at,
        "parsed": {"pools": {"P": [
            {"date": (d + timedelta(days=i)).isoformat(), "flags": []}
            for i in range(7)
        ]}},
        "coverage": {},
    }


def test_first_history_entry_is_left_censored():
    history = [_entry("2026-08-19T09:00:00-07:00", "2026-08-17")]
    stats = scrape.build_stats(history, {"total": 1, "covered": 0})
    assert stats["weeks"][0]["censored"] is True
    assert stats["median_post_lag_hours"] is None  # censored weeks excluded


def test_post_lag_is_measured_from_that_weeks_monday():
    history = [
        _entry("2026-08-19T09:00:00-07:00", "2026-08-17"),   # censored
        _entry("2026-08-25T12:00:00-07:00", "2026-08-24"),   # Mon 8/24 + 36h
    ]
    stats = scrape.build_stats(history, {"total": 2, "covered": 1})
    later = next(w for w in stats["weeks"] if w["week_of"] == "2026-08-24")
    assert later["censored"] is False
    assert later["lag_hours"] == 36.0
    assert stats["median_post_lag_hours"] == 36.0


def test_coverage_rate_is_reported_over_checks_not_changes():
    stats = scrape.build_stats([], {"total": 8, "covered": 6})
    assert stats["checks_total"] == 8
    assert stats["changes_total"] == 0
    assert stats["coverage_rate"] == 0.75


def test_stats_survive_an_empty_dataset():
    stats = scrape.build_stats([], {})
    assert stats["coverage_rate"] is None
    assert stats["median_post_lag_hours"] is None
    assert stats["weeks"] == []


# ------------------------------------------------- windows going missing

def test_a_row_that_loses_windows_is_flagged():
    """The failure that got through: a row can match ROW_RE, look parsed, and
    still drop half its hours in the value splitter."""
    block = (
        "<h3>Rec Swim Hours</h3><h3>Dive Pool</h3>"
        "<p>Tue, 8/25: 6am-8am &amp; 4pm-6pm</p>"
    )
    parsed = scrape.parse_block(block, date(2026, 8, 25))
    row = parsed["pools"]["Dive Pool"][0]
    assert row["windows"] == [[360, 480], [960, 1080]]
    assert "windows_dropped" not in row["flags"]


def test_dropped_windows_drive_the_health_status():
    """A row holding more ranges than we extracted is the parser failing."""
    parsed = {"pools": {"P": [
        {"windows": [[360, 480]], "flags": ["windows_dropped"]},
    ]}}
    health = scrape.parse_health(parsed, [])
    assert health["status"] == "degraded"
    assert health["rows_with_dropped_windows"] == 1


def test_a_clean_row_reports_no_dropped_windows():
    parsed = {"pools": {"P": [{"windows": [[360, 480]], "flags": []}]}}
    health = scrape.parse_health(parsed, [])
    assert health["status"] == "ok"
    assert health["rows_with_dropped_windows"] == 0


@pytest.mark.parametrize(
    "value,expected_ranges",
    [
        ("6am-8am", 1),
        ("6am-8am & 4pm-6pm", 2),
        ("6am-8am, 11am-12pm, & 4pm-6pm", 3),
        ("12pm-1pm", 1),
        ("Closed", 0),
        ("USC hosting a WP match", 0),
    ],
)
def test_range_counter_sees_what_the_text_holds(value, expected_ranges):
    """The counter is the independent check on the splitter, so it must not
    share the splitter's assumptions about separators."""
    assert len(scrape.RANGE_RE.findall(value)) == expected_ranges
