"""
Configuration module for Tavily search integration.
Handles environment variable loading, validation, and secret masking.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Automatically load .env file from the project root (one level up from src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)


class ConfigurationError(Exception):
    """Raised when required configuration or environment variables are missing/invalid."""
    pass


def mask_api_key(key: Optional[str]) -> str:
    """
    Mask an API key to safely include in logs or debug strings without exposing secrets.
    Example: 'tvly-abcdef1234567890' -> 'tvly-****...7890'
    """
    if not key:
        return "[NOT CONFIGURED]"
    key_str = str(key).strip()
    if len(key_str) <= 8:
        return "****"
    return f"{key_str[:5]}****...{key_str[-4:]}"


class TavilyConfig:
    """
    Encapsulates Tavily Search API settings loaded from environment variables.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        search_depth: Optional[str] = None,
        max_results: Optional[int] = None,
        topic: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        raw_key = api_key if api_key is not None else os.getenv("TAVILY_API_KEY")
        self.api_key = raw_key.strip() if raw_key else None

        self.search_depth = search_depth or os.getenv("TAVILY_SEARCH_DEPTH", "advanced")
        
        raw_max = max_results or os.getenv("TAVILY_MAX_RESULTS", "5")
        try:
            self.max_results = int(raw_max)
        except (ValueError, TypeError):
            self.max_results = 5

        self.topic = topic or os.getenv("TAVILY_TOPIC", "news")
        
        raw_timeout = timeout or os.getenv("TAVILY_TIMEOUT", "30")
        try:
            self.timeout = int(raw_timeout)
        except (ValueError, TypeError):
            self.timeout = 30

    def validate(self) -> None:
        """
        Validate that the configuration contains a valid, non-placeholder API key.
        Raises ConfigurationError if the key is missing or is the placeholder.
        """
        if not self.api_key:
            raise ConfigurationError(
                "Tavily API key is missing. Please set TAVILY_API_KEY in your .env file "
                "or environment variables (see .env.example for guidance)."
            )
        if self.api_key == "tvly-your-api-key-here" or self.api_key.startswith("your-"):
            raise ConfigurationError(
                "Tavily API key is still set to placeholder value. "
                "Please replace it with your real key from https://app.tavily.com in .env."
            )

    @property
    def is_configured(self) -> bool:
        """Check if an API key is present without raising an exception."""
        try:
            self.validate()
            return True
        except ConfigurationError:
            return False

    def __repr__(self) -> str:
        """Safe string representation that never reveals the raw API key."""
        return (
            f"TavilyConfig(api_key={mask_api_key(self.api_key)}, "
            f"search_depth={self.search_depth!r}, "
            f"max_results={self.max_results}, "
            f"topic={self.topic!r}, "
            f"timeout={self.timeout})"
        )


def get_config() -> TavilyConfig:
    """Convenience factory function to create a TavilyConfig instance."""
    return TavilyConfig()


class USGSConfig:
    """
    Configuration settings for USGS Earthquake Hazards API.
    Does not require an API key (public domain service).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        user_agent: Optional[str] = None,
    ):
        raw_url = base_url or os.getenv(
            "USGS_BASE_URL",
            "https://earthquake.usgs.gov/fdsnws/event/1/query",
        )
        self.base_url = raw_url.strip()

        raw_timeout = timeout or os.getenv("USGS_TIMEOUT", "30")
        try:
            self.timeout = int(raw_timeout)
        except (ValueError, TypeError):
            self.timeout = 30

        raw_ua = user_agent or os.getenv(
            "USGS_USER_AGENT",
            "DisasterIntelligencePipeline/1.0",
        )
        self.user_agent = raw_ua.strip()

    def __repr__(self) -> str:
        return (
            f"USGSConfig(base_url={self.base_url!r}, "
            f"timeout={self.timeout}, "
            f"user_agent={self.user_agent!r})"
        )


def get_usgs_config() -> USGSConfig:
    """Convenience factory function to create a USGSConfig instance."""
    return USGSConfig()


class GDACSConfig:
    """
    Configuration settings for the Global Disaster Alert and Coordination System (GDACS) API.
    A joint framework of the United Nations (OCHA) and the European Commission (JRC).
    Does not require an API key (public service).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        event_data_url: Optional[str] = None,
        timeout: Optional[int] = None,
        user_agent: Optional[str] = None,
    ):
        raw_url = base_url or os.getenv(
            "GDACS_BASE_URL",
            "https://www.gdacs.org/gdacsapi/api/events/geteventlist/search",
        )
        self.base_url = raw_url.strip()

        raw_event_data_url = event_data_url or os.getenv(
            "GDACS_EVENT_DATA_URL",
            "https://www.gdacs.org/gdacsapi/api/events/geteventdata",
        )
        self.event_data_url = raw_event_data_url.strip()

        raw_timeout = timeout or os.getenv("GDACS_TIMEOUT", "30")
        try:
            self.timeout = int(raw_timeout)
        except (ValueError, TypeError):
            self.timeout = 30

        raw_ua = user_agent or os.getenv(
            "GDACS_USER_AGENT",
            "DisasterIntelligencePipeline/1.0",
        )
        self.user_agent = raw_ua.strip()

    def __repr__(self) -> str:
        return (
            f"GDACSConfig(base_url={self.base_url!r}, "
            f"event_data_url={self.event_data_url!r}, "
            f"timeout={self.timeout}, "
            f"user_agent={self.user_agent!r})"
        )


def get_gdacs_config() -> GDACSConfig:
    """Convenience factory function to create a GDACSConfig instance."""
    return GDACSConfig()


