"""Small synthetic geometry fixtures; live USGS data is tested separately offline."""
import asyncio
import hashlib
import json
import math
from pathlib import Path
import zipfile

import pytest
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, box, mapping

from app.contracts.api import MarsCoordinate
from app.contracts.workers import SciencePOI, SourceReference, WorkerContext
from app.agents.a4.geology import (
    ARCHIVE_URL, CRS_PROJ, GDB_MEMBER, GEOGRAPHIC_MEMBER, PRJ_MEMBER,
    GeologyCatalog, UnitPolygon, UnitReference, build_report, extract_vectors,
    read_catalog, verified_mars_crs,
)
from app.evidence.models import EvidenceDataset, PREVIEW_ROI
from app.agents.a4 import ScienceEvidenceWorker
from app.evidence.adapters import GEOLOGY_NOT_LOADED

CRS_MARS = CRS.from_proj4(CRS_PROJ)
FORWARD = Transformer.from_crs(CRS_MARS.geodetic_crs, CRS_MARS, always_xy=True)
INVERSE = Transformer.from_crs(CRS_MARS, CRS_MARS.geodetic_crs, always_xy=True)
ORIGIN = FORWARD.transform(77.5, 18.4446)


def native_box(x1, y1, x2, y2):
    return box(ORIGIN[0] + x1, ORIGIN[1] + y1, ORIGIN[0] + x2, ORIGIN[1] + y2)


def poi(x=0, y=0, identifier="synthetic-poi"):
    lon, lat = INVERSE.transform(ORIGIN[0] + x, ORIGIN[1] + y)
    return SciencePOI(id=identifier, longitude=lon, latitude=lat, category="synthetic", rationale="Synthetic test only",
                      source=SourceReference(dataset_id="synthetic", source_url="https://example.org/synthetic", mission="synthetic", instrument="synthetic"))


def polygon(geometry, fid="1", code="A", inconsistent=False):
    return UnitPolygon(UnitReference(feature_id=fid, unit_code=code, symbol=code, name=f"Synthetic {code}", inconsistent_source_code=inconsistent), geometry)


def catalog(polygons=None, coverage=None, **kwargs):
    return GeologyCatalog(polygons=polygons or [polygon(native_box(-1000, -1000, 1000, 1000))],
                          coverage=coverage if coverage is not None else native_box(-2000, -2000, 2000, 2000),
                          crs=CRS_MARS, version="synthetic-only-v1", provenance_ref="synthetic-source.json", **kwargs)


def test_mars_projection_matches_independent_spherical_transverse_mercator_formula():
    lon, lat = 77.4509, 18.4446
    phi = math.radians(lat)
    delta = math.radians(lon - 77.5)
    radius = 3396190
    expected_x = radius * math.atanh(math.cos(phi) * math.sin(delta))
    expected_y = radius * math.atan2(math.tan(phi), math.cos(delta))
    x, y = FORWARD.transform(lon, lat)
    assert x == pytest.approx(expected_x, abs=1e-6)
    assert y == pytest.approx(expected_y, abs=1e-6)
    assert INVERSE.transform(x, y) == pytest.approx((lon, lat), abs=1e-10)
    assert verified_mars_crs(CRS_MARS).is_projected


@pytest.mark.parametrize("wrong", [
    "EPSG:3857", "EPSG:4326", CRS_PROJ.replace("77.5", "77.0"),
    CRS_PROJ.replace("+R=3396190", "+a=3396190 +b=3376200"),
    CRS_PROJ.replace("+units=m", "+units=km"), CRS_PROJ.replace("+k=1", "+k=0.9996"),
    CRS_PROJ.replace("+x_0=0", "+x_0=10"),
])
def test_wrong_planet_projection_scale_or_units_fail_closed(wrong):
    with pytest.raises(ValueError):
        verified_mars_crs(wrong)


def test_single_nominal_match_does_not_invent_priority_or_claim_registration():
    point = poi()
    result = catalog().associate(point, PREVIEW_ROI)
    assert result.status == "nominal_match"
    assert [unit.symbol for unit in result.nominal_units] == ["A"]
    assert result.nearest_boundary_m == pytest.approx(1000, abs=.001)
    assert point.priority is None
    assert any("not validated" in reason for reason in result.reasons)


