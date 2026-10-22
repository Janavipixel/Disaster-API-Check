"""
Text cleaning utilities for scraped web content.
"""

from __future__ import annotations

import re
import unicodedata


# ─── Boilerplate patterns to strip ───────────────────────────────────────────
_BOILERPLATE_PATTERNS = [
    r"(cookie|privacy) policy.*",
    r"accept all cookies.*",
    r"subscribe to our newsletter.*",
    r"follow us on (twitter|facebook|instagram|linkedin).*",
    r"all rights reserved.*",
    r"terms of (service|use).*",
    r"©\s*\d{4}.*",
    r"share this article.*",
    r"click here to.*",
    r"read more.*",
    r"back to top.*",
    r"skip to (main )?content.*",
    r"advertisement.*",
    r"\[ad\].*",
]

_BOILERPLATE_RE = re.compile(
    "|".join(_BOILERPLATE_PATTERNS), re.IGNORECASE | re.MULTILINE
)


def clean_text(text: str) -> str:
    """
    Full cleaning pipeline for scraped text:
      1. Unicode normalisation (NFKC)
      2. Remove null bytes and control characters (keep newlines/tabs)
      3. Strip boilerplate phrases
      4. Collapse multiple blank lines to at most two
      5. Collapse multiple spaces/tabs on a single line
      6. Strip leading/trailing whitespace
    """
    if not text:
        return ""

    # 1. Unicode normalisation
    text = unicodedata.normalize("NFKC", text)

    # 2. Remove null bytes and non-printable control chars (keep \n \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 3. Boilerplate removal (line by line for accuracy)
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if _BOILERPLATE_RE.match(stripped):
            continue
        # Skip very short lines that are likely nav elements
        if len(stripped) < 3 and stripped not in (".", "-", "*"):
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # 4. Collapse multiple blank lines → max 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 5. Collapse in-line whitespace
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 6. Strip
    return text.strip()


def clean_title(title: str) -> str:
    """Clean and normalise a page title."""
    if not title:
        return "Untitled"
    title = unicodedata.normalize("NFKC", title)
    # Remove common suffix patterns like " | Site Name"
    title = re.sub(r"\s*[\|–—]\s*.{3,40}$", "", title)
    return title.strip() or "Untitled"


def truncate_content(text: str, max_chars: int = 50_000) -> str:
    """Truncate text at a paragraph boundary near max_chars."""
    if len(text) <= max_chars:
        return text
    # Find last paragraph break before limit
    cutoff = text.rfind("\n\n", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars
    return text[:cutoff].strip() + "\n\n[Content truncated for storage]"


def is_mostly_english(text: str, threshold: float = 0.7) -> bool:
    """
    Rough heuristic: checks if enough characters are ASCII (Latin).
    Not a language detector — just filters obvious non-Latin content.
    """
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= threshold
