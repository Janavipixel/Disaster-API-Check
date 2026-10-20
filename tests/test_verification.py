"""
Unit tests for source quality evaluation, filtering, deduplication, and cross-source verification.
Covers:
  - Irrelevant search result filtering
  - Low-value domain filtering (social media, video-only)
  - Duplicate result detection
  - Conflicting claims across sources
  - Corroborated facts across sources
  - Missing publication date handling
"""

from src.models import SearchResult
from src.query_parser import parse_disaster_query
from src.verification import (
    evaluate_domain_credibility,
    extract_domain,
    perform_cross_verification,
    process_and_filter_results,
    synthesize_incident_summary,
)


def test_domain_credibility_tiering():
    assert evaluate_domain_credibility("ndma.gov.in")[0] == "official_or_academic"
    assert evaluate_domain_credibility("thehindu.com")[0] == "established_news"
    assert evaluate_domain_credibility("reuters.com")[0] == "established_news"
    assert evaluate_domain_credibility("twitter.com")[0] == "low_value"
    assert evaluate_domain_credibility("youtube.com")[0] == "low_value"
    assert evaluate_domain_credibility("someblog.xyz")[0] == "general_web"


def test_filter_irrelevant_search_result():
    """Scenario 4: An irrelevant search result is detected and filtered."""
    event_info = parse_disaster_query("Mumbai floods July 2005")

    relevant = SearchResult(
        title="2005 Maharashtra floods in Mumbai",
        url="https://en.wikipedia.org/wiki/2005_Maharashtra_floods",
        content="On 26 July 2005, Mumbai experienced torrential rainfall and severe flooding.",
        score=0.92,
        published_date="2005-08-10",
    )
    irrelevant = SearchResult(
        title="Top 10 Bollywood Action Movies of 2005",
        url="https://example.com/bollywood-movies-2005",
        content="A review of the best box office cinema hits released in Indian theaters.",
        score=0.35,
        published_date="2005-12-01",
    )

    retained, filtered = process_and_filter_results([relevant, irrelevant], event_info)

    assert len(retained) == 1
    assert retained[0].title == "2005 Maharashtra floods in Mumbai"
    assert len(filtered) == 1
    assert filtered[0].title == "Top 10 Bollywood Action Movies of 2005"
    assert filtered[0].is_filtered is True
    assert "Irrelevant" in filtered[0].filter_reason


def test_filter_low_value_social_and_video():
    """Identifies and filters low-value social media and video links."""
    event_info = parse_disaster_query("Kerala floods August 2018")

    yt_result = SearchResult(
        title="Drone footage of Kerala Floods 2018",
        url="https://www.youtube.com/watch?v=abcd1234",
        content="Video showing flooded roads in Alappuzha.",
        score=0.75,
    )
    tweet_result = SearchResult(
        title="Update on Twitter: Floods in Wayanad",
        url="https://twitter.com/user/status/12345678",
        content="Help needed in Wayanad relief camp.",
        score=0.72,
    )

    retained, filtered = process_and_filter_results([yt_result, tweet_result], event_info)
    assert len(retained) == 0
    assert len(filtered) == 2
    assert any("Low-value" in f.filter_reason for f in filtered)


def test_detect_and_filter_duplicate_results():
    """Scenario 7: Duplicate results are identified and filtered."""
    event_info = parse_disaster_query("Mumbai floods July 2005")

    item1 = SearchResult(
        title="Over 1,000 dead in Mumbai floods - News",
        url="https://thehindu.com/news/national/mumbai-floods-2005.html?utm_source=feed",
        content="On 26 July 2005, Mumbai recorded 944 mm of rainfall resulting in devastating floods.",
        score=0.95,
        published_date="2005-07-28",
    )
    # Duplicate with different tracking param and slightly different whitespace
    item2 = SearchResult(
        title="Over 1,000 dead in Mumbai floods - News",
        url="https://thehindu.com/news/national/mumbai-floods-2005.html",
        content="On 26 July 2005, Mumbai recorded 944 mm of rainfall resulting in devastating floods.",
        score=0.94,
        published_date="2005-07-28",
    )

    retained, filtered = process_and_filter_results([item1, item2], event_info)
    assert len(retained) == 1
    assert len(filtered) == 1
    assert filtered[0].is_duplicate is True
    assert "Duplicate" in filtered[0].filter_reason