def test_near_unit_boundary_and_shared_boundary_preserve_both_candidates():
    source = catalog([polygon(native_box(-1000, -1000, 0, 1000)), polygon(native_box(0, -1000, 1000, 1000), "2", "B")])
    nearby = source.associate(poi(-100), PREVIEW_ROI)
    assert nearby.status == "ambiguous"
    assert len(nearby.nominal_units) == 1
    assert len(nearby.possible_units) == 2
    shared = source.associate(poi(), PREVIEW_ROI)
    assert shared.status == "ambiguous"
    assert len(shared.possible_units) == 2


def test_actual_overlap_is_not_resolved_by_order():
    first = polygon(native_box(-1000, -1000, 1000, 1000))
    second = polygon(native_box(-500, -500, 500, 500), "2", "B")
    one = catalog([first, second]).associate(poi(), PREVIEW_ROI)
    two = catalog([second, first]).associate(poi(), PREVIEW_ROI)
    assert one == two
    assert one.status == "ambiguous" and len(one.nominal_units) == 2


def test_holes_no_coverage_and_outside_roi_remain_explicit():
    outer = list(native_box(-1000, -1000, 1000, 1000).exterior.coords)
    hole = list(native_box(-250, -250, 250, 250).exterior.coords)
    source = catalog([polygon(Polygon(outer, [hole]))])
    assert source.associate(poi(), PREVIEW_ROI).status == "unmapped"
    assert source.associate(poi(2500), PREVIEW_ROI).status == "outside_coverage"
    point = poi().model_copy(update={"longitude": 78.0})
    assert source.associate(point, PREVIEW_ROI).status == "outside_roi"
    at_edge = catalog(coverage=native_box(-150, -150, 150, 150)).associate(poi(), PREVIEW_ROI)
    assert at_edge.status == "ambiguous"


def test_unknown_invalid_polygon_bounds_and_source_label_conflicts_are_not_erased():
    unknown = catalog(rejected_bounds=[native_box(-50, -50, 50, 50)], rejected_ids=["bad"])
    assert unknown.associate(poi(), PREVIEW_ROI).status == "ambiguous"
    inconsistent = catalog([polygon(native_box(-1000, -1000, 1000, 1000), inconsistent=True)])
    assert inconsistent.associate(poi(), PREVIEW_ROI).status == "ambiguous"
    with pytest.raises(ValueError):
        catalog([polygon(Polygon([(0, 0), (1, 1), (0, 1), (1, 0)]))])


@pytest.mark.parametrize("offset", [0, 100, 199, float("nan"), float("inf"), 1001])
def test_offset_screen_cannot_suppress_the_documented_approximate_offset(offset):
    with pytest.raises(ValueError):
        catalog().associate(poi(), PREVIEW_ROI, offset)


def archive_fixture(tmp_path, extra=None):
    archive = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr(PRJ_MEMBER, CRS_MARS.to_wkt())
        target.writestr(GEOGRAPHIC_MEMBER, CRS_MARS.geodetic_crs.to_wkt())
        target.writestr(GDB_MEMBER + "synthetic.gdbtable", "SYNTHETIC ONLY")
        target.writestr(GDB_MEMBER + "stale.sr.lock", "locked")
        target.writestr("sim3464_JezeroNili_FINAL/Rasters/example.tif", "synthetic raster")
        if extra:
            target.writestr(extra, "bad path")
    receipt = {"source_url": ARCHIVE_URL, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "bytes": archive.stat().st_size, "downloaded_at": "2026-11-12T00:00:00Z"}
    archive.with_name(archive.name + ".source.json").write_text(json.dumps(receipt))
    return archive


def test_selective_extraction_integrity_and_no_unrelated_overwrite(tmp_path):
    archive = archive_fixture(tmp_path)
    gdb, prj, manifest = extract_vectors(archive, tmp_path / "output")
    assert gdb.is_dir() and prj.is_file()
    assert manifest["rasters_extracted"] is False
    assert not list((tmp_path / "output").rglob("*.tif"))
    assert not list((tmp_path / "output").rglob("*.lock"))
    assert extract_vectors(archive, tmp_path / "output")[0] == gdb
    (gdb / "synthetic.gdbtable").write_text("modified")
    with pytest.raises(ValueError, match="modified"):
        extract_vectors(archive, tmp_path / "output")
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(ValueError):
        extract_vectors(archive, tmp_path / "elsewhere")


