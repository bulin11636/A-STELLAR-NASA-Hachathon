"""Synthetic fixtures exercise ingestion; no synthetic sample is a measurement."""
import asyncio
from copy import deepcopy
import csv
import io
import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.api import MarsCoordinate
from app.contracts.workers import WorkerContext
from app.coordinator.dispatcher import AgentDispatcher
from app.agents.registry import WorkerRegistry
from app.evidence.adapters import SOURCE_URLS, normalize_evidence
from app.evidence.coordinates import MARS_RADIUS_M, STANDARD_PARALLEL_DEG, from_places_projected, nearest_track_distance_m, verified_map_point
from app.evidence.models import EvidenceRoi, PREVIEW_ROI, TrackSegment
from app.evidence.places import parse_places
from app.evidence import snapshots
from app.agents.a6 import RoverEvidenceWorker
from app.agents.a4 import ScienceEvidenceWorker


def test_published_pds_control_matches_source_projection_without_claiming_wmts_alignment():
    fixture = json.loads((Path(__file__).resolve().parents[2] / "data/fixtures/jezero-pds-control.json").read_text())
    point = fixture["source_projected"]
    wire = from_places_projected(point["northing_m"], point["easting_m"])
    assert wire.longitude == pytest.approx(fixture["wire_coordinate"]["longitude"], abs=2e-7)
    assert wire.latitude == pytest.approx(fixture["wire_coordinate"]["latitude"], abs=2e-7)
    assert fixture["wmts_alignment_validated"] is False
    assert fixture["dem_alignment_validated"] is False


def properties(longitude, latitude):
    return {"lon": longitude, "lat": latitude, "northing": math.radians(latitude) * MARS_RADIUS_M,
            "easting": math.radians(longitude) * MARS_RADIUS_M * math.cos(math.radians(STANDARD_PARALLEL_DEG))}


def point_feature(longitude, latitude, **props):
    return {"type": "Feature", "properties": {**properties(longitude, latitude), **props},
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]}}


def collection(features):
    return {"type": "FeatureCollection", "name": "synthetic-test-only", "features": features}


def fixtures():
    waypoints = collection([
        point_feature(77.4, 18.4, RMC="3_0", site=3, drive=0, sol=1, images=[{"url": "Layers/mosaics/synthetic.jpg"}]),
        point_feature(77.41, 18.41, RMC="3_10", site=3, drive=10, sol=1),
        point_feature(77.42, 18.42, RMC="3_20", site=3, drive=20, sol=2),
    ])
    traverse = collection([
        {"type": "Feature", "properties": {"sol": 1, "fromRMC": "3_0", "toRMC": "3_10"},
         "geometry": {"type": "LineString", "coordinates": [[77.4, 18.4], [77.41, 18.41]]}},
        {"type": "Feature", "properties": {"sol": 2, "fromRMC": "3_10", "toRMC": "3_20"},
         "geometry": {"type": "LineString", "coordinates": [[77.41, 18.41], [77.42, 18.42]]}},
    ])
    samples = collection([
        point_feature(77.4, 18.4, sample_num="2 & 3", sample_name="Synthetic A", sample_type="Rock Core", outcrop_name="Synthetic"),
        point_feature(77.42, 18.42, sample_num="4", sample_name="Synthetic B", sample_type="Regolith", outcrop_name="Synthetic"),
    ])
    return {"waypoints": waypoints, "traverse": traverse, "samples": samples,
            "controls": {"3_0": MarsCoordinate(longitude=77.4, latitude=18.4), "3_10": MarsCoordinate(longitude=77.41, latitude=18.41)},
            "roi": PREVIEW_ROI, "dataset_version": "synthetic-v1", "provenance_ref": "synthetic-manifest.json", "artifact_ref": "synthetic-artifact.json"}


def test_synthetic_adapter_preserves_same_sol_positions_and_unranked_science():
    dataset = normalize_evidence(**fixtures())
    assert len(dataset.stops) == 3
    assert [stop.sol for stop in dataset.stops] == [1, 1, 2]
    assert len(dataset.segments) == 2
    assert dataset.pois[0].id == "nasa-m20-sample:2 & 3"
    assert all(poi.priority is None and poi.priority_method is None for poi in dataset.pois)
    assert dataset.stops[0].observation_urls[0].host == "mars.nasa.gov"


