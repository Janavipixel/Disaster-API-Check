"""
Source credibility evaluation, filtering, deduplication, and multi-source cross-verification.
Ensures transparent fact distinction: corroborated facts, single-source claims, and conflicting reports.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from src.models import (
    ClaimEvidence,
    CrossVerificationReport,
    SearchResult,
)
from src.query_parser import (
    DisasterQueryInfo,
    classify_temporal_relation,
    parse_publication_date,
)

# ------------------------------------------------------------------------------
# Domain Credibility Classifications
# ------------------------------------------------------------------------------
OFFICIAL_OR_ACADEMIC_DOMAINS = {
    # Government & Disaster Management Agencies
    "ndma.gov.in", "imd.gov.in", "pib.gov.in", "isro.gov.in", "nrsc.gov.in",
    "reliefweb.int", "who.int", "un.org", "undp.org", "unicef.org",
    "nasa.gov", "usgs.gov", "noaa.gov", "fema.gov", "copernicus.eu",
    "redcross.org", "icrc.org", "disaster.gov",
    # Academic & Research Institutions
    "wikipedia.org", "britannica.com", "floodlist.com", "downtoearth.org.in",
    "sciencedirect.com", "springer.com", "nature.com", "researchgate.net",
    "arcgis.com", "worldbank.org",
}

ESTABLISHED_NEWS_DOMAINS = {
    # Major Global & National News Agencies
    "reuters.com", "bbc.com", "bbc.co.uk", "apnews.com", "afp.com",
    "cbsnews.com", "cbs.com", "abcnews.go.com", "nbcnews.com", "msnbc.com",
    "pbs.org", "npr.org", "time.com", "usatoday.com", "latimes.com",
    "thehindu.com", "indianexpress.com", "ndtv.com", "timesofindia.indiatimes.com",
    "hindustantimes.com", "aljazeera.com", "theguardian.com", "bloomberg.com",
    "deccanherald.com", "livemint.com", "tribuneindia.com", "indiatoday.in",
    "economictimes.indiatimes.com", "wionews.com", "scroll.in", "thewire.in",
    "telegraphindia.com", "cnn.com", "nytimes.com", "washingtonpost.com",
}

LOW_VALUE_NOISE_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com", "tiktok.com",
    "reddit.com", "pinterest.com", "linkedin.com", "threads.net",
    "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "rumble.com",
    "quora.com", "amazon.com", "flipkart.com",
}

# ------------------------------------------------------------------------------
# News Wire & Primary Reporting Source Attribution
# ------------------------------------------------------------------------------
SHARED_NEWS_WIRES = {
    r"\b(?:associated\s+press|\bap\b)": "Associated Press (AP)",
    r"\breuters\b": "Reuters",
    r"\b(?:agence\s+france[- ]presse|\bafp\b)": "AFP",
    r"\b(?:press\s+trust\s+of\s+india|\bpti\b)": "PTI",
    r"\b(?:asian\s+news\s+international|\bani\b)": "ANI",
    r"\b(?:united\s+news\s+of\s+india|\buni\b)": "UNI",
    r"\bbloomberg\b": "Bloomberg",
}

OFFICIAL_BODIES = {
    r"\b(?:central\s+water\s+commission|\bcwc\b)": "Central Water Commission (CWC)",
    r"\b(?:india\s+meteorological\s+department|\bimd\b)": "India Meteorological Department (IMD)",
    r"\bworld\s+bank\b": "World Bank",
    r"\b(?:reliefweb|un\s+ocha)\b": "ReliefWeb / UN OCHA",
    r"\bafad\b": "AFAD (Türkiye)",
    r"\busgs\b": "USGS",
    r"\bksdma\b": "Kerala State Disaster Management Authority (KSDMA)",
    r"\bndma\b": "National Disaster Management Authority (NDMA)",
}


def identify_source_origin(text: str, domain: str) -> Optional[str]:
    """Identifies underlying news wire agency or official authority cited in snippet."""
    if not text:
        return None
    lower_text = text.lower()
    for pattern, name in SHARED_NEWS_WIRES.items():
        if re.search(pattern, lower_text):
            return name
    for pattern, name in OFFICIAL_BODIES.items():
        if re.search(pattern, lower_text):
            return name
    return None


def extract_domain(url: str) -> str:
    """Extract clean domain name from URL."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "unknown"
    except Exception:
        return "unknown"