def test_zip_traversal_is_rejected(tmp_path):
    archive = archive_fixture(tmp_path, GDB_MEMBER + "../../../../escape.txt")
    with pytest.raises(ValueError, match="Unsafe"):
        extract_vectors(archive, tmp_path / "output")
    assert not (tmp_path / "escape.txt").exists()


def evidence(points):
    return EvidenceDataset(dataset_version="synthetic-v1", roi=PREVIEW_ROI, stops=[], segments=[], pois=points,
                           dataset_ids=["synthetic"], warnings=[GEOLOGY_NOT_LOADED], provenance_ref="synthetic.json", artifact_ref="synthetic-vectors.json")


def test_a4_accepts_only_matching_report_and_keeps_the_existing_contract():
    dataset = evidence([poi()])
    report = build_report(catalog(), pois=dataset.pois, roi=dataset.roi, evidence_version=dataset.dataset_version,
                          evidence_provenance_ref=dataset.provenance_ref)
    context = WorkerContext(mission_id="test", region_id="jezero", roi_id=dataset.roi.roi_id, dataset_version=dataset.dataset_version)
    result = asyncio.run(ScienceEvidenceWorker(dataset, geology_report=report, geology_ref="synthetic-geology.json").run(context))
    assert result.geology_ref == "synthetic-geology.json"
    assert result.status == "partial" and result.data_kind == "observed"
    assert result.pois[0].priority is None and result.ranking_method is None
    assert GEOLOGY_NOT_LOADED not in result.warnings
    assert result.artifacts["geology_associations"] == result.geology_ref
    for wrong in [
        report.model_copy(update={"evidence_version": "stale"}),
        report.model_copy(update={"evidence_provenance_ref": "wrong-source.json"}),
        report.model_copy(update={"roi": dataset.roi.model_copy(update={"north": 18.6})}),
        report.model_copy(update={"associations": []}),
        report.model_copy(update={"associations": [report.associations[0].model_copy(update={"coordinate": MarsCoordinate(longitude=77.4, latitude=18.4)})]}),
    ]:
        rejected = asyncio.run(ScienceEvidenceWorker(dataset, geology_report=wrong, geology_ref="wrong.json").run(context))
        assert rejected.geology_ref is None
        assert GEOLOGY_NOT_LOADED in rejected.warnings
        assert rejected.pois == dataset.pois


def test_duplicate_poi_ids_require_resolution_before_matching():
    with pytest.raises(ValueError, match="unique"):
        build_report(catalog(), pois=[poi(), poi()], roi=PREVIEW_ROI, evidence_version="synthetic", evidence_provenance_ref="synthetic.json")


def test_fiona_loader_reads_native_units_rejects_invalid_geometry_and_detects_inconsistent_codes(tmp_path):
    import fiona

    path = tmp_path / "synthetic.gpkg"
    schema = {"geometry": "Polygon", "properties": {"unit": "str", "symbol": "str", "name": "str"}}
    rows = [polygon(native_box(-1000, -1000, 0, 1000)), polygon(native_box(0, -1000, 1000, 1000), "2", "B")]
    with fiona.open(path, "w", driver="GPKG", layer="GeoUnits_v1", crs_wkt=CRS_MARS.to_wkt(), schema=schema) as output:
        for item in rows:
            output.write({"geometry": mapping(item.geometry), "properties": {"unit": "same", "symbol": item.reference.symbol, "name": item.reference.name}})
        output.write({"geometry": mapping(Polygon([(0, 0), (1, 1), (0, 1), (1, 0)])), "properties": {"unit": "bad", "symbol": "bad", "name": "bad"}})
    with fiona.open(path, "w", driver="GPKG", layer="MapBoundary", crs_wkt=CRS_MARS.to_wkt(), schema={"geometry": "Polygon", "properties": {}}) as output:
        output.write({"geometry": mapping(native_box(-2000, -2000, 2000, 2000)), "properties": {}})
    prj = tmp_path / "synthetic.prj"
    prj.write_text(CRS_MARS.to_wkt())
    loaded = read_catalog(path, prj, version="synthetic", provenance_ref="synthetic-receipt.json")
    assert len(loaded.polygons) == 2
    assert len(loaded.rejected_ids) == 1
    assert all(item.reference.inconsistent_source_code for item in loaded.polygons)