class ReliefWebConfig:
    """
    Configuration settings for the ReliefWeb Reports API (UN OCHA).
    ReliefWeb is a leading humanitarian information portal providing situation reports,
    evaluations, and assessments.
    Requires an 'appname' query parameter registered/approved with ReliefWeb per
    https://apidoc.reliefweb.int/parameters#appname.
    """

    def __init__(
        self,
        appname: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        user_agent: Optional[str] = None,
        limit: Optional[int] = None,
    ):
        raw_appname = appname if appname is not None else os.getenv("RELIEFWEB_APPNAME")
        self.appname = raw_appname.strip() if raw_appname else None

        raw_url = base_url or os.getenv(
            "RELIEFWEB_BASE_URL",
            "https://api.reliefweb.int/v2/reports",
        )
        self.base_url = raw_url.strip()

        raw_timeout = timeout or os.getenv("RELIEFWEB_TIMEOUT", "30")
        try:
            self.timeout = int(raw_timeout)
        except (ValueError, TypeError):
            self.timeout = 30

        raw_ua = user_agent or os.getenv(
            "RELIEFWEB_USER_AGENT",
            "DisasterIntelligencePipeline/1.0",
        )
        self.user_agent = raw_ua.strip()

        raw_limit = limit or os.getenv("RELIEFWEB_LIMIT", "10")
        try:
            self.limit = int(raw_limit)
        except (ValueError, TypeError):
            self.limit = 10

    def validate(self) -> None:
        """
        Validate that an approved appname is configured.
        Raises ConfigurationError if missing or set to placeholder.
        """
        if not self.appname:
            raise ConfigurationError(
                "ReliefWeb appname is missing. Please set RELIEFWEB_APPNAME in your .env file "
                "or environment variables (obtain/register an appname at https://apidoc.reliefweb.int/parameters#appname)."
            )
        if self.appname == "your-reliefweb-appname-here" or self.appname.startswith("your-"):
            raise ConfigurationError(
                "ReliefWeb appname is still set to placeholder value. "
                "Please configure an approved appname in RELIEFWEB_APPNAME."
            )

    @property
    def is_configured(self) -> bool:
        """Check if an approved appname is configured without raising an exception."""
        try:
            self.validate()
            return True
        except ConfigurationError:
            return False

    def __repr__(self) -> str:
        return (
            f"ReliefWebConfig(appname={self.appname!r}, "
            f"base_url={self.base_url!r}, "
            f"timeout={self.timeout}, "
            f"user_agent={self.user_agent!r}, "
            f"limit={self.limit})"
        )


def get_reliefweb_config() -> ReliefWebConfig:
    """Convenience factory function to create a ReliefWebConfig instance."""
    return ReliefWebConfig()


class FIRMSConfig:
    """
    Configuration settings for the NASA FIRMS (Fire Information for Resource Management System) API.
    Provides near-real-time and archive active fire / thermal anomaly detections from MODIS and VIIRS.
    Requires a free 32-character MAP_KEY obtained at https://firms.modaps.eosdis.nasa.gov/api/map_key.
    """

    def __init__(
        self,
        map_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_source: Optional[str] = None,
        timeout: Optional[int] = None,
        user_agent: Optional[str] = None,
    ):
        raw_key = map_key if map_key is not None else os.getenv("FIRMS_MAP_KEY")
        self.map_key = raw_key.strip() if raw_key else None

        raw_url = base_url or os.getenv(
            "FIRMS_BASE_URL",
            "https://firms.modaps.eosdis.nasa.gov/api",
        )
        self.base_url = raw_url.strip().rstrip("/")

        raw_source = default_source or os.getenv("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
        self.default_source = raw_source.strip()

        raw_timeout = timeout or os.getenv("FIRMS_TIMEOUT", "30")
        try:
            self.timeout = int(raw_timeout)
        except (ValueError, TypeError):
            self.timeout = 30

        raw_ua = user_agent or os.getenv(
            "FIRMS_USER_AGENT",
            "DisasterIntelligencePipeline/1.0",
        )
        self.user_agent = raw_ua.strip()

    def validate(self) -> None:
        """
        Validate that a non-placeholder MAP_KEY is configured.
        Raises ConfigurationError if missing or set to placeholder.
        """
        if not self.map_key:
            raise ConfigurationError(
                "NASA FIRMS MAP_KEY is missing. Please set FIRMS_MAP_KEY in your .env file "
                "or environment variables (obtain a free key at https://firms.modaps.eosdis.nasa.gov/api/map_key)."
            )
        if self.map_key == "your-nasa-firms-map-key-here" or self.map_key.startswith("your-"):
            raise ConfigurationError(
                "NASA FIRMS MAP_KEY is still set to placeholder value. "
                "Please obtain your free 32-character key from https://firms.modaps.eosdis.nasa.gov/api/map_key and configure FIRMS_MAP_KEY in .env."
            )

    @property
    def is_configured(self) -> bool:
        """Check if a MAP_KEY is configured without raising an exception."""
        try:
            self.validate()
            return True
        except ConfigurationError:
            return False

    def __repr__(self) -> str:
        """Safe representation that masks MAP_KEY to prevent leaking secrets."""
        return (
            f"FIRMSConfig(map_key={mask_api_key(self.map_key)}, "
            f"base_url={self.base_url!r}, "
            f"default_source={self.default_source!r}, "
            f"timeout={self.timeout}, "
            f"user_agent={self.user_agent!r})"
        )


def get_firms_config() -> FIRMSConfig:
    """Convenience factory function to create a FIRMSConfig instance."""
    return FIRMSConfig()


