"""Swappable maps/ETA provider adapter (contract section 11.3 step 6).

The MVP ships a deterministic haversine estimator so the demo runs without a map
vendor key. A real provider must be approved before production use; on any provider
failure the caller falls back to distance-based estimation.
"""

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from app.core.config import Settings, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MOCK_PROVIDER = "mock"
EARTH_RADIUS_KM = 6371.0088

EstimateSource = Literal["provider", "fallback"]


@dataclass(frozen=True, slots=True)
class Coordinate:
    latitude: float
    longitude: float

    @classmethod
    def from_decimals(cls, latitude: Decimal | float, longitude: Decimal | float) -> "Coordinate":
        return cls(float(latitude), float(longitude))


@dataclass(frozen=True, slots=True)
class RouteEstimate:
    eta_minutes: int | None
    distance_km: float | None
    source: EstimateSource


class MapsProvider(Protocol):
    name: str

    def route(self, origin: Coordinate, destination: Coordinate) -> RouteEstimate: ...


def haversine_km(origin: Coordinate, destination: Coordinate) -> float:
    lat1, lon1 = math.radians(origin.latitude), math.radians(origin.longitude)
    lat2, lon2 = math.radians(destination.latitude), math.radians(destination.longitude)
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@dataclass(frozen=True, slots=True)
class MockMapsProvider:
    """Straight-line distance converted to an urban driving estimate."""

    average_speed_kmh: float = 30.0
    traffic_factor: float = 1.25
    name: str = MOCK_PROVIDER

    def route(self, origin: Coordinate, destination: Coordinate) -> RouteEstimate:
        distance = haversine_km(origin, destination)
        eta = distance * self.traffic_factor / self.average_speed_kmh * 60
        return RouteEstimate(
            eta_minutes=max(1, round(eta)), distance_km=round(distance, 3), source="provider"
        )


class MapsUnavailableError(RuntimeError):
    """Raised by a provider that cannot answer; callers fall back to distance."""


def build_maps_provider(config: Settings | None = None) -> MapsProvider:
    config = config or settings
    if config.maps_provider.lower() == MOCK_PROVIDER:
        return MockMapsProvider()
    raise ValueError(
        f"Unsupported MAPS_PROVIDER={config.maps_provider!r}. "
        "A real routing vendor requires an approved API key."
    )


def estimate_route(
    provider: MapsProvider, origin: Coordinate, destination: Coordinate
) -> RouteEstimate:
    """Never let a provider outage break Matching - degrade to a labelled estimate."""
    fallback = FallbackDistanceEstimator().route(origin, destination)
    try:
        estimate = provider.route(origin, destination)
    except Exception as exc:  # provider errors are expected and must not crash dispatch
        logger.warning("maps_provider_failed", extra={"error_type": type(exc).__name__})
        return fallback
    if estimate.eta_minutes is None and estimate.distance_km is None:
        return fallback
    return estimate


@dataclass(frozen=True, slots=True)
class FallbackDistanceEstimator:
    """Section 11.3: when ETA is unavailable, `distance_km` is the ranking input."""

    average_speed_kmh: float = 30.0

    def route(self, origin: Coordinate, destination: Coordinate) -> RouteEstimate:
        distance = haversine_km(origin, destination)
        return RouteEstimate(
            eta_minutes=None, distance_km=round(distance, 3), source="fallback"
        )