def test_conflicting_claims_across_sources():
    """Scenario 8: Conflicting claims (e.g. differing casualty figures) are flagged."""
    event_info = parse_disaster_query("Kerala floods August 2018")

    r1 = SearchResult(
        title="Over 300 dead in Kerala Floods - FloodList",
        url="https://floodlist.com/asia/kerala-floods-august-2018",
        content="Over 300 dead in Kerala floods following relentless monsoon rains in August.",
        score=0.93,
        domain="floodlist.com",
        source_credibility="official_or_academic",
        temporal_category="contemporaneous",
    )
    r2 = SearchResult(
        title="Chief Minister Statement on Kerala Disaster",
        url="https://thehindu.com/news/kerala-cmo-toll",
        content="Chief Minister office confirms 324 lives lost in Kerala flood relief operations.",
        score=0.91,
        domain="thehindu.com",
        source_credibility="established_news",
        temporal_category="contemporaneous",
    )
    r3 = SearchResult(
        title="Retrospective Analysis of 2018 Floods",
        url="https://downtoearth.org.in/kerala-floods-review",
        content="Final disaster reports show less than 500 fatalities were recorded due to swift evacuation.",
        score=0.88,
        domain="downtoearth.org.in",
        source_credibility="official_or_academic",
        temporal_category="retrospective",
    )

    report = perform_cross_verification([r1, r2, r3], event_info)
    assert len(report.conflicting_claims) >= 1
    conf_text = report.conflicting_claims[0].lower()
    assert "casualty" in conf_text or "vary" in conf_text


def test_corroborated_rainfall_facts():
    """Scenario: Multiple independent sources report the same meteorological fact."""
    event_info = parse_disaster_query("Mumbai floods July 2005")

    r1 = SearchResult(
        title="Mumbai 26 July Record Rainfall",
        url="https://imd.gov.in/mumbai-2005-record",
        content="Mumbai city received an unprecedented 944 mm of rainfall in 24 hours on 26 July.",
        score=0.96,
        domain="imd.gov.in",
        source_credibility="official_or_academic",
        temporal_category="contemporaneous",
    )
    r2 = SearchResult(
        title="Analysis of the 2005 Mumbai Deluge",
        url="https://thehindu.com/analysis-mumbai-floods",
        content="On 26 July 2005, a staggering 944 mm of rain paralyzed the financial capital.",
        score=0.92,
        domain="thehindu.com",
        source_credibility="established_news",
        temporal_category="retrospective",
    )

    report = perform_cross_verification([r1, r2], event_info)
    assert any("944 mm" in fact for fact in report.corroborated_facts)
    assert any("corroborated across" in fact for fact in report.corroborated_facts)


def test_evidence_based_summary_synthesis():
    event_info = parse_disaster_query("Kerala floods August 2018")
    r1 = SearchResult(
        title="Kerala Floods 2018",
        url="https://reliefweb.int/report/kerala",
        content="Over 300 dead in Kerala floods across 14 districts.",
        domain="reliefweb.int",
    )
    report = perform_cross_verification([r1], event_info)
    summary = synthesize_incident_summary(event_info, [r1], report)

    assert "Kerala" in summary
    assert "floods" in summary
    assert "August 2018" in summary


