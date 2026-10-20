"""
External API client integrations for disaster intelligence feeds:
USGS Earthquake API, GDACS, ReliefWeb, NASA FIRMS, and Weather services.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.clients.usgs_client import (
        USGSClient,
        USGSClientError,
        USGSHTTPError,
        USGSInvalidParameterError,
        USGSNetworkError,
        USGSParsingError,
        USGSTimeoutError,
    )
    from src.clients.gdacs_client import (
        GDACSClient,
        GDACSClientError,
        GDACSHTTPError,
        GDACSInvalidParameterError,
        GDACSNetworkError,
        GDACSParsingError,
        GDACSTimeoutError,
    )
    from src.clients.reliefweb_client import (
        ReliefWebClient,
        ReliefWebClientError,
        ReliefWebHTTPError,
        ReliefWebInvalidParameterError,
        ReliefWebNetworkError,
        ReliefWebParsingError,
        ReliefWebTimeoutError,
    )
    from src.clients.firms_client import (
        FIRMSClient,
        FIRMSClientError,
        FIRMSHTTPError,
        FIRMSInvalidParameterError,
        FIRMSNetworkError,
        FIRMSParsingError,
        FIRMSTimeoutError,
    )

__all__ = [
    # USGS
    "USGSClient",
    "USGSClientError",
    "USGSInvalidParameterError",
    "USGSTimeoutError",
    "USGSHTTPError",
    "USGSParsingError",
    "USGSNetworkError",
    # GDACS
    "GDACSClient",
    "GDACSClientError",
    "GDACSInvalidParameterError",
    "GDACSTimeoutError",
    "GDACSHTTPError",
    "GDACSParsingError",
    "GDACSNetworkError",
    # ReliefWeb
    "ReliefWebClient",
    "ReliefWebClientError",
    "ReliefWebInvalidParameterError",
    "ReliefWebTimeoutError",
    "ReliefWebHTTPError",
    "ReliefWebParsingError",
    "ReliefWebNetworkError",
    # NASA FIRMS
    "FIRMSClient",
    "FIRMSClientError",
    "FIRMSInvalidParameterError",
    "FIRMSTimeoutError",
    "FIRMSHTTPError",
    "FIRMSParsingError",
    "FIRMSNetworkError",
]


def __getattr__(name: str):
    if name.startswith("USGS"):
        import src.clients.usgs_client as usgs_mod
        return getattr(usgs_mod, name)
    if name.startswith("GDACS"):
        import src.clients.gdacs_client as gdacs_mod
        return getattr(gdacs_mod, name)
    if name.startswith("ReliefWeb"):
        import src.clients.reliefweb_client as rw_mod
        return getattr(rw_mod, name)
    if name.startswith("FIRMS"):
        import src.clients.firms_client as firms_mod
        return getattr(firms_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

