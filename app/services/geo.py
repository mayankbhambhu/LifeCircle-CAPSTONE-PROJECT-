"""Distance maths for urgent-mode ranking.

We use the haversine (great-circle) formula, which is accurate to well under
1% for city distances. Road distance / travel time is out of scope.
"""
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088
DEFAULT_RADIUS_KM = 10.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp = p2 - p1
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def format_km(km: float) -> str:
    return f"{km:.1f} km"