def test_cbs_news_credibility_mapping():
    """Issue 3: Verify CBS News domain is classified as established_news, not general_web."""
    tier, desc = evaluate_domain_credibility("cbsnews.com")
    assert tier == "established_news"
    assert "reputable news" in desc.lower()

    tier2, _ = evaluate_domain_credibility("cbs.com")
    assert tier2 == "established_news"


def test_mumbai_rainfall_unit_normalization():
    """Issue 2: Verify rainfall unit normalization (millimetres vs mm) matches the same underlying claim."""
    event_info = parse_disaster_query("Mumbai floods July 2005")

    r1 = SearchResult(
        title="2005 Deluge on July 26",
        url="https://hindustantimes.com/cities/mumbai-news/deluge-2005",
        content="On July 26, 944 millimetres of rain flooded Mumbai in 24 hours.",
        domain="hindustantimes.com",
    )
    r2 = SearchResult(
        title="Rising Tides: Mumbai Floods",
        url="https://resilience.org/stories/rising-tides-mumbai",
        content="Torrential downpours recorded 944 mm of rain across Mumbai suburban areas.",
        domain="resilience.org",
    )

    report = perform_cross_verification([r1, r2], event_info)
    # Both normalize to '944 mm' and corroborate across the 2 domains
    assert any("944 mm" in fact for fact in report.corroborated_facts)
    rain_claim = next(c for c in report.verified_claims if c.topic == "Rainfall Measurement")
    assert rain_claim.status == "corroborated"
    assert len(rain_claim.sources) == 2
    domains = [s["domain"] for s in rain_claim.sources]
    assert "hindustantimes.com" in domains
    assert "resilience.org" in domains


def test_mumbai_casualty_scale_corroboration():
    """Issue 1 & 2: Verify casualty counts with consistent scale (e.g. 1094 vs over 1,000) corroborate."""
    event_info = parse_disaster_query("Mumbai floods July 2005")

    r1 = SearchResult(
        title="2005 Deluge: July 26",
        url="https://hindustantimes.com/deluge-2005",
        content="Heavy rain caused catastrophic urban flooding, claiming 1094 lives across Mumbai.",
        domain="hindustantimes.com",
    )
    r2 = SearchResult(
        title="Mumbai Flooding Challenges",
        url="https://resilience.org/mumbai-floods",
        content="The floods resulted in the death of over 1,000 people and extensive damage.",
        domain="resilience.org",
    )

    report = perform_cross_verification([r1, r2], event_info)
    cas_claim = next(c for c in report.verified_claims if c.topic == "Casualty Figures")
    assert cas_claim.status == "corroborated"
    assert len(cas_claim.sources) == 2
    assert "1000" in cas_claim.claim or "1094" in cas_claim.claim or "fatalities" in cas_claim.claim
    # Check URLs are attached
    assert any("hindustantimes.com" in s["url"] for s in cas_claim.sources)
    assert any("resilience.org" in s["url"] for s in cas_claim.sources)


def test_syndicated_reprints_not_counted_as_independent():
    """Issue 2: Verify identical syndicated text across different domains is deduplicated."""
    event_info = parse_disaster_query("Kerala floods August 2018")

    r1 = SearchResult(
        title="Kerala floods update wire report",
        url="https://newsportal-a.com/wire/kerala-floods",
        content="The state government declared high alert as continuous torrential monsoon rains triggered catastrophic landslides across multiple districts.",
        domain="newsportal-a.com",
    )
    # Syndicated wire copy on another domain with identical text
    r2 = SearchResult(
        title="Kerala floods update wire report",
        url="https://newsportal-b.com/wire/kerala-floods-copy",
        content="The state government declared high alert as continuous torrential monsoon rains triggered catastrophic landslides across multiple districts.",
        domain="newsportal-b.com",
    )

    retained, filtered = process_and_filter_results([r1, r2], event_info)
    assert len(retained) == 1
    assert len(filtered) == 1
    assert filtered[0].is_duplicate is True
    assert "syndicated" in filtered[0].filter_reason.lower() or "duplicate" in filtered[0].filter_reason.lower()


