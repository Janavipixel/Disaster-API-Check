"""
Unit tests for configuration and environment loading.
"""

import os
import pytest
from src.config import ConfigurationError, TavilyConfig, mask_api_key


def test_mask_api_key():
    assert mask_api_key(None) == "[NOT CONFIGURED]"
    assert mask_api_key("") == "[NOT CONFIGURED]"
    assert mask_api_key("1234567") == "****"
    
    key = "tvly-prod-secret-9876543210"
    masked = mask_api_key(key)
    assert "prod-secret" not in masked
    assert masked.startswith("tvly-")
    assert masked.endswith("3210")


def test_tavily_config_missing_key():
    config = TavilyConfig(api_key=None)
    # Ensure env is empty for this test
    old_env = os.environ.pop("TAVILY_API_KEY", None)
    try:
        config = TavilyConfig(api_key="")
        assert not config.is_configured
        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()
        assert "Tavily API key is missing" in str(exc_info.value)
    finally:
        if old_env is not None:
            os.environ["TAVILY_API_KEY"] = old_env


def test_tavily_config_placeholder_key():
    config = TavilyConfig(api_key="tvly-your-api-key-here")
    assert not config.is_configured
    with pytest.raises(ConfigurationError) as exc_info:
        config.validate()
    assert "placeholder" in str(exc_info.value).lower()


def test_tavily_config_valid_key():
    config = TavilyConfig(api_key="tvly-test-sample-key-1234")
    assert config.is_configured
    config.validate()  # Should not raise
    assert "test-sample" not in repr(config)  # Must never leak raw key in repr


def test_tavily_config_defaults_and_overrides():
    config = TavilyConfig(
        api_key="tvly-valid-key-9999",
        search_depth="advanced",
        max_results=10,
        topic="news",
        timeout=45,
    )
    assert config.search_depth == "advanced"
    assert config.max_results == 10
    assert config.topic == "news"
    assert config.timeout == 45


def test_gdacs_config_env_vars():
    from src.config import GDACSConfig, get_gdacs_config
    old_base = os.environ.get("GDACS_BASE_URL")
    old_timeout = os.environ.get("GDACS_TIMEOUT")
    try:
        os.environ["GDACS_BASE_URL"] = "https://custom.gdacs.org/api/events/search"
        os.environ["GDACS_TIMEOUT"] = "40"
        cfg = get_gdacs_config()
        assert cfg.base_url == "https://custom.gdacs.org/api/events/search"
        assert cfg.timeout == 40
        assert "custom.gdacs.org" in repr(cfg)
    finally:
        if old_base is not None:
            os.environ["GDACS_BASE_URL"] = old_base
        else:
            os.environ.pop("GDACS_BASE_URL", None)
        if old_timeout is not None:
            os.environ["GDACS_TIMEOUT"] = old_timeout
        else:
            os.environ.pop("GDACS_TIMEOUT", None)


def test_reliefweb_config_env_vars():
    from src.config import ReliefWebConfig, get_reliefweb_config
    old_base = os.environ.get("RELIEFWEB_BASE_URL")
    old_appname = os.environ.get("RELIEFWEB_APPNAME")
    old_timeout = os.environ.get("RELIEFWEB_TIMEOUT")
    try:
        os.environ["RELIEFWEB_BASE_URL"] = "https://custom.reliefweb.int/v2/reports"
        os.environ["RELIEFWEB_APPNAME"] = "CustomApp-EnvTest"
        os.environ["RELIEFWEB_TIMEOUT"] = "45"
        cfg = get_reliefweb_config()
        assert cfg.base_url == "https://custom.reliefweb.int/v2/reports"
        assert cfg.appname == "CustomApp-EnvTest"
        assert cfg.timeout == 45
        assert "CustomApp-EnvTest" in repr(cfg)
    finally:
        if old_base is not None:
            os.environ["RELIEFWEB_BASE_URL"] = old_base
        else:
            os.environ.pop("RELIEFWEB_BASE_URL", None)
        if old_appname is not None:
            os.environ["RELIEFWEB_APPNAME"] = old_appname
        else:
            os.environ.pop("RELIEFWEB_APPNAME", None)
        if old_timeout is not None:
            os.environ["RELIEFWEB_TIMEOUT"] = old_timeout
        else:
            os.environ.pop("RELIEFWEB_TIMEOUT", None)


def test_firms_config_env_vars():
    from src.config import FIRMSConfig, get_firms_config
    old_key = os.environ.get("FIRMS_MAP_KEY")
    old_base = os.environ.get("FIRMS_BASE_URL")
    old_source = os.environ.get("FIRMS_SOURCE")
    old_timeout = os.environ.get("FIRMS_TIMEOUT")
    try:
        os.environ["FIRMS_MAP_KEY"] = "abcdef1234567890abcdef1234567890"
        os.environ["FIRMS_BASE_URL"] = "https://custom.firms.nasa.gov/api"
        os.environ["FIRMS_SOURCE"] = "MODIS_NRT"
        os.environ["FIRMS_TIMEOUT"] = "50"
        cfg = get_firms_config()
        assert cfg.map_key == "abcdef1234567890abcdef1234567890"
        assert cfg.base_url == "https://custom.firms.nasa.gov/api"
        assert cfg.default_source == "MODIS_NRT"
        assert cfg.timeout == 50
        assert "abcdef1234567890abcdef1234567890" not in repr(cfg)
        assert "****" in repr(cfg)
    finally:
        if old_key is not None:
            os.environ["FIRMS_MAP_KEY"] = old_key
        else:
            os.environ.pop("FIRMS_MAP_KEY", None)
        if old_base is not None:
            os.environ["FIRMS_BASE_URL"] = old_base
        else:
            os.environ.pop("FIRMS_BASE_URL", None)
        if old_source is not None:
            os.environ["FIRMS_SOURCE"] = old_source
        else:
            os.environ.pop("FIRMS_SOURCE", None)
        if old_timeout is not None:
            os.environ["FIRMS_TIMEOUT"] = old_timeout
        else:
            os.environ.pop("FIRMS_TIMEOUT", None)