def test_duplicates_conflicts_and_stable_order_do_not_invent_rankings():
    data = fixtures()
    expected = normalize_evidence(**data)
    for key in ("waypoints", "traverse", "samples"):
        data[key]["features"].append(deepcopy(data[key]["features"][0]))
        data[key]["features"].reverse()
    actual = normalize_evidence(**data)
    assert actual.stops == expected.stops
    assert actual.segments == expected.segments
    assert actual.pois == expected.pois
    conflict = deepcopy(data["samples"]["features"][0])
    conflict["properties"]["sample_name"] = "Contradictory science site"
    data["samples"]["features"].append(conflict)
    actual = normalize_evidence(**data)
    assert len(actual.pois) == 1
    assert "conflicting_pois=1" in actual.warnings[-1]


@pytest.mark.parametrize("mutation", ["missing_position", "unknown_sol", "string_sol", "fractional_site"])
def test_bad_waypoints_are_excluded_and_never_linked(mutation):
    data = fixtures()
    last = data["waypoints"]["features"][-1]
    if mutation == "missing_position":
        last["geometry"] = None
    elif mutation == "unknown_sol":
        last["properties"]["sol"] = -1
    elif mutation == "string_sol":
        last["properties"]["sol"] = "2"
    else:
        last["properties"]["site"] = 3.5
    result = normalize_evidence(**data)
    assert len(result.stops) == 2
    assert len(result.segments) == 1
    assert "invalid_waypoints=1" in result.warnings[-1]


def test_conflicting_rover_positions_are_removed_instead_of_chosen():
    data = fixtures()
    changed = point_feature(77.43, 18.43, RMC="3_20", site=3, drive=20, sol=2)
    data["waypoints"]["features"].append(changed)
    result = normalize_evidence(**data)
    assert len(result.stops) == 2
    assert len(result.segments) == 1


def test_missing_provenance_wrong_crs_and_control_mismatch_are_failures():
    data = fixtures()
    data["waypoints"].pop("name")
    with pytest.raises(ValueError):
        normalize_evidence(**data)
    data = fixtures()
    data["traverse"]["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    with pytest.raises(ValueError):
        normalize_evidence(**data)
    data = fixtures()
    data["controls"]["3_0"] = MarsCoordinate(longitude=77.5, latitude=18.5)
    with pytest.raises(ValueError):
        normalize_evidence(**data)
    with pytest.raises(ValueError):
        verified_map_point([77.4, 18.5], properties(77.4, 18.4))
    with pytest.raises(ValueError):
        verified_map_point([77.4, 18.4], {**properties(77.4, 18.4), "lat": float("nan")})


def test_out_of_roi_pois_and_disconnected_tracks_remain_unknown():
    data = fixtures()
    data["samples"]["features"].append(point_feature(78, 18.4, sample_num="outside", sample_name="Outside", sample_type="Rock Core"))
    result = normalize_evidence(**data)
    assert len(result.pois) == 2
    assert "out_of_roi_pois=1" in result.warnings[-1]
    data["traverse"]["features"][0]["geometry"]["coordinates"] = [[77.4, 18.4], [78, 18.5], [77.41, 18.41]]
    result = normalize_evidence(**data)
    assert len(result.segments) == 1  # Two isolated vertices never become a shortcut.
    assert result.segments[0].sol == 2


def test_observation_links_are_allowlisted_and_optional():
    data = fixtures()
    data["waypoints"]["features"][0]["properties"]["images"] = [{"url": "https://evil.example/test.jpg"}, {"no_url": True}]
    result = normalize_evidence(**data)
    assert len(result.stops) == 3
    assert result.stops[0].observation_urls == []


def test_local_metric_geometry_wraparound_and_unknown_coverage():
    roi = EvidenceRoi(roi_id="synthetic-wrap", west=359.99, east=.01, south=-.01, north=.01)
    segment = TrackSegment(record_id="synthetic-only", sol=1, points=[MarsCoordinate(longitude=359.999, latitude=0), MarsCoordinate(longitude=.001, latitude=0)])
    assert nearest_track_distance_m(MarsCoordinate(longitude=0, latitude=0), [segment], roi) == pytest.approx(0, abs=1e-8)
    distance = nearest_track_distance_m(MarsCoordinate(longitude=0, latitude=.001), [segment], roi)
    assert distance == pytest.approx(MARS_RADIUS_M * math.radians(.001), rel=1e-6)
    assert nearest_track_distance_m(MarsCoordinate(longitude=77, latitude=18), [segment], roi) is None
    assert nearest_track_distance_m(MarsCoordinate(longitude=0, latitude=0), [], roi) is None
    with pytest.raises(ValidationError):
        EvidenceRoi(roi_id="../bad", west=77, east=78, south=18, north=19)
    with pytest.raises(ValidationError):
        EvidenceRoi(roi_id="global", west=0, east=180, south=-90, north=90)


def test_observed_workers_are_callable_without_changing_the_default_registry():
    dataset = normalize_evidence(**fixtures())
    registry = WorkerRegistry()
    registry.register(ScienceEvidenceWorker(dataset))
    registry.register(RoverEvidenceWorker(dataset, MarsCoordinate(longitude=77.4, latitude=18.4)))
    context = WorkerContext(mission_id="synthetic", region_id="jezero", roi_id=dataset.roi.roi_id, dataset_version=dataset.dataset_version)
    report = asyncio.run(AgentDispatcher(registry).run(context, ("A4", "A6")))
    assert [result.status for result in report.results] == ["partial", "partial"]
    assert all(result.data_kind == "observed" for result in report.results)
    assert report.results[1].nearest_track_distance_m == pytest.approx(0)
    wrong = context.model_copy(update={"dataset_version": "wrong"})
    result = asyncio.run(RoverEvidenceWorker(dataset).run(wrong))
    assert result.status == "unavailable" and result.nearest_track_distance_m is None
    result = asyncio.run(ScienceEvidenceWorker(dataset, frozenset({"absent"})).run(context))
    assert result.status == "unavailable" and result.pois == []


def places_fixture():
    names = ["frame", "site", "drive", "sol", "longitude", "planetocentric_latitude", "planetodetic_latitude", "northing", "easting"]
    units = {"longitude": "DEGREE", "planetocentric_latitude": "DEGREE", "northing": "METER", "easting": "METER"}
    fields = "".join(f"<Field_Delimited><name>{name}</name><unit>{units.get(name, '')}</unit></Field_Delimited>" for name in names)
    label = f'''<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1"><Identification_Area><logical_identifier>urn:nasa:pds:mars2020_rover_places:data_localizations:best_tactical.csv</logical_identifier><version_id>synthetic-test</version_id></Identification_Area><Table_Delimited><records>4</records><Record_Delimited>{fields}</Record_Delimited></Table_Delimited></Product_Observational>'''
    rows = []
    for drive, sol, lat in [(0, 1, 18.4), (10, 1, 18.41), (20, -1, 18.42)]:
        props = properties(77.4, lat)
        rows.append({"frame": "ROVER", "site": 3, "drive": drive, "sol": sol, "longitude": 77.4, "planetocentric_latitude": lat, "planetodetic_latitude": -9999, "northing": props["northing"], "easting": props["easting"]})
    rows.append({**rows[0], "frame": "SITE"})
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=names)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode(), label.encode()


