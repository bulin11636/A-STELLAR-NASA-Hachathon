import math

from app.contracts.api import MarsCoordinate
from app.evidence.models import EvidenceRoi, TrackSegment

# PLACES SIS sections 3.9.1 / 5.1.3: global northing/easting conversion.
MARS_RADIUS_M = 3396190.0
STANDARD_PARALLEL_DEG = 18.4663


def from_places_projected(northing: float, easting: float) -> MarsCoordinate:
    if not math.isfinite(northing) or not math.isfinite(easting):
        raise ValueError("Nonfinite PLACES projected coordinates.")
    longitude = math.degrees(easting / (MARS_RADIUS_M * math.cos(math.radians(STANDARD_PARALLEL_DEG))))
    if not -180 <= longitude <= 360:
        raise ValueError("Invalid source longitude domain.")
    return MarsCoordinate(longitude=longitude % 360, latitude=math.degrees(northing / MARS_RADIUS_M))


def verified_map_point(coordinates: list, properties: dict) -> MarsCoordinate:
    """Interpret NASA mapping JSON only with independent projected-field checks.

    The export's Earth-like CRS84 tag is not authority for Mars semantics.
    These values must agree with the explicit PLACES planetocentric formula.
    This does NOT validate the existing NASA WMTS's latitude convention.
    """
    if len(coordinates) not in (2, 3):
        raise ValueError("Expected a point with longitude, latitude and optional elevation.")
    point = MarsCoordinate(longitude=coordinates[0], latitude=coordinates[1])
    supplied = MarsCoordinate(longitude=properties["lon"], latitude=properties["lat"])
    expected = from_places_projected(properties["northing"], properties["easting"])
    if abs(point.longitude - expected.longitude) > 2e-7 or abs(point.latitude - expected.latitude) > 2e-7:
        raise ValueError("Point disagrees with the documented planetocentric projected coordinates.")
    if abs(supplied.longitude - point.longitude) > 2e-7 or abs(supplied.latitude - point.latitude) > 2e-7:
        raise ValueError("Geometry and source coordinate fields disagree.")
    return point


def nearest_track_distance_m(point: MarsCoordinate, segments: list[TrackSegment], roi: EvidenceRoi) -> float | None:
    """2D geometric proximity in local Mars-sphere AEQD; never a safety score.

    Explicit sphere/ROI limit avoids Earth defaults and unbounded projection use.
    It is an approximation to surface distance, with no terrain/elevation model.
    """
    if not roi.contains(point):
        return None
    from pyproj import CRS, Transformer

    center = roi.center
    geographic = CRS.from_proj4(f"+proj=longlat +R={MARS_RADIUS_M} +no_defs")
    projected = CRS.from_proj4(f"+proj=aeqd +R={MARS_RADIUS_M} +lon_0={center.longitude} +lat_0={center.latitude} +units=m +no_defs")
    transform = Transformer.from_crs(geographic, projected, always_xy=True)
    px, py = transform.transform(point.longitude, point.latitude, errcheck=True)
    distances = []
    for segment in segments:
        for first, second in zip(segment.points, segment.points[1:]):
            if not roi.contains(first) or not roi.contains(second):
                continue
            ax, ay = transform.transform(first.longitude, first.latitude, errcheck=True)
            bx, by = transform.transform(second.longitude, second.latitude, errcheck=True)
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            fraction = min(1, max(0, ((px - ax) * dx + (py - ay) * dy) / length2)) if length2 else 0
            distances.append(math.hypot(px - (ax + fraction * dx), py - (ay + fraction * dy)))
    return min(distances) if distances else None
