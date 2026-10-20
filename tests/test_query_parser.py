"""
Unit tests for disaster query parsing, date extraction, and temporal classification.
"""

from datetime import datetime
from src.query_parser import (
    DisasterQueryInfo,
    classify_temporal_relation,
    parse_disaster_query,
    parse_publication_date,
)


def test_parse_mumbai_floods_july_2005():
    """Scenario: Mumbai floods, July 2005."""
    info = parse_disaster_query("Mumbai floods July 2005")
    assert info.original_query == "Mumbai floods July 2005"
    assert info.location == "Mumbai"
    assert info.disaster_type == "floods"
    assert info.event_year == 2005
    assert info.event_month == 7
    assert info.event_date_str == "July 2005"
    assert "Mumbai" in info.optimized_search_query
    assert "floods" in info.optimized_search_query
    assert "2005" in info.optimized_search_query


def test_parse_kerala_floods_august_2018():
    """Scenario: Kerala floods, August 2018."""
    info = parse_disaster_query("Kerala floods August 2018")
    assert info.original_query == "Kerala floods August 2018"
    assert info.location == "Kerala"
    assert info.disaster_type == "floods"
    assert info.event_year == 2018
    assert info.event_month == 8
    assert info.event_date_str == "August 2018"
    assert "Kerala" in info.optimized_search_query
    assert "2018" in info.optimized_search_query


def test_parse_query_with_missing_or_ambiguous_date():
    """Scenario: Query with missing or ambiguous date."""
    info = parse_disaster_query("Japan tsunami")
    assert info.original_query == "Japan tsunami"
    assert info.location == "Japan"
    assert info.disaster_type == "tsunami"
    assert info.event_year is None
    assert info.event_month is None
    assert info.event_date_str is None
    assert info.has_event_date is False


def test_parse_publication_date_formats():
    """Tests parsing RFC 2822, ISO 8601, and natural date strings."""
    # RFC 2822
    d1 = parse_publication_date("Mon, 20 Aug 2018 00:00:00 GMT")
    assert d1 is not None
    assert d1.year == 2018
    assert d1.month == 8
    assert d1.day == 20

    # ISO 8601
    d2 = parse_publication_date("2023-05-15T01:55:40Z")
    assert d2 is not None
    assert d2.year == 2023
    assert d2.month == 5

    # Simple string
    d3 = parse_publication_date("26 July 2005")
    assert d3 is not None
    assert d3.year == 2005
    assert d3.month == 7

    # Missing / None
    assert parse_publication_date(None) is None
    assert parse_publication_date("") is None
    assert parse_publication_date("unparseable date string") is None


def test_classify_temporal_relation_contemporaneous():
    info = parse_disaster_query("Mumbai floods July 2005")
    # Same year
    dt_same = datetime(2005, 7, 28)
    cat, explanation = classify_temporal_relation(dt_same, info)
    assert cat == "contemporaneous"
    assert "contemporaneous" in explanation.lower()

    # Early following year
    dt_follow = datetime(2006, 2, 10)
    cat2, _ = classify_temporal_relation(dt_follow, info)
    assert cat2 == "contemporaneous"


def test_classify_temporal_relation_retrospective():
    """Scenario: An article published years after the event."""
    info = parse_disaster_query("Mumbai floods July 2005")
    # Published in 2023 (18 years later)
    dt_retro = datetime(2023, 7, 26)
    cat, explanation = classify_temporal_relation(dt_retro, info)
    assert cat == "retrospective"
    assert "18 years after" in explanation


def test_classify_temporal_relation_missing_date():
    """Scenario: Missing publication dates must be unknown, not invented."""
    info = parse_disaster_query("Mumbai floods July 2005")
    cat, explanation = classify_temporal_relation(None, info)
    assert cat == "unknown"
    assert "not available" in explanation.lower()

    # Missing event date
    info_no_date = parse_disaster_query("Assam floods")
    cat2, explanation2 = classify_temporal_relation(datetime(2021, 6, 1), info_no_date)
    assert cat2 == "unknown"
    assert "not specified" in explanation2.lower()


def test_time_window_rule_not_just_calendar_year():
    """
    Scenario: Proves that classification does NOT simply check calendar year.
    - Pre-event: Published in January 2005 (before July 2005 disaster) is NOT contemporaneous.
    - Contemporaneous: Published in January 2006 (6 months after July 2005) IS contemporaneous.
    - Retrospective: Published in August 2006 (>12 months after July 2005) is retrospective.
    """
    info = parse_disaster_query("Mumbai floods July 2005")

    # 1. Pre-event in same calendar year (Jan 2005 vs Jul 2005)
    dt_pre = datetime(2005, 1, 15)
    cat_pre, expl_pre = classify_temporal_relation(dt_pre, info)
    assert cat_pre == "retrospective"
    assert "prior to" in expl_pre.lower()

    # 2. Immediate aftermath in next calendar year (Jan 2006, 6 months post-event)
    dt_post = datetime(2006, 1, 10)
    cat_post, expl_post = classify_temporal_relation(dt_post, info)
    assert cat_post == "contemporaneous"
    assert "contemporaneous reporting window" in expl_post.lower()

    # 3. Retrospective (>12 months post-event, Aug 2006)
    dt_retro = datetime(2006, 8, 20)
    cat_retro, expl_retro = classify_temporal_relation(dt_retro, info)
    assert cat_retro == "retrospective"
    assert "after" in expl_retro.lower()