def test_places_uses_labelled_planetocentric_field_and_retains_multiple_same_sol_controls():
    table, label = places_fixture()
    controls, identity, warnings = parse_places(table, label)
    assert set(controls) == {"3_0", "3_10"}
    assert controls["3_0"].latitude == 18.4  # Not the deliberately invalid -detic value.
    assert identity.endswith("::synthetic-test")
    assert warnings
    for invalid in [label.replace(b"DEGREE", b"METER"), label.replace(b"<records>4", b"<records>5"), b'<!DOCTYPE test [<!ENTITY x "bad">]>' + label]:
        with pytest.raises(ValueError):
            parse_places(table, invalid)


def test_snapshot_integrity_allowlist_stable_version_and_offline_reuse(tmp_path, monkeypatch):
    content = {key: b"synthetic" for key in snapshots.URLS}
    content["config"] = json.dumps({"layers": [{"url": url} for url in SOURCE_URLS.values()]}).encode()

    class Response:
        def __init__(self, url):
            self.url = url
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            key = next(key for key, url in snapshots.URLS.items() if url == self.url)
            return content[key][:size]

    monkeypatch.setattr(snapshots, "urlopen", lambda request, **kwargs: Response(request.full_url))
    path = snapshots.fetch_snapshots(tmp_path)
    original = path.read_bytes()
    assert snapshots.fetch_snapshots(tmp_path) == path
    assert path.read_bytes() == original  # Retrieval time is not silently replaced.
    manifest, loaded = snapshots.load_snapshots(path)
    assert loaded == content
    target = path.parent / manifest.snapshots["samples"].file_name
    target.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        snapshots.load_snapshots(path)
    target.write_bytes(content["samples"])
    data = json.loads(original)
    data["snapshots"]["samples"]["source_url"] = "https://untrusted.example/input.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="allowlisted"):
        snapshots.load_snapshots(path)


def test_network_failure_does_not_publish_partial_cache(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("offline")
    monkeypatch.setattr(snapshots, "urlopen", fail)
    with pytest.raises(OSError):
        snapshots.fetch_snapshots(tmp_path)
    assert not list(tmp_path.rglob("manifest.json"))
