import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

REQUEST = json.loads((Path(__file__).resolve().parents[2] / "data/fixtures/route-request.json").read_text())


@pytest.fixture
def client():
    with TestClient(create_app(), raise_server_exceptions=False) as instance:
        yield instance


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]


def test_health_and_regions(client):
    assert client.get("/api/v1/health").json() == {
        "status": "ok", "service": "a-stellar-backend", "api_version": "v1",
    }
    response = client.get("/api/v1/regions")
    assert response.status_code == 200
    assert response.json() == {"regions": [{
        "id": "jezero", "name": "Jezero Crater",
        "coordinate_system": REQUEST["coordinate_system"],
        "routing_available": True, "routing_mode": "mock", "planning": None,
    }]}


@pytest.mark.parametrize("mode", ["shortest", "safest"])
def test_route_success_contract(client, mode):
    body = deepcopy(REQUEST)
    body["mode"] = mode
    response = client.post("/api/v1/routes/plan", json=body)
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"status", "route_id", "region_id", "coordinate_system", "mode", "source", "route", "metrics", "warnings"}
    assert result["status"] == "success"
    assert result["source"] == "mock"
    assert result["route_id"].startswith("demo-jezero-")
    assert result["region_id"] == body["region_id"]
    assert result["coordinate_system"] == body["coordinate_system"]
    assert result["mode"] == mode
    assert result["route"][0] == body["start"]
    assert result["route"][-1] == body["goal"]
    assert result["metrics"] == {"distance_m": None, "estimated_time_min": None, "risk_score": None}
    assert any("Demonstration" in warning for warning in result["warnings"])
    assert any("Coordinate convention not validated" in warning for warning in result["warnings"])
    for agent in ("A1", "A2", "A3", "A4", "A6"):
        assert any(agent in warning for warning in result["warnings"])
    assert client.post("/api/v1/routes/plan", json=body).json()["route_id"] != result["route_id"]


@pytest.mark.parametrize("field,value,status,code", [
    ("region_id", "gale", 404, "UNKNOWN_REGION"),
    ("coordinate_system", "EPSG:4326", 400, "UNSUPPORTED_COORDINATE_SYSTEM"),
    ("mode", "fastest", 422, "VALIDATION_ERROR"),
    ("region_id", 123, 422, "VALIDATION_ERROR"),
    ("coordinate_system", 123, 422, "VALIDATION_ERROR"),
])
def test_invalid_request_fields(client, field, value, status, code):
    body = {**REQUEST, field: value}
    assert_error(client.post("/api/v1/routes/plan", json=body), status, code)


@pytest.mark.parametrize("field", list(REQUEST))
def test_missing_required_fields(client, field):
    body = deepcopy(REQUEST)
    del body[field]
    assert_error(client.post("/api/v1/routes/plan", json=body), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("axis,value", [
    ("longitude", -1), ("longitude", 360), ("longitude", "77.42"),
    ("longitude", True), ("longitude", None), ("latitude", -91),
    ("latitude", 91), ("latitude", "18.44"), ("latitude", None),
])
@pytest.mark.parametrize("endpoint", ["start", "goal"])
def test_coordinate_validation(client, endpoint, axis, value):
    body = deepcopy(REQUEST)
    body[endpoint][axis] = value
    assert_error(client.post("/api/v1/routes/plan", json=body), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_is_standardized_without_serialization_failure(client, value):
    raw = json.dumps(REQUEST).replace("77.42", value)
    response = client.post("/api/v1/routes/plan", content=raw, headers={"Content-Type": "application/json"})
    assert_error(response, 422, "VALIDATION_ERROR")
    assert value not in response.text


def test_equal_points_malformed_json_and_unknown_endpoint(client):
    assert_error(client.post("/api/v1/routes/plan", json={**REQUEST, "goal": REQUEST["start"]}), 400, "INVALID_ROUTE")
    assert_error(client.post("/api/v1/routes/plan", content="{", headers={"Content-Type": "application/json"}), 422, "VALIDATION_ERROR")
    assert_error(client.get("/api/v1/missing"), 404, "NOT_FOUND")


def test_boundary_coordinates_and_integer_numbers_are_accepted(client):
    body = {**REQUEST, "start": {"longitude": 0, "latitude": -90}, "goal": {"longitude": 359.999, "latitude": 90}}
    assert client.post("/api/v1/routes/plan", json=body).status_code == 200


def test_internal_errors_do_not_leak_exception_or_credentials():
    class BrokenCoordinator:
        async def plan_mock_route(self, body):
            raise RuntimeError("secret-token-do-not-expose")

    with TestClient(create_app(BrokenCoordinator()), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/routes/plan", json=REQUEST)
    assert_error(response, 500, "INTERNAL_ERROR")
    assert "secret-token" not in response.text
    assert "Traceback" not in response.text


def test_openapi_and_documentation(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/routes/plan" in schema["paths"]
    error_schema = schema["paths"]["/api/v1/routes/plan"]["post"]["responses"]["422"]["content"]["application/json"]["schema"]
    assert error_schema["$ref"].endswith("ErrorEnvelope")
