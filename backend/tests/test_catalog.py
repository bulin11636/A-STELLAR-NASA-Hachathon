import pytest
from pydantic import ValidationError

from app.contracts.api import COORDINATE_SYSTEM, PlanRouteResponse, RouteMetrics
from app.contracts.workers import ArtifactMetadata, SciencePOI
from app.services.data_catalog import ArtifactCatalog


def metadata():
    # Synthetic metadata only; no real NASA product is implied.
    return {
        "artifact_id": "synthetic-demo-v1",
        "source": {"dataset_id": "synthetic-test-fixture", "source_url": "https://example.org/synthetic-fixture", "mission": "synthetic", "instrument": "synthetic"},
        "acquisition_time": None, "downloaded_at": "2026-11-09T00:00:00Z",
        "bounding_region": [{"longitude": 77, "latitude": 18}, {"longitude": 78, "latitude": 19}],
        "coordinate_system": COORDINATE_SYSTEM, "projection": "synthetic-local-metric",
        "grid_transform": [0, 1, 0, 0, 0, -1], "resolution_m": 1,
        "nodata_value": None, "coverage_ref": None, "unknown_mask_ref": None,
        "resampling": "none", "processing_version": "synthetic-v1",
        "uncertainties": ["Synthetic test data; not a Jezero measurement."],
    }


def test_artifact_metadata_registration_is_versioned_and_does_not_imply_data_availability():
    catalog = ArtifactCatalog()
    entry = ArtifactMetadata.model_validate(metadata())
    catalog.register(entry)
    assert catalog.get("absent") is None
    loaded = catalog.get(entry.artifact_id)
    assert loaded == entry
    loaded.uncertainties.append("Changed copy")
    assert catalog.get(entry.artifact_id).uncertainties == entry.uncertainties
    with pytest.raises(ValueError):
        catalog.register(entry)


def test_missing_provenance_invalid_units_and_unknown_coordinates_are_rejected():
    for change in ({"source": {}}, {"resolution_m": 0}, {"coordinate_system": "EPSG:4326"}, {"uncertainties": []}):
        with pytest.raises(ValidationError):
            ArtifactMetadata.model_validate({**metadata(), **change})


def test_science_priority_requires_method_even_when_provenance_is_present():
    poi = {"id": "synthetic-only", "longitude": 77, "latitude": 18, "category": "synthetic", "rationale": "Test fixture", "source": metadata()["source"]}
    assert SciencePOI.model_validate(poi).priority is None
    with pytest.raises(ValidationError):
        SciencePOI.model_validate({**poi, "priority": .5})


def test_mock_route_cannot_silently_acquire_metrics_or_lose_warnings():
    body = {
        "route_id": "test", "mode": "safest", "source": "mock",
        "route": [{"longitude": 77, "latitude": 18}, {"longitude": 78, "latitude": 19}],
        "metrics": RouteMetrics(), "warnings": ["MOCK only"],
    }
    assert PlanRouteResponse(**body).source == "mock"
    with pytest.raises(ValidationError):
        PlanRouteResponse(**{**body, "metrics": RouteMetrics(distance_m=0)})
    with pytest.raises(ValidationError):
        PlanRouteResponse(**{**body, "warnings": []})
