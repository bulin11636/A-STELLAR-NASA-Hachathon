from collections import Counter
import hashlib
from urllib.parse import urljoin, urlparse

from app.contracts.api import MarsCoordinate
from app.contracts.workers import SciencePOI, SourceReference
from app.evidence.coordinates import verified_map_point
from app.evidence.models import EvidenceDataset, EvidenceRoi, LocalizedStop, TrackSegment

MAP_CONFIG = "https://mars.nasa.gov/maps/location/api/configure/get?mission=M20"
MAP_BASE = "https://mars.nasa.gov/mmgis-maps/M20/"
GEOLOGY_NOT_LOADED = "Geology-unit attribution is not loaded."
SOURCE_URLS = {
    "waypoints": MAP_BASE + "Layers/json/M20_waypoints.json",
    "traverse": MAP_BASE + "Layers/json/M20_traverse.json",
    "samples": MAP_BASE + "Layers/json/M20_SAMPLE_v3.json",
}


def features(body: dict) -> list[dict]:
    if not isinstance(body, dict) or body.get("type") != "FeatureCollection" or not isinstance(body.get("features"), list):
        raise ValueError("Expected an official mapping FeatureCollection.")
    if not isinstance(body.get("name"), str) or not body["name"].strip():
        raise ValueError("A source collection name is required for provenance.")
    if "crs" in body and body["crs"] != {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}:
        raise ValueError("Unexpected transport CRS label; do not silently transform Mars coordinates.")
    return body["features"]


def source(kind: str, dataset_id: str) -> SourceReference:
    return SourceReference(dataset_id=dataset_id, source_url=SOURCE_URLS[kind], mission="Mars 2020 / Perseverance",
                           instrument="Derived mission mapping; individual instrument attribution not specified")


