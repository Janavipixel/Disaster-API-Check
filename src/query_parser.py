"""
Disaster query parsing and temporal relation classification.
Extracts disaster type, location, and approximate event dates from natural-language queries.
Distinguishes event dates from article publication timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Optional, Tuple


# Common disaster keywords
DISASTER_PATTERNS = [
    (r"\b(flash\s+floods?|flooding|floods?|deluge|inundation)\b", "floods"),
    (r"\b(earthquakes?|tremors?|quakes?)\b", "earthquake"),
    (r"\b(cyclones?|hurricanes?|typhoons?|tropical\s+storms?)\b", "cyclone"),
    (r"\b(tsunamis?|tidal\s+waves?)\b", "tsunami"),
    (r"\b(landslides?|mudslides?|rockfalls?|debris\s+flows?)\b", "landslide"),
    (r"\b(wildfires?|forest\s+fires?|bushfires?)\b", "wildfire"),
    (r"\b(dam\s+collapse|dam\s+burst|dam\s+breach|dam\s+failure)\b", "dam collapse"),
    (r"\b(volcanic\s+eruptions?|volcanoes?|volcano)\b", "volcano"),
    (r"\b(droughts?)\b", "drought"),
    (r"\b(avalanches?)\b", "avalanche"),
]

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

MONTH_NAMES = {v: k.capitalize() for k, v in MONTH_MAP.items() if len(k) > 3}

STOPWORDS = {
    "in", "of", "the", "and", "at", "on", "during", "after", "hit", "strikes",
    "recent", "major", "severe", "deadly", "disaster", "incident", "report", "news"
}


@dataclass(frozen=True)
class DisasterQueryInfo:
    """Structured information extracted from a natural-language disaster query."""
    original_query: str
    disaster_type: Optional[str]
    location: Optional[str]
    event_year: Optional[int]
    event_month: Optional[int]
    event_month_name: Optional[str]
    event_date_str: Optional[str]
    optimized_search_query: str
    event_day: Optional[int] = None

    @property
    def has_event_date(self) -> bool:
        return self.event_year is not None


def parse_disaster_query(query: str) -> DisasterQueryInfo:
    """
    Parses a disaster search query to extract:
      - Disaster type (e.g. floods, earthquake, cyclone)
      - Location (e.g. Mumbai, Kerala, Derna)
      - Event Date (year, optional month, and optional day)
      - Constructs an optimized query for Tavily
    """
    raw_query = query.strip()
    lower_query = raw_query.lower()

    # 1. Extract Disaster Type
    disaster_type: Optional[str] = None
    disaster_match_span: Optional[Tuple[int, int]] = None
    for pattern, name in DISASTER_PATTERNS:
        match = re.search(pattern, lower_query)
        if match:
            disaster_type = name
            disaster_match_span = match.span()
            break

    # 2. Extract Year (4 digits between 1900 and 2099)
    year_match = re.search(r"\b(19\d\d|20\d\d)\b", raw_query)
    event_year: Optional[int] = int(year_match.group(1)) if year_match else None
    year_span = year_match.span() if year_match else None

    # 3. Extract Month
    event_month: Optional[int] = None
    event_month_name: Optional[str] = None
    month_span: Optional[Tuple[int, int]] = None

    for m_name, m_num in MONTH_MAP.items():
        m_match = re.search(r"\b" + m_name + r"\b", lower_query)
        if m_match:
            event_month = m_num
            event_month_name = MONTH_NAMES.get(m_num, m_name.capitalize())
            month_span = m_match.span()
            break

    # 3b. Extract Day (if month is found)
    event_day: Optional[int] = None
    day_span: Optional[Tuple[int, int]] = None
    if month_span:
        # Check day immediately after month, e.g. "February 6, 2023" or "February 6th"
        after_month = raw_query[month_span[1]:]
        d_after = re.match(r"^\s*,?\s*([0-2]?[1-9]|3[01])(?:st|nd|rd|th)?\b", after_month, re.IGNORECASE)
        if d_after:
            event_day = int(d_after.group(1))
            start_idx = month_span[1] + after_month.find(d_after.group(1))
            day_span = (start_idx, start_idx + len(d_after.group(1)))
        else:
            # Check day immediately before month, e.g. "6 February 2023" or "26th July"
            before_month = raw_query[:month_span[0]]
            d_before = re.search(r"\b([0-2]?[1-9]|3[01])(?:st|nd|rd|th)?\s*(?:of\s*)?$", before_month, re.IGNORECASE)
            if d_before:
                event_day = int(d_before.group(1))
                day_span = (d_before.start(1), d_before.end(1))

    # Formulate Event Date String
    event_date_str: Optional[str] = None
    if event_year and event_month_name and event_day:
        event_date_str = f"{event_month_name} {event_day}, {event_year}"
    elif event_year and event_month_name:
        event_date_str = f"{event_month_name} {event_year}"
    elif event_year:
        event_date_str = str(event_year)

    # 4. Extract Location
    # Remove disaster term, year, month, and day from the query string
    chars = list(raw_query)
    spans_to_remove = [s for s in [disaster_match_span, year_span, month_span, day_span] if s is not None]
    for start, end in sorted(spans_to_remove, key=lambda x: x[0], reverse=True):
        chars[start:end] = [" "] * (end - start)

    cleaned_remaining = "".join(chars)
    tokens = [
        tok.strip(" ,.-/")
        for tok in cleaned_remaining.split()
        if tok.lower().strip(" ,.-/") not in STOPWORDS and len(tok.strip(" ,.-/")) > 1
    ]

    location: Optional[str] = " ".join(tokens).title() if tokens else None

    # 5. Construct Optimized Query for Tavily
    query_parts = []
    if location:
        query_parts.append(location)
    if disaster_type:
        query_parts.append(disaster_type)
    if event_date_str:
        query_parts.append(event_date_str)
    
    if location and disaster_type:
        optimized_query = f"{' '.join(query_parts)} disaster news report"
    else:
        optimized_query = raw_query

    return DisasterQueryInfo(
        original_query=raw_query,
        disaster_type=disaster_type,
        location=location,
        event_year=event_year,
        event_month=event_month,
        event_month_name=event_month_name,
        event_date_str=event_date_str,
        optimized_search_query=optimized_query,
        event_day=event_day,
    )


def derive_incident_date_range(info: DisasterQueryInfo) -> Tuple[Optional[str], Optional[str]]:
    """
    Derives standard ISO date window (start_date, end_date) in 'YYYY-MM-DD' format
    based on the extracted event date components.
    """
    if not info.has_event_date:
        return None, None

    year = info.event_year
    assert year is not None

    if info.event_month and info.event_day:
        from datetime import date, timedelta
        try:
            start_dt = date(year, info.event_month, info.event_day)
            end_dt = start_dt + timedelta(days=2)
            return start_dt.isoformat(), end_dt.isoformat()
        except ValueError:
            pass

    if info.event_month:
        import calendar
        last_day = calendar.monthrange(year, info.event_month)[1]
        start_str = f"{year:04d}-{info.event_month:02d}-01"
        end_str = f"{year:04d}-{info.event_month:02d}-{last_day:02d}"
        return start_str, end_str

    return f"{year:04d}-01-01", f"{year:04d}-12-31"


def parse_publication_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parses various date formats returned by Tavily or news sources:
      - RFC 2822: 'Mon, 20 Aug 2018 00:00:00 GMT'
      - ISO 8601: '2018-08-20', '2018-08-20T14:30:00Z'
      - Natural strings: '20 Aug 2018', 'August 20, 2018'
    Returns datetime or None if unparseable.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = date_str.strip()
    if not cleaned:
        return None

    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except (ValueError, TypeError):
            continue

    # Try regex fallback for 4-digit year and month name
    year_match = re.search(r"\b(19\d\d|20\d\d)\b", cleaned)
    if year_match:
        year = int(year_match.group(1))
        # Look for month
        for m_name, m_num in MONTH_MAP.items():
            if re.search(r"\b" + m_name + r"\b", cleaned.lower()):
                return datetime(year, m_num, 1)
        return datetime(year, 1, 1)

    return None


def classify_temporal_relation(
    pub_date: Optional[datetime],
    event_info: DisasterQueryInfo,
) -> Tuple[str, str]:
    """
    Classifies whether an article is contemporaneous or retrospective relative to the disaster event.

    Documented Time-Window Rule:
      - If both event month and year are known:
        - Contemporaneous: Published between the event month/year and up to +12 months post-event
          (covers active disaster response, rescue, and initial inquiry reports).
        - Pre-event: Published before the disaster occurred.
        - Retrospective: Published >12 months after the event month/year.
      - If only event year is known:
        - Contemporaneous: Published within the event year or up to +12 months post-event year.
        - Retrospective: Published >12 months after the event year.
      - If publication date is missing or unparseable:
        - Unknown: Labeled as 'unknown' rather than inventing an unverified date.
    
    Returns:
        (category, explanation):
          - "contemporaneous": Published during the active event or immediate response window.
          - "retrospective": Published years or months after the event window.
          - "unknown": Publication date or event date could not be established.
    """
    if not event_info.has_event_date:
        return "unknown", "Event occurrence date not specified in search query."

    if pub_date is None:
        return "unknown", "Article publication date is not available in source metadata."

    event_year = event_info.event_year
    event_month = event_info.event_month or 1

    # Approximate month difference: (pub_year - event_year) * 12 + (pub_month - event_month)
    month_diff = (pub_date.year - event_year) * 12 + (pub_date.month - event_month)

    if event_info.event_month is not None:
        if month_diff < 0:
            return "retrospective", f"Published in {pub_date.strftime('%b %Y')}, prior to the {event_info.event_date_str} disaster occurrence (pre-event background)."
        elif 0 <= month_diff <= 12:
            return "contemporaneous", f"Published in {pub_date.strftime('%b %Y')}, within the contemporaneous reporting window of the {event_info.event_date_str} incident."
        else:
            int_years = pub_date.year - event_year
            years_str = f"{int_years} year{'s' if int_years != 1 else ''}" if int_years >= 1 else f"{month_diff} months"
            return "retrospective", f"Published in {pub_date.strftime('%b %Y')} ({years_str} after the {event_info.event_date_str} incident)."
    else:
        # Only year known
        if pub_date.year < event_year:
            return "retrospective", f"Published in {pub_date.year}, prior to the {event_year} incident."
        elif pub_date.year == event_year or (pub_date.year == event_year + 1 and pub_date.month <= 12):
            return "contemporaneous", f"Published in {pub_date.strftime('%b %Y')}, contemporaneous with the {event_year} incident."
        else:
            years_diff = pub_date.year - event_year
            return "retrospective", f"Published in {pub_date.year} ({years_diff} years after the {event_year} incident)."