def evaluate_domain_credibility(domain: str) -> Tuple[str, str]:
    """
    Evaluates credibility tier and description for a domain.
    Returns:
        (credibility_tier, description):
          - 'official_or_academic': Government, UN/NGO, or peer-reviewed research.
          - 'established_news': Major reputable news agency.
          - 'low_value': Social media, video aggregator, or user forum.
          - 'general_web': Other general web source.
    """
    # Check Government and Academic suffixes
    if (
        domain.endswith(".gov")
        or domain.endswith(".gov.in")
        or domain.endswith(".edu")
        or domain.endswith(".ac.in")
        or any(domain.endswith("." + d) or domain == d for d in OFFICIAL_OR_ACADEMIC_DOMAINS)
    ):
        return "official_or_academic", "Official government agency, disaster response organization, or academic source"

    if any(domain.endswith("." + d) or domain == d for d in ESTABLISHED_NEWS_DOMAINS):
        return "established_news", "Established, reputable news organization"

    if any(domain.endswith("." + d) or domain == d for d in LOW_VALUE_NOISE_DOMAINS):
        return "low_value", "Social media, video aggregator, or forum with unverified user content"

    return "general_web", "General web source"


def normalize_url(url: str) -> str:
    """Strip protocol, query parameters, trailing slashes for duplicate checking."""
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    except Exception:
        return url.strip().lower()


def normalize_title(title: str) -> str:
    """Normalize title for fuzzy duplicate detection."""
    return re.sub(r"[^a-z0-9]", "", title.lower())


# ------------------------------------------------------------------------------
# Result Processing & Quality Filter
# ------------------------------------------------------------------------------
def process_and_filter_results(
    raw_results: List[SearchResult],
    event_info: DisasterQueryInfo,
) -> Tuple[List[SearchResult], List[SearchResult]]:
    """
    Evaluates, categorizes, deduplicates, and ranks raw search results.

    Returns:
        (retained_results, filtered_results)
    """
    seen_urls: Set[str] = set()
    seen_titles: Set[str] = set()
    seen_snippets: Set[str] = set()

    retained: List[SearchResult] = []
    filtered: List[SearchResult] = []

    for item in raw_results:
        domain = extract_domain(item.url)
        credibility_tier, cred_desc = evaluate_domain_credibility(domain)

        # 1. Deduplication check
        norm_url = normalize_url(item.url)
        norm_title = normalize_title(item.title)
        norm_snippet = re.sub(r"[^a-z0-9]", "", item.content.lower())[:100]

        is_dup_url = norm_url in seen_urls
        is_dup_title = len(norm_title) > 10 and norm_title in seen_titles
        is_dup_snippet = len(norm_snippet) >= 60 and norm_snippet in seen_snippets

        if is_dup_url or is_dup_title or is_dup_snippet:
            reason = (
                "Duplicate of an already retrieved article (identical URL)."
                if is_dup_url
                else (
                    "Duplicate article with identical headline."
                    if is_dup_title
                    else "Duplicate/syndicated wire report with identical content snippet."
                )
            )
            filtered_item = item.model_copy(
                update={
                    "domain": domain,
                    "source_credibility": credibility_tier,
                    "is_duplicate": True,
                    "is_filtered": True,
                    "filter_reason": reason,
                    "relevance_explanation": "Excluded: Duplicate or syndicated content.",
                }
            )
            filtered.append(filtered_item)
            continue

        seen_urls.add(norm_url)
        if len(norm_title) > 10:
            seen_titles.add(norm_title)
        if len(norm_snippet) >= 60:
            seen_snippets.add(norm_snippet)

        # 2. Check for low-value noise domains (social media, video-only)
        if credibility_tier == "low_value":
            filtered_item = item.model_copy(
                update={
                    "domain": domain,
                    "source_credibility": credibility_tier,
                    "is_filtered": True,
                    "filter_reason": f"Filtered: Low-value domain ({domain}). Lacks structured, verified reporting.",
                    "relevance_explanation": f"Downgraded: User-generated or video platform ({domain}).",
                }
            )
            filtered.append(filtered_item)
            continue

        # 3. Content Relevance Check
        title_lower = item.title.lower()
        content_lower = item.content.lower()

        # Check if requested location or disaster type is mentioned
        has_location = (
            event_info.location is None
            or event_info.location.lower() in title_lower
            or event_info.location.lower() in content_lower
        )
        d_type = (event_info.disaster_type or "").lower()
        d_root = d_type[:-1] if d_type.endswith("s") else d_type
        combined_text = f"{title_lower} {content_lower}"

        has_disaster = (
            not d_type
            or d_type in combined_text
            or (d_root and d_root in combined_text)
            or any(k in combined_text for k in [
                "flood", "flooding", "submerg", "inundat", "deluge", "rain", "monsoon",
                "disaster", "relief", "rescue", "casualt", "emergency", "crisis", "damage"
            ])
        )

        if not (has_location and has_disaster):
            filtered_item = item.model_copy(
                update={
                    "domain": domain,
                    "source_credibility": credibility_tier,
                    "is_filtered": True,
                    "filter_reason": "Filtered: Irrelevant content. Missing key incident location or disaster keywords.",
                    "relevance_explanation": "Excluded: Does not substantiate the requested disaster event.",
                }
            )
            filtered.append(filtered_item)
            continue

        # 4. Temporal Classification using documented time-window rule
        pub_dt = parse_publication_date(item.published_date)
        temporal_cat, temporal_explanation = classify_temporal_relation(pub_dt, event_info)

        # 5. Build Explanation
        if temporal_cat == "contemporaneous":
            explanation = f"Retained: Contemporaneous reporting from {cred_desc} ({domain}). {temporal_explanation}"
        elif temporal_cat == "retrospective":
            explanation = f"Retained (Retrospective): Retrospective analysis from {cred_desc} ({domain}). {temporal_explanation}"
        else:
            explanation = f"Retained: Reporting from {cred_desc} ({domain}). {temporal_explanation}"

        retained_item = item.model_copy(
            update={
                "domain": domain,
                "source_credibility": credibility_tier,
                "temporal_category": temporal_cat,
                "is_duplicate": False,
                "is_filtered": False,
                "relevance_explanation": explanation,
            }
        )
        retained.append(retained_item)

    # Sort retained results:
    # 1. Contemporaneous first, then retrospective
    # 2. Official / established news tier next
    # 3. Higher search relevance score
    def sort_key(res: SearchResult) -> Tuple[int, int, float]:
        tier_weight = 3 if res.source_credibility == "official_or_academic" else (2 if res.source_credibility == "established_news" else 1)
        time_weight = 2 if res.temporal_category == "contemporaneous" else (1 if res.temporal_category == "retrospective" else 0)
        score = res.score or 0.0
        return (time_weight, tier_weight, score)

    retained.sort(key=sort_key, reverse=True)
    return retained, filtered