def normalize_evidence(*, waypoints: dict, traverse: dict, samples: dict,
                       controls: dict[str, MarsCoordinate], roi: EvidenceRoi,
                       dataset_version: str, provenance_ref: str, artifact_ref: str) -> EvidenceDataset:
    for body in (waypoints, traverse, samples):
        features(body)
    warnings = [
        "Historical rover evidence is not evidence of astronaut safety; no route cost is reduced.",
        "Evidence selection ROI is not a verified DEM planning ROI. WMTS alignment remains unvalidated.",
        "Science POIs are unranked; an agreed priority rubric is not loaded.",
        GEOLOGY_NOT_LOADED,
        "Proximity uses a local Mars-sphere metric approximation, not terrain/elevation-aware distance.",
        "Source export sol labels are retained; download time is not acquisition time.",
        "Observation URLs are source-provided references, not guarantees of image availability.",
    ]
    counts = Counter()
    stops_by_rmc = {}
    conflict_ids = set()
    waypoints_id = f"nasa-m20-waypoints:{waypoints.get('name', 'unversioned')}"
    sample_id = f"nasa-m20-samples:{samples.get('name', 'unversioned')}"
    traverse_id = f"nasa-m20-traverse:{traverse.get('name', 'unversioned')}"
    for feature in features(waypoints):
        try:
            props = feature["properties"]
            if feature["geometry"]["type"] != "Point" or type(props["sol"]) is not int or props["sol"] < 0:
                raise ValueError("Missing position or sol.")
            if any(type(props[key]) is not int or props[key] < 0 for key in ("site", "drive")):
                raise ValueError("Missing integer site/drive.")
            point = verified_map_point(feature["geometry"]["coordinates"], props)
            rmc = f"{int(props['site'])}_{int(props['drive'])}"
            if props["RMC"] != rmc:
                raise ValueError("RMC fields disagree.")
            links = []
            images = props.get("images", [])
            if not isinstance(images, list):
                counts["invalid_observation_links"] += 1
                images = []
            for image in images:
                if not isinstance(image, dict) or not isinstance(image.get("url"), str):
                    counts["invalid_observation_links"] += 1
                    continue
                url = urljoin(MAP_BASE, image["url"])
                if urlparse(url).scheme == "https" and urlparse(url).netloc == "mars.nasa.gov" and urlparse(url).path.startswith("/mmgis-maps/M20/"):
                    links.append(url)
            stop = LocalizedStop(record_id=rmc, sol=props["sol"], **point.model_dump(),
                                 source=source("waypoints", waypoints_id), observation_urls=links)
            if rmc in stops_by_rmc and stops_by_rmc[rmc] != stop:
                conflict_ids.add(rmc)
            else:
                stops_by_rmc[rmc] = stop
        except (KeyError, TypeError, ValueError):
            counts["invalid_waypoints"] += 1
    for key in conflict_ids:
        stops_by_rmc.pop(key, None)
    counts["conflicting_waypoints"] = len(conflict_ids)
    shared = [(point, stops_by_rmc[key]) for key, point in controls.items() if key in stops_by_rmc]
    if len(shared) < 2 or any(abs(first.longitude - second.longitude) > 2e-7 or abs(first.latitude - second.latitude) > 2e-7 for first, second in shared):
        raise ValueError("Official map export does not agree with at least two independent PDS coordinate controls.")

    segments = []
    segment_ids = set()
    for feature in features(traverse):
        try:
            props = feature["properties"]
            sol = props["sol"]
            if type(sol) is not int or sol < 0 or feature["geometry"]["type"] != "LineString":
                raise ValueError("Invalid traverse geometry/sol.")
            vertices = [MarsCoordinate(longitude=pair[0], latitude=pair[1]) for pair in feature["geometry"]["coordinates"]]
            # Keep source features separate. Never bridge missing positions or
            # invent links between successive sols/RMCs.
            first = stops_by_rmc[props["fromRMC"]]
            last = stops_by_rmc[props["toRMC"]]
            if len(vertices) < 2 or last.sol != sol or any(
                abs(endpoint.longitude - control.longitude) > 2e-7 or abs(endpoint.latitude - control.latitude) > 2e-7
                for endpoint, control in ((vertices[0], first), (vertices[-1], last))
            ):
                raise ValueError("Unverified segment endpoints.")
            # Split at ROI exclusions rather than drawing a shortcut across it.
            run = []
            for point in vertices + [None]:
                if point is not None and roi.contains(point):
                    if not run or point != run[-1]:
                        run.append(point)
                else:
                    if len(run) >= 2:
                        digest = hashlib.sha256(str([(p.longitude, p.latitude) for p in run]).encode()).hexdigest()[:12]
                        key = f"{sol}:{props['fromRMC']}:{props['toRMC']}:{digest}"
                        # Exact duplicate source features are suppressed below.
                        signature = (sol, tuple((p.longitude, p.latitude) for p in run))
                        if signature not in segment_ids:
                            segments.append(TrackSegment(record_id=key, sol=sol, points=run))
                            segment_ids.add(signature)
                    run = []
        except (KeyError, IndexError, TypeError, ValueError):
            counts["invalid_segments"] += 1

    pois = {}
    conflicted_pois = set()
    excluded_science = []
    for index, feature in enumerate(features(samples)):
        try:
            props = feature["properties"]
            if feature["geometry"]["type"] != "Point":
                raise ValueError("Science POI must be a point.")
            point = verified_map_point(feature["geometry"]["coordinates"], props)
            if not roi.contains(point):
                counts["out_of_roi_pois"] += 1
                continue
            # Combined sample numbers remain one documented site; do not split
            # strings such as '2 & 3' into invented independently located POIs.
            key = str(props["sample_num"]).strip()
            if not key or props["sample_num"] is None or any(
                not isinstance(props.get(field), str) or not props[field].strip() for field in ("sample_name", "sample_type")
            ):
                raise ValueError("Missing sample identity or category.")
            poi = SciencePOI(id=f"nasa-m20-sample:{key}", **point.model_dump(),
                             category=props["sample_type"].strip().lower().replace(" ", "_"),
                             source=source("samples", sample_id),
                             rationale=f"Documented sample site {props['sample_name']} at {props.get('outcrop_name') or 'unspecified outcrop'}; source class: {props['sample_type']}. Historical science context only; no future sampling priority inferred.")
            if key in pois and pois[key] != poi:
                conflicted_pois.add(key)
            else:
                pois[key] = poi
        except (KeyError, TypeError, ValueError) as error:
            counts["invalid_pois"] += 1
            identifier = feature.get("properties", {}).get("sample_num", index) if isinstance(feature, dict) and isinstance(feature.get("properties"), dict) else index
            excluded_science.append(f"{identifier}: {str(error).splitlines()[0][:160]}")
    for key in conflicted_pois:
        pois.pop(key, None)
    counts["conflicting_pois"] = len(conflicted_pois)
    if excluded_science:
        warnings.append("Excluded science source records (first 10): " + "; ".join(excluded_science[:10]))
    warnings.append("Excluded/ambiguous input counts: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) + ".")
    return EvidenceDataset(
        dataset_version=dataset_version, roi=roi,
        stops=sorted((stop for stop in stops_by_rmc.values() if roi.contains(stop)), key=lambda stop: (stop.sol, stop.record_id)),
        segments=sorted(segments, key=lambda segment: (segment.sol, segment.record_id)),
        pois=sorted(pois.values(), key=lambda poi: poi.id), dataset_ids=[waypoints_id, traverse_id, sample_id],
        warnings=warnings, provenance_ref=provenance_ref, artifact_ref=artifact_ref,
    )