def test_retrospective_historical_sources_retained():
    """Issue 4: Verify useful retrospective historical sources are retained, not filtered."""
    event_info = parse_disaster_query("Mumbai floods July 2005")

    retro_source = SearchResult(
        title="20 Years on, July 26 Deluge Memories Return to Haunt City Residents",
        url="https://deccanherald.com/india/maharashtra/mumbai-floods-20-years-on-deluge",
        content="The deluge of July 26, 2005 was the worst urban flood disaster in Mumbai history, submerging road and rail corridors.",
        published_date="2025-07-26",
        domain="deccanherald.com",
    )

    retained, filtered = process_and_filter_results([retro_source], event_info)
    assert len(retained) == 1
    assert len(filtered) == 0
    assert retained[0].temporal_category == "retrospective"
    assert "retrospective" in retained[0].relevance_explanation.lower()


def test_claim_evidence_structure_and_urls():
    """Issue 7: Verify every claim has supporting source URLs, quotes, and evidence explanation."""
    event_info = parse_disaster_query("Kerala floods August 2018")

    r1 = SearchResult(
        title="Kerala historic floods",
        url="https://cbsnews.com/news/kerala-historic-floods-2018",
        content="Rescue efforts continue in Kerala as 800,000 people displaced, more than 350 killed.",
        domain="cbsnews.com",
    )

    report = perform_cross_verification([r1], event_info)
    assert len(report.verified_claims) >= 1

    for claim in report.verified_claims:
        assert claim.topic
        assert claim.claim
        assert claim.status in {"corroborated", "single_source", "conflicting", "unverified"}
        assert claim.evidence_explanation
        if claim.status in {"corroborated", "single_source", "conflicting"}:
            assert len(claim.sources) >= 1
            for s in claim.sources:
                assert s["url"].startswith("http")
                assert s["domain"]
                assert s["quote"]


def test_unverified_claim_handling():
    """Issue 7: Verify that missing factual claims are explicitly marked unverified."""
    event_info = parse_disaster_query("Mumbai floods July 2005")

    # Result contains no rainfall numbers and no casualty figures
    r_empty = SearchResult(
        title="Civic Administration Reviews Mumbai Infrastructure",
        url="https://example.gov.in/civic-review",
        content="The municipal corporation held a comprehensive review meeting regarding stormwater drainage infrastructure.",
        domain="example.gov.in",
    )

    report = perform_cross_verification([r_empty], event_info)
    unverified_claims = [c for c in report.verified_claims if c.status == "unverified"]
    assert len(unverified_claims) >= 1
    rain_or_cas = [c for c in unverified_claims if c.topic in {"Rainfall Measurement", "Casualty Figures"}]
    assert len(rain_or_cas) >= 1
    assert rain_or_cas[0].sources == []
    assert "unverified" in rain_or_cas[0].evidence_explanation.lower()


def test_dependent_wire_sources_not_treated_as_independent_corroboration():
    """Verify that multiple domains republishing the same AP wire report are recognized as shared origin."""
    event_info = parse_disaster_query("Kerala floods August 2018")

    r1 = SearchResult(
        title="Death toll climbs in Kerala - News Outlet A",
        url="https://portal-a.com/news/kerala-floods",
        content="By Associated Press: Officials reported more than 350 killed as emergency crews mobilized.",
        domain="portal-a.com",
    )
    r2 = SearchResult(
        title="Floods inundate southern India - News Outlet B",
        url="https://portal-b.com/world/india-monsoon",
        content="According to the Associated Press, more than 350 killed in the southern coastal state.",
        domain="portal-b.com",
    )

    report = perform_cross_verification([r1, r2], event_info)
    cas_claim = next(c for c in report.verified_claims if c.topic == "Casualty Figures")
    # Must NOT claim independent multi-source corroboration
    assert cas_claim.status == "single_source"
    assert "shared wire" in cas_claim.evidence_explanation.lower() or "associated press" in cas_claim.evidence_explanation.lower()
    assert not any("corroborated across" in f.lower() for f in report.corroborated_facts if "casualty" in f.lower())