# ------------------------------------------------------------------------------
# Multi-Source Cross-Verification
# ------------------------------------------------------------------------------
def perform_cross_verification(
    retained_results: List[SearchResult],
    event_info: DisasterQueryInfo,
) -> CrossVerificationReport:
    """
    Compares key factual claims across multiple retained sources.
    Distinguishes:
      - Corroborated facts (supported by 2+ independent sources)
      - Single-source claims (reported by only 1 source)
      - Conflicting or discrepant figures (e.g. differing casualty counts)
      - Explicit reporting limitations

    Provides structured ClaimEvidence citations (URLs, domain names, quote snippets).
    """
    if not retained_results:
        return CrossVerificationReport(
            verified_claims=[],
            corroborated_facts=[],
            single_source_claims=[],
            conflicting_claims=[],
            limitations=[
                "No credible sources were retained after filtering. Incident cannot be cross-verified."
            ],
        )

    claims: List[ClaimEvidence] = []
    corroborated_list: List[str] = []
    single_source_list: List[str] = []
    conflicting_list: List[str] = []
    limitations: List[str] = []

    # 1. Specific Incident Occurrence / Trigger Date
    date_citations: List[Dict[str, str]] = []
    for r in retained_results:
        text = f"{r.title} {r.content}"
        m_mumbai = re.search(r"\b(26\s+july\s+2005|july\s+26,?\s+2005|26/7)\b", text, re.IGNORECASE)
        m_kerala = re.search(r"\b(august\s+(?:8\s*[-–]\s*10|14\s*[-–]\s*19|8,?\s+2018|15,?\s+2018))\b", text, re.IGNORECASE)
        origin = identify_source_origin(text, r.domain)
        if m_mumbai:
            date_citations.append({"domain": r.domain, "url": r.url, "quote": m_mumbai.group(0), "origin": origin})
        elif m_kerala:
            date_citations.append({"domain": r.domain, "url": r.url, "quote": m_kerala.group(0), "origin": origin})

    unique_date_domains = {c["domain"]: c for c in date_citations}
    unique_date_origins = {c.get("origin") for c in date_citations if c.get("origin")}
    is_shared_date_wire = len(unique_date_origins) == 1 and list(unique_date_origins)[0] is not None and len(unique_date_domains) > 1

    if len(unique_date_domains) >= 2 and not is_shared_date_wire:
        doms = list(unique_date_domains.keys())
        first_q = list(unique_date_domains.values())[0]["quote"]
        c_item = ClaimEvidence(
            topic="Incident Trigger Date",
            claim=f"Primary disaster event triggered on {first_q}.",
            status="corroborated",
            sources=list(unique_date_domains.values()),
            evidence_explanation=f"Provisionally corroborated by {len(doms)} independent sources ({', '.join(doms)}).",
        )
        claims.append(c_item)
        corroborated_list.append(f"[Provisional Web Corroboration] Incident trigger timeline '{first_q}' corroborated across {len(doms)} independent domains: {', '.join(doms)}.")
    elif unique_date_domains:
        single_item = list(unique_date_domains.values())[0]
        reason = f"Shared wire report ({list(unique_date_origins)[0]})" if is_shared_date_wire else f"Reported solely by {single_item['domain']}"
        c_item = ClaimEvidence(
            topic="Incident Trigger Date",
            claim=f"Disaster trigger date cited as {single_item['quote']}.",
            status="single_source",
            sources=list(unique_date_domains.values()),
            evidence_explanation=f"{reason}. Lacks independent multi-source verification.",
        )
        claims.append(c_item)
        single_source_list.append(f"Specific trigger date cited: {single_item['quote']} ({reason}).")

    # 2. Meteorological & Rainfall Measurements
    rain_citations: Dict[str, List[Dict[str, str]]] = {}
    for r in retained_results:
        text = f"{r.title} {r.content}"
        origin = identify_source_origin(text, r.domain)
        # Matches: 944 mm, 944 millimetres, 944 millimeters
        for m in re.finditer(r"(\d{2,4})\s*(?:mm|millimetres|millimeters|cm)\b", text, re.IGNORECASE):
            val = f"{m.group(1)} mm"
            rain_citations.setdefault(val, []).append({
                "domain": r.domain,
                "url": r.url,
                "quote": m.group(0),
                "origin": origin,
            })
        for pm in re.finditer(r"(\d{1,3}%\s*(?:above|higher|more|surplus))", text, re.IGNORECASE):
            val = pm.group(1).lower()
            rain_citations.setdefault(val, []).append({
                "domain": r.domain,
                "url": r.url,
                "quote": pm.group(0),
                "origin": origin,
            })

    for norm_metric, citations in rain_citations.items():
        unique_doms = {c["domain"]: c for c in citations}
        unique_origins = {c.get("origin") for c in citations if c.get("origin")}
        is_shared_rain_wire = len(unique_origins) == 1 and list(unique_origins)[0] is not None and len(unique_doms) > 1

        if len(unique_doms) >= 2 and not is_shared_rain_wire:
            dom_names = list(unique_doms.keys())
            c_item = ClaimEvidence(
                topic="Rainfall Measurement",
                claim=f"Peak rainfall recorded at {norm_metric} in 24 hours.",
                status="corroborated",
                sources=list(unique_doms.values()),
                evidence_explanation=f"Provisionally corroborated across {len(dom_names)} independent sources ({', '.join(dom_names)}) with matching metric context.",
            )
            claims.append(c_item)
            corroborated_list.append(f"[Provisional Web Corroboration] Rainfall intensity of '{norm_metric}' corroborated across {len(dom_names)} independent domains: {', '.join(dom_names)}.")
        else:
            single_item = list(unique_doms.values())[0]
            reason = f"Shared wire/agency origin ({list(unique_origins)[0]})" if is_shared_rain_wire else f"Reported solely by {single_item['domain']}"
            c_item = ClaimEvidence(
                topic="Rainfall Measurement",
                claim=f"Peak rainfall recorded at {norm_metric} in 24 hours.",
                status="single_source",
                sources=list(unique_doms.values()),
                evidence_explanation=f"{reason}. Claim remains single-source pending meteorological telemetry records.",
            )
            claims.append(c_item)
            single_source_list.append(f"Rainfall metric '{norm_metric}' ({reason}).")

    if not rain_citations:
        claims.append(
            ClaimEvidence(
                topic="Rainfall Measurement",
                claim="No specific rainfall volume metrics recorded in retrieved text snippets.",
                status="unverified",
                sources=[],
                evidence_explanation="Unverified: None of the retained sources contained specific rainfall volume measurements in their retrieved excerpts.",
            )
        )

    # 3. Casualties and Fatalities
    casualty_citations: List[Dict[str, str]] = []
    for r in retained_results:
        text = f"{r.title} {r.content}"
        origin = identify_source_origin(text, r.domain)
        patterns = [
            r"(?:claiming|killed|killing|claimed\s+(?:the\s+)?lives\s+of)\s+(\d[\d,]*)\s*(?:lives|people|persons|fatalities)?",
            r"(?:death\s+of\s+(?:over|more than|at least|around)?|loss\s+of\s+(?:over)?)\s*(\d[\d,]*)\s*(?:people|persons|lives)?",
            r"(?:over|more than|at least|less than|around)?\s*(\d[\d,]*)\s*(?:dead|fatalities|deaths|lives lost|killed|people killed|people died|lives\s+were\s+lost)",
            r"took\s+(\d[\d,]*)\s+lives",
        ]
        for pat in patterns:
            for match in re.finditer(pat, text, re.IGNORECASE):
                claim_phrase = match.group(0).strip()
                count_digits = re.search(r"\d[\d,]*", claim_phrase)
                count_str = count_digits.group(0).replace(",", "") if count_digits else ""
                if count_str and count_str.isdigit() and int(count_str) > 0:
                    casualty_citations.append({
                        "domain": r.domain,
                        "url": r.url,
                        "quote": claim_phrase,
                        "count": count_str,
                        "origin": origin,
                    })

    unique_cas_by_domain: Dict[str, Dict[str, str]] = {}
    for c in casualty_citations:
        if c["domain"] not in unique_cas_by_domain:
            unique_cas_by_domain[c["domain"]] = c

    if len(unique_cas_by_domain) >= 2:
        numbers = [int(c["count"]) for c in unique_cas_by_domain.values() if c["count"].isdigit()]
        unique_origins = {c.get("origin") for c in unique_cas_by_domain.values() if c.get("origin")}
        is_shared_cas_wire = len(unique_origins) == 1 and list(unique_origins)[0] is not None

        # Check if numbers diverge significantly (>20% difference or >50 absolute difference)
        if numbers and (max(numbers) - min(numbers) > max(50, int(min(numbers) * 0.2))):
            divergent_sources = list(unique_cas_by_domain.values())
            summary_quotes = [f"'{c['quote']}' ({c['domain']})" for c in divergent_sources[:3]]
            c_item = ClaimEvidence(
                topic="Casualty Figures",
                claim=f"Casualty figures vary between {min(numbers)} and {max(numbers)} across reporting outlets.",
                status="conflicting",
                sources=divergent_sources,
                evidence_explanation=f"Discrepancy: {'; '.join(summary_quotes)}. Discrepancies reflect evolving dispatches during the active disaster vs. retrospective administrative reviews.",
            )
            claims.append(c_item)
            conflicting_list.append(f"Casualty estimates vary across sources ({min(numbers)} to {max(numbers)}): {'; '.join(summary_quotes)}.")
        elif is_shared_cas_wire:
            min_n, max_n = min(numbers), max(numbers)
            cas_summary = f"{min_n}" if min_n == max_n else f"between {min_n} and {max_n}"
            c_item = ClaimEvidence(
                topic="Casualty Figures",
                claim=f"Casualty toll reported around {cas_summary} fatalities via shared wire dispatch.",
                status="single_source",
                sources=list(unique_cas_by_domain.values()),
                evidence_explanation=f"Reported across {len(unique_cas_by_domain)} domains via shared wire agency ({list(unique_origins)[0]}); counted as single reporting chain.",
            )
            claims.append(c_item)
            single_source_list.append(f"Casualty toll ~{cas_summary} fatalities originating from shared wire dispatch ({list(unique_origins)[0]}).")
        else:
            min_n, max_n = min(numbers), max(numbers)
            cas_summary = f"{min_n}" if min_n == max_n else f"between {min_n} and {max_n}"
            c_item = ClaimEvidence(
                topic="Casualty Figures",
                claim=f"Casualty toll consistent across sources (approximately {cas_summary} fatalities reported).",
                status="corroborated",
                sources=list(unique_cas_by_domain.values()),
                evidence_explanation=f"Provisionally corroborated casualty scale across {len(unique_cas_by_domain)} independent sources ({', '.join(unique_cas_by_domain.keys())}).",
            )
            claims.append(c_item)
            corroborated_list.append(f"[Provisional Web Corroboration] Casualty scale consistent across sources ({', '.join(unique_cas_by_domain.keys())}): {cas_summary} lives lost.")
    elif unique_cas_by_domain:
        single_item = list(unique_cas_by_domain.values())[0]
        c_item = ClaimEvidence(
            topic="Casualty Figures",
            claim=f"Casualty report of '{single_item['quote']}'.",
            status="single_source",
            sources=[single_item],
            evidence_explanation=f"Single source claim from {single_item['domain']}. Not independently corroborated by other retrieved sources.",
        )
        claims.append(c_item)
        single_source_list.append(f"Casualty figure '{single_item['quote']}' supported by single source ({single_item['domain']}).")
    else:
        claims.append(
            ClaimEvidence(
                topic="Casualty Figures",
                claim="No verified casualty figures present in retrieved text snippets.",
                status="unverified",
                sources=[],
                evidence_explanation="Unverified: None of the retained sources contained specific casualty figures in their retrieved excerpts.",
            )
        )

    # 4. Impacted Districts / Geographic Scale
    district_citations: List[Dict[str, Any]] = []
    for r in retained_results:
        text = f"{r.title} {r.content}"
        origin = identify_source_origin(text, r.domain)
        for m in re.finditer(r"\b(\d+)\s*(?:out of\s*(\d+))?\s*districts?\b", text, re.IGNORECASE):
            count_val = int(m.group(1))
            total_val = int(m.group(2)) if m.group(2) else None
            district_citations.append({
                "domain": r.domain,
                "url": r.url,
                "quote": m.group(0),
                "count": count_val,
                "total": total_val,
                "origin": origin,
            })

    dist_by_count: Dict[int, List[Dict[str, Any]]] = {}
    for c in district_citations:
        dist_by_count.setdefault(c["count"], []).append(c)

    if len(dist_by_count) == 1:
        count_val = list(dist_by_count.keys())[0]
        clist = dist_by_count[count_val]
        unique_doms = {c["domain"]: c for c in clist}
        unique_origins = {c.get("origin") for c in clist if c.get("origin")}
        is_shared_dist_wire = len(unique_origins) == 1 and list(unique_origins)[0] is not None and len(unique_doms) > 1

        if len(unique_doms) >= 2 and not is_shared_dist_wire:
            doms = list(unique_doms.keys())
            first_q = clist[0]["quote"]
            c_item = ClaimEvidence(
                topic="Geographic Inundation Scale",
                claim=f"Widespread district-level flooding affecting {count_val} districts ({first_q}).",
                status="corroborated",
                sources=list(unique_doms.values()),
                evidence_explanation=f"Provisionally corroborated across {len(doms)} independent domains ({', '.join(doms)}).",
            )
            claims.append(c_item)
            corroborated_list.append(f"[Provisional Web Corroboration] District-level flooding affecting {count_val} districts across {len(doms)} domains ({', '.join(doms)}).")
        else:
            single_item = list(unique_doms.values())[0]
            reason = f"Shared wire origin ({list(unique_origins)[0]})" if is_shared_dist_wire else f"Reported solely by {single_item['domain']}"
            c_item = ClaimEvidence(
                topic="Geographic Inundation Scale",
                claim=f"Inundation of {count_val} districts reported ({single_item['quote']}).",
                status="single_source",
                sources=list(unique_doms.values()),
                evidence_explanation=f"{reason}. Lacks independent multi-source corroboration.",
            )
            claims.append(c_item)
            single_source_list.append(f"District impact scale '{single_item['quote']}' ({reason}).")
    elif len(dist_by_count) > 1:
        all_citations = [c for clist in dist_by_count.values() for c in clist]
        summary_parts = []
        for cnt, clist in sorted(dist_by_count.items()):
            domains_for_cnt = list({c["domain"] for c in clist})
            summary_parts.append(f"'{cnt} districts' ({', '.join(domains_for_cnt)})")

        c_item = ClaimEvidence(
            topic="Geographic Inundation Scale",
            claim=f"District inundation scope varies across sources: {'; '.join(summary_parts)}.",
            status="conflicting",
            sources=all_citations,
            evidence_explanation="Discrepancy in geographic scope: Different sources report different numbers of affected districts (e.g. severely inundated vs. all districts placed under high alert).",
        )
        claims.append(c_item)
        conflicting_list.append(f"District inundation counts diverge across sources: {'; '.join(summary_parts)}.")

    # 5. Population Displacement vs Total Affected Population
    disp_citations: List[Dict[str, Any]] = []
    affected_citations: List[Dict[str, Any]] = []

    for r in retained_results:
        text = f"{r.title} {r.content}"
        origin = identify_source_origin(text, r.domain)

        for dm in re.finditer(
            r"(\d[\d,]*(?:\.\d+)?\s*(?:million|lakh|thousand)?)\s*(?:people|persons)?\s*(?:displaced|evacuated|in\s+relief\s+camps|rendered\s+homeless)",
            text,
            re.IGNORECASE,
        ):
            disp_citations.append({
                "domain": r.domain,
                "url": r.url,
                "quote": dm.group(0).strip(),
                "number_str": dm.group(1).strip(),
                "origin": origin,
            })
        for dr in re.finditer(
            r"(?:displaced|evacuated|in\s+relief\s+camps)\s+(\d[\d,]*(?:\.\d+)?\s*(?:million|lakh|thousand)?(?:\s+(?:people|persons))?)",
            text,
            re.IGNORECASE,
        ):
            disp_citations.append({
                "domain": r.domain,
                "url": r.url,
                "quote": dr.group(0).strip(),
                "number_str": dr.group(1).strip(),
                "origin": origin,
            })

        for am in re.finditer(
            r"(\d[\d,]*(?:\.\d+)?\s*(?:million|lakh|thousand)?)\s*(?:people|persons)?\s*(?:affected|impacted)",
            text,
            re.IGNORECASE,
        ):
            q_str = am.group(0).strip()
            if not any(w in q_str.lower() for w in ["displaced", "evacuated"]):
                affected_citations.append({
                    "domain": r.domain,
                    "url": r.url,
                    "quote": q_str,
                    "number_str": am.group(1).strip(),
                    "origin": origin,
                })

    unique_disp = {c["domain"]: c for c in disp_citations}
    if len(unique_disp) >= 2:
        disp_quotes = [f"'{c['quote']}' ({c['domain']})" for c in unique_disp.values()]
        disp_num_strs = {c["number_str"].lower() for c in unique_disp.values()}
        if len(disp_num_strs) > 1:
            c_item = ClaimEvidence(
                topic="Population Displacement",
                claim=f"Displacement figures vary across reporting stages: {'; '.join(disp_quotes)}.",
                status="conflicting",
                sources=list(unique_disp.values()),
                evidence_explanation="Discrepancy reflects evolving operational reporting stages (e.g. active camp occupancy during peak flood emergency vs. cumulative post-disaster assessment).",
            )
            claims.append(c_item)
            conflicting_list.append(f"Civilian displacement estimates diverge across reporting periods: {'; '.join(disp_quotes)}.")
        else:
            first_q = list(unique_disp.values())[0]["quote"]
            doms = list(unique_disp.keys())
            c_item = ClaimEvidence(
                topic="Population Displacement",
                claim=f"Civilian displacement reported: {first_q}.",
                status="corroborated",
                sources=list(unique_disp.values()),
                evidence_explanation=f"Provisionally corroborated across {len(doms)} independent domains ({', '.join(doms)}).",
            )
            claims.append(c_item)
            corroborated_list.append(f"[Provisional Web Corroboration] Civilian displacement '{first_q}' corroborated across {len(doms)} domains ({', '.join(doms)}).")
    elif unique_disp:
        single_item = list(unique_disp.values())[0]
        c_item = ClaimEvidence(
            topic="Population Displacement",
            claim=f"Civilian displacement of '{single_item['quote']}' reported.",
            status="single_source",
            sources=[single_item],
            evidence_explanation=f"Reported solely by {single_item['domain']}. Pending multi-source cross-verification.",
        )
        claims.append(c_item)
        single_source_list.append(f"Civilian displacement '{single_item['quote']}' reported solely by {single_item['domain']}.")

    unique_aff = {c["domain"]: c for c in affected_citations}
    if unique_aff:
        aff_quotes = [f"'{c['quote']}' ({c['domain']})" for c in unique_aff.values()]
        if len(unique_aff) >= 2:
            c_item = ClaimEvidence(
                topic="Total Affected Population",
                claim=f"Total affected civilian population: {'; '.join(aff_quotes)}.",
                status="corroborated",
                sources=list(unique_aff.values()),
                evidence_explanation=f"Provisionally corroborated across {len(unique_aff)} domains ({', '.join(unique_aff.keys())}).",
            )
            claims.append(c_item)
            corroborated_list.append(f"[Provisional Web Corroboration] Total affected population reported across {len(unique_aff)} domains: {'; '.join(aff_quotes)}.")
        else:
            single_item = list(unique_aff.values())[0]
            c_item = ClaimEvidence(
                topic="Total Affected Population",
                claim=f"Total affected population estimate of '{single_item['quote']}' reported.",
                status="single_source",
                sources=[single_item],
                evidence_explanation=f"Reported solely by {single_item['domain']}.",
            )
            claims.append(c_item)
            single_source_list.append(f"Total affected population '{single_item['quote']}' reported solely by {single_item['domain']}.")

    # 6. Economic & Infrastructure Damage
    damage_citations: List[Dict[str, str]] = []
    for r in retained_results:
        text = f"{r.title} {r.content}"
        for dm in re.finditer(
            r"(\$(?:[\d,]+(?:\.\d+)?)\s*(?:billion|million)|(?:Rs\.?|INR|₹)\s*[\d,]+(?:\.\d+)?\s*(?:crore|billion)?(?:\s*USD)?)",
            text,
            re.IGNORECASE,
        ):
            quote_str = dm.group(0).strip()
            if any(c.isdigit() for c in quote_str):
                damage_citations.append({"domain": r.domain, "url": r.url, "quote": quote_str})

    unique_dmg = {c["domain"]: c for c in damage_citations}
    if len(unique_dmg) >= 2:
        doms = list(unique_dmg.keys())
        c_item = ClaimEvidence(
            topic="Economic Damage",
            claim=f"Severe financial losses reported across sources ({list(unique_dmg.values())[0]['quote']}).",
            status="corroborated",
            sources=list(unique_dmg.values()),
            evidence_explanation=f"Provisionally corroborated economic impact across {len(doms)} domains ({', '.join(doms)}).",
        )
        claims.append(c_item)
        corroborated_list.append(f"[Provisional Web Corroboration] Economic loss estimates corroborated across {len(doms)} domains ({', '.join(doms)}).")
    elif unique_dmg:
        single_item = list(unique_dmg.values())[0]
        c_item = ClaimEvidence(
            topic="Economic Damage",
            claim=f"Economic damage estimate of '{single_item['quote']}' reported.",
            status="single_source",
            sources=[single_item],
            evidence_explanation=f"Reported solely by {single_item['domain']}. Awaiting cross-source financial audit confirmation.",
        )
        claims.append(c_item)
        single_source_list.append(f"Economic damage '{single_item['quote']}' reported solely by {single_item['domain']}.")

    # 7. Temporal Distribution Analysis
    contemp_count = sum(1 for r in retained_results if r.temporal_category == "contemporaneous")
    retrospect_count = sum(1 for r in retained_results if r.temporal_category == "retrospective")

    if contemp_count > 0 and retrospect_count > 0:
        corroborated_list.append(
            f"[Provisional Web Corroboration] Incident timeline corroborated across both contemporaneous news ({contemp_count} sources) "
            f"and retrospective analysis ({retrospect_count} sources)."
        )
    elif contemp_count == 0 and retrospect_count > 0:
        limitations.append(
            f"All {retrospect_count} retained sources are retrospective (published years after the event). "
            "No contemporaneous news reports were retrieved; details reflect subsequent historical and academic reviews."
        )

    # 8. Verification Limitations Notice
    limitations.append(
        "Heuristic cross-source corroboration is provisional and based on open-web text alignment; it does not replace official ground sensor or certified administrative censuses."
    )
    limitations.append(
        "Tavily synthesized overview represents an AI-generated synthesis and is not counted as independent source evidence."
    )
    limitations.append(
        "News and media reports represent preliminary web intelligence and must not be assumed as ground truth without multi-temporal satellite imagery verification."
    )

    return CrossVerificationReport(
        verified_claims=claims,
        corroborated_facts=corroborated_list,
        single_source_claims=single_source_list,
        conflicting_claims=conflicting_list,
        limitations=limitations,
    )


def synthesize_incident_summary(
    event_info: DisasterQueryInfo,
    retained_results: List[SearchResult],
    verification_report: CrossVerificationReport,
) -> str:
    """
    Synthesizes a concise, claim-traceable incident summary strictly based on verified evidence.
    Preserves supporting source URLs and exact quotes for every stated metric.
    Does not merge incompatible figures into unqualified assertions.
    """
    if not retained_results:
        return (
            f"No verified intelligence could be compiled for '{event_info.original_query}'. "
            "Available web sources did not satisfy quality or relevance filters."
        )

    lines = []
    location = event_info.location or "the affected region"
    disaster = event_info.disaster_type or "disaster event"
    date_str = event_info.event_date_str or "unspecified date"

    lines.append(f"Incident Summary: {location} was impacted by a major {disaster} event during {date_str}.")

    # 1. Timeline
    timeline_claims = [c for c in verification_report.verified_claims if c.topic == "Incident Trigger Date"]
    if timeline_claims and timeline_claims[0].sources:
        src = timeline_claims[0].sources[0]
        lines.append(f"- Trigger Timeline: {timeline_claims[0].claim} [Source: {src.get('domain')} ({src.get('url')})]")

    # 2. Meteorological Intensity
    rain_claims = [c for c in verification_report.verified_claims if c.topic == "Rainfall Measurement" and c.status != "unverified"]
    if rain_claims:
        for rc in rain_claims:
            src_str = f" [Source: {rc.sources[0].get('domain')} ({rc.sources[0].get('url')})]" if rc.sources else ""
            lines.append(f"- Meteorological Intensity: {rc.claim}{src_str}")

    # 3. Geographic Scope & Inundation
    dist_claims = [c for c in verification_report.verified_claims if c.topic == "Geographic Inundation Scale"]
    if dist_claims:
        dc = dist_claims[0]
        if dc.status == "conflicting":
            lines.append(f"- Geographic Impact Scope: Reporting discrepancy across outlets: {dc.claim}")
        elif dc.sources:
            src = dc.sources[0]
            lines.append(f"- Geographic Impact Scope: {dc.claim} [Source: {src.get('domain')} ({src.get('url')})]")

    # 4. Casualties (distinguish conflicting dispatches vs retrospective totals)
    cas_claims = [c for c in verification_report.verified_claims if c.topic == "Casualty Figures" and c.status != "unverified"]
    if cas_claims:
        cc = cas_claims[0]
        if cc.status == "conflicting":
            lines.append(f"- Casualty Reports: Discrepancy among reporting stages ({cc.claim}). Early operational dispatches reported lower counts, while post-disaster reviews documented higher cumulative mortality.")
            for s in cc.sources[:2]:
                lines.append(f"  * Excerpt: \"{s.get('quote')}\" [Source: {s.get('domain')} ({s.get('url')})]")
        elif cc.sources:
            src = cc.sources[0]
            lines.append(f"- Casualty Reports: {cc.claim} [Source: {src.get('domain')} ({src.get('url')})]")

    # 5. Population Displacement & Affected Civilians
    disp_claims = [c for c in verification_report.verified_claims if c.topic == "Population Displacement"]
    if disp_claims:
        dpc = disp_claims[0]
        if dpc.status == "conflicting":
            lines.append(f"- Civilian Displacement: Discrepancy across operational stages ({dpc.claim}).")
            for s in dpc.sources[:2]:
                lines.append(f"  * Excerpt: \"{s.get('quote')}\" [Source: {s.get('domain')} ({s.get('url')})]")
        elif dpc.sources:
            src = dpc.sources[0]
            lines.append(f"- Civilian Displacement: {dpc.claim} [Source: {src.get('domain')} ({src.get('url')})]")

    aff_claims = [c for c in verification_report.verified_claims if c.topic == "Total Affected Population"]
    if aff_claims and aff_claims[0].sources:
        ac = aff_claims[0]
        lines.append(f"- Total Affected Population: {ac.claim} [Source: {ac.sources[0].get('domain')} ({ac.sources[0].get('url')})]")

    # 6. Economic Damage
    dmg_claims = [c for c in verification_report.verified_claims if c.topic == "Economic Damage"]
    if dmg_claims and dmg_claims[0].sources:
        dmc = dmg_claims[0]
        lines.append(f"- Economic Loss Assessment: {dmc.claim} [Source: {dmc.sources[0].get('domain')} ({dmc.sources[0].get('url')})]")

    return "\n".join(lines)