def test_divergent_district_counts_treated_as_conflicting_not_corroborated():
    """
    Verify that when different sources report conflicting district numbers (10 vs 14),
    it is classified as conflicting, NOT falsely claimed as corroborated.
    """
    event_info = parse_disaster_query("Kerala floods August 2018")

    r1 = SearchResult(
        title="Kerala Post Disaster Needs Assessment",
        url="https://reliefweb.int/report/kerala-pdna",
        content="Flooding and landslides impacted villages across 14 districts of the state.",
        domain="reliefweb.int",
    )
    r2 = SearchResult(
        title="Monsoon Dam Management Review",
        url="https://india.mongabay.com/cwc-dams-kerala",
        content="Severe inundation was recorded across 10 districts in central and southern Kerala.",
        domain="india.mongabay.com",
    )

    report = perform_cross_verification([r1, r2], event_info)
    dist_claim = next(c for c in report.verified_claims if c.topic == "Geographic Inundation Scale")
    assert dist_claim.status == "conflicting"
    assert any("diverge" in c.lower() or "varies" in c.lower() for c in report.conflicting_claims)
    # Must NOT be in corroborated facts
    assert not any("10 districts" in f and "corroborated by 2 sources" in f for f in report.corroborated_facts)


def test_population_displacement_not_conflated_with_total_affected():
    """Verify displacement into relief camps is distinguished from total affected population."""
    event_info = parse_disaster_query("Kerala floods August 2018")

    r1 = SearchResult(
        title="Rescue Operations Ongoing",
        url="https://cbsnews.com/kerala-relief",
        content="Rescue operations continue as over 800,000 people displaced into relief camps.",
        domain="cbsnews.com",
    )
    r2 = SearchResult(
        title="Kerala Humanitarian Assessment",
        url="https://reliefweb.int/kerala-report",
        content="An estimated 5.4 million people affected by heavy monsoon floods across Kerala.",
        domain="reliefweb.int",
    )

    report = perform_cross_verification([r1, r2], event_info)
    topics = [c.topic for c in report.verified_claims]
    assert "Population Displacement" in topics
    assert "Total Affected Population" in topics

    disp_claim = next(c for c in report.verified_claims if c.topic == "Population Displacement")
    aff_claim = next(c for c in report.verified_claims if c.topic == "Total Affected Population")

    assert "800,000" in disp_claim.claim or "800,000" in disp_claim.sources[0]["quote"]
    assert "5.4 million" in aff_claim.claim or "5.4 million" in aff_claim.sources[0]["quote"]


def test_synthesize_incident_summary_preserves_urls_and_quotes():
    """Verify that synthesize_incident_summary preserves URLs and quotes for stated facts."""
    event_info = parse_disaster_query("Kerala floods August 2018")

    r1 = SearchResult(
        title="Kerala PDNA Report",
        url="https://reliefweb.int/report/kerala-pdna",
        content="Flooding and landslides took 433 lives across 14 districts.",
        domain="reliefweb.int",
    )
    r2 = SearchResult(
        title="CBS News Kerala Coverage",
        url="https://cbsnews.com/kerala-floods",
        content="Early dispatch confirms more than 350 killed and 800,000 displaced.",
        domain="cbsnews.com",
    )

    report = perform_cross_verification([r1, r2], event_info)
    summary = synthesize_incident_summary(event_info, [r1, r2], report)

    assert "https://reliefweb.int/report/kerala-pdna" in summary or "reliefweb.int" in summary
    assert "https://cbsnews.com/kerala-floods" in summary or "cbsnews.com" in summary
    assert "Incident Summary" in summary
    assert "Casualty Reports" in summary
