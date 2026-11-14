"""USGS SIM 3464 vector ingestion and nominal POI/unit association.

No basemap shift is invented. A configurable screening distance carries the
source readme's approximate 100–200 m offset; it is not an error bound.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
from typing import Annotated, Literal
import zipfile

from pydantic import Field
from pyproj import CRS, Transformer
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.strtree import STRtree

from app.contracts.api import ContractModel, MarsCoordinate, NonEmptyString
from app.contracts.workers import SciencePOI
from app.evidence.models import EvidenceRoi

SOURCE_DOI = "https://doi.org/10.3133/sim3464"
ARCHIVE_URL = "https://pubs.usgs.gov/sim/3464/sim3464_database.zip"
SOURCE_PREFIX = "sim3464_JezeroNili_FINAL/"
GDB_MEMBER = SOURCE_PREFIX + "Geodatabase/Nili.gdb/"
PRJ_MEMBER = SOURCE_PREFIX + "CoordinateSystems/MTM_clon77_5E.prj"
GEOGRAPHIC_MEMBER = SOURCE_PREFIX + "CoordinateSystems/Mars2000_Sphere.prj"
CRS_PROJ = "+proj=tmerc +lon_0=77.5 +lat_0=0 +k=1 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"
PROCESSING_VERSION = "sim3464-geology-v1"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_archive(archive: Path) -> dict:
    receipt = json.loads(archive.with_name(archive.name + ".source.json").read_text(encoding="utf-8"))
    if receipt.get("source_url") != ARCHIVE_URL or receipt.get("bytes") != archive.stat().st_size:
        raise ValueError("Geology archive receipt has the wrong source or file size.")
    if receipt.get("sha256") != file_hash(archive):
        raise ValueError("Geology archive SHA-256 does not match its acquisition receipt.")
    try:
        acquired = datetime.fromisoformat(receipt["downloaded_at"].replace("Z", "+00:00"))
        if acquired.tzinfo is None:
            raise ValueError("Download time must include a timezone.")
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError("Geology receipt needs a valid timezone-aware acquisition timestamp.") from error
    return receipt


def extract_vectors(archive: Path, output_root: Path) -> tuple[Path, Path, dict]:
    """Extract selected vectors/PRJs only; never overwrite unrelated files."""
    receipt = verify_archive(archive)
    target = (output_root / receipt["sha256"][:16]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(archive) as source:
        selected = [item for item in source.infolist() if
                    (item.filename.startswith(GDB_MEMBER) or item.filename in (PRJ_MEMBER, GEOGRAPHIC_MEMBER))
                    and not item.is_dir() and not item.filename.endswith(".lock")]
        if not selected or len(selected) > 4096 or sum(item.file_size for item in selected) > 128_000_000:
            raise ValueError("Unexpected geology vector archive size/layout.")
        if not {PRJ_MEMBER, GEOGRAPHIC_MEMBER}.issubset({item.filename for item in selected}):
            raise ValueError("The archive lacks the required source projection files.")
        for item in selected:
            parts = PurePosixPath(item.filename)
            if parts.is_absolute() or ".." in parts.parts or "\\" in item.filename or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Unsafe archive member.")
            destination = target.joinpath(*parts.parts).resolve()
            if not destination.is_relative_to(target):
                raise ValueError("Archive member escapes the extraction directory.")
            data = source.read(item)  # ZIP CRC is checked while reading.
            digest = hashlib.sha256(data).hexdigest()
            if destination.exists():
                if file_hash(destination) != digest:
                    raise ValueError("An extracted geology file was modified; refusing to replace it.")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as output:
                    output.write(data)
            extracted.append({"member": item.filename, "sha256": digest, "bytes": len(data)})
    manifest = {"source_doi": SOURCE_DOI, "archive": receipt, "processing_version": PROCESSING_VERSION,
                "extracted_files": extracted, "rasters_extracted": False,
                "stale_arcgis_lock_files_extracted": False}
    manifest_path = target / "vector-extraction-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target / GDB_MEMBER, target / PRJ_MEMBER, manifest


def verified_mars_crs(value: str | CRS) -> CRS:
    crs = CRS.from_user_input(value)
    parameters = {"Latitude of natural origin": 0, "Longitude of natural origin": 77.5,
                  "Scale factor at natural origin": 1, "False easting": 0, "False northing": 0}
    operation = crs.coordinate_operation
    actual = {parameter.name: parameter.value for parameter in operation.params} if operation else {}
    units_ok = operation is not None and all(math.isclose(
        parameter.unit_conversion_factor,
        math.pi / 180 if parameter.name in ("Latitude of natural origin", "Longitude of natural origin") else 1,
        abs_tol=1e-12, rel_tol=0,
    ) for parameter in operation.params)
    # PROJ treats a named Mars datum and an unnamed +R datum as distinct even
    # when mathematically identical. Check every supported projection parameter,
    # axes, prime meridian and sphere size, instead of guessing by a datum name.
    if (not crs.is_projected or operation is None or not units_ok or operation.method_name != "Transverse Mercator" or
            set(actual) != set(parameters) or any(not math.isclose(actual[key], expected, abs_tol=1e-10, rel_tol=0) for key, expected in parameters.items()) or
            not math.isclose(crs.ellipsoid.semi_major_metre, 3396190, abs_tol=1e-5, rel_tol=0) or
            not math.isclose(crs.ellipsoid.semi_minor_metre, 3396190, abs_tol=1e-5, rel_tol=0) or
            crs.prime_meridian.longitude != 0 or [axis.direction for axis in crs.axis_info] != ["east", "north"]):
        raise ValueError("Expected the verified spherical Mars TM projection, metres, central meridian 77.5 E.")
    if any(not math.isclose(axis.unit_conversion_factor, 1, abs_tol=1e-12) for axis in crs.axis_info):
        raise ValueError("Geology coordinates must be in metres.")
    return crs


class UnitReference(ContractModel):
    feature_id: NonEmptyString
    unit_code: NonEmptyString
    symbol: NonEmptyString
    name: NonEmptyString
    inconsistent_source_code: bool = False


class GeologyAssociation(ContractModel):
    poi_id: NonEmptyString
    coordinate: MarsCoordinate
    status: Literal["nominal_match", "ambiguous", "unmapped", "outside_coverage", "outside_roi"]
    nominal_units: list[UnitReference]
    possible_units: list[UnitReference]
    screening_offset_m: Annotated[float, Field(ge=200, le=1000, allow_inf_nan=False)]
    nearest_boundary_m: float | None = None
    reasons: list[str]


class GeologyReport(ContractModel):
    source_doi: Literal["https://doi.org/10.3133/sim3464"] = SOURCE_DOI
    geology_version: NonEmptyString
    evidence_version: NonEmptyString
    evidence_provenance_ref: NonEmptyString
    roi: EvidenceRoi
    source_layer: Literal["GeoUnits_v1"] = "GeoUnits_v1"
    source_crs_wkt: NonEmptyString
    screening_offset_m: Annotated[float, Field(ge=200, le=1000, allow_inf_nan=False)]
    associations: list[GeologyAssociation]
    accepted_polygons: int
    rejected_feature_ids: list[str]
    inconsistent_unit_codes: list[str]
    warnings: list[str]
    provenance_ref: NonEmptyString


@dataclass(frozen=True)
class UnitPolygon:
    reference: UnitReference
    geometry: BaseGeometry


class GeologyCatalog:
    def __init__(self, *, polygons: list[UnitPolygon], coverage: BaseGeometry, crs: str | CRS,
                 provenance_ref: str, version: str, rejected_bounds: list[BaseGeometry] | None = None,
                 rejected_ids: list[str] | None = None):
        if not provenance_ref.strip() or not version.strip():
            raise ValueError("Geology source version and provenance are required.")
        self.crs = verified_mars_crs(crs)
        if coverage.is_empty or not coverage.is_valid or coverage.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Invalid geology map coverage boundary.")
        if not polygons or len({item.reference.feature_id for item in polygons}) != len(polygons):
            raise ValueError("Geology features must have unique source IDs.")
        for item in polygons:
            if item.geometry.is_empty or not item.geometry.is_valid or item.geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("Invalid polygon passed to the geology catalog.")
        self.polygons = polygons
        self.coverage = coverage
        self.tree = STRtree([item.geometry for item in polygons])
        self.rejected_bounds = rejected_bounds or []
        if any(bounds.is_empty or not bounds.is_valid or not all(math.isfinite(value) for value in bounds.bounds) for bounds in self.rejected_bounds):
            raise ValueError("Rejected-feature uncertainty bounds must be valid and finite.")
        self.rejected_ids = rejected_ids or []
        self.provenance_ref = provenance_ref
        self.version = version
        self.to_native = Transformer.from_crs(self.crs.geodetic_crs, self.crs, always_xy=True)

    def associate(self, poi: SciencePOI, roi: EvidenceRoi, offset_m: float = 200) -> GeologyAssociation:
        if not math.isfinite(offset_m) or not 200 <= offset_m <= 1000:
            raise ValueError("Offset screening must retain at least the reported 200 m approximation.")
        coordinate = MarsCoordinate(longitude=poi.longitude, latitude=poi.latitude)
        base = dict(poi_id=poi.id, coordinate=coordinate, nominal_units=[], possible_units=[], screening_offset_m=offset_m)
        if not roi.contains(coordinate):
            return GeologyAssociation(**base, status="outside_roi", reasons=["POI is outside the selected evidence window."])
        x, y = self.to_native.transform(poi.longitude, poi.latitude, errcheck=True)
        point = Point(x, y)
        # Query a square and compute exact polygon distances, avoiding buffered
        # circle tessellation dropping candidates at the screening threshold.
        indices = self.tree.query(box(x - offset_m, y - offset_m, x + offset_m, y + offset_m))
        candidates = [self.polygons[int(index)] for index in indices
                      if self.polygons[int(index)].geometry.distance(point) <= offset_m]
        nominal = [item for item in candidates if item.geometry.covers(point)]
        reasons = []
        status = "nominal_match"
        class_key = lambda item: (item.reference.unit_code, item.reference.symbol, item.reference.name)
        if not self.coverage.covers(point):
            status = "outside_coverage"
            reasons.append("Nominal point lies outside the published map boundary.")
        elif not nominal:
            status = "unmapped"
            reasons.append("No accepted source polygon covers the nominal point; do not infer a unit.")
        else:
            if len(nominal) > 1 or len({class_key(item) for item in candidates}) > 1:
                status = "ambiguous"
                reasons.append("Multiple source polygons cover the point or different units lie within the offset screen.")
            if self.coverage.boundary.distance(point) <= offset_m:
                status = "ambiguous"
                reasons.append("Offset screen reaches the edge of mapped coverage.")
            if any(bounds.distance(point) <= offset_m for bounds in self.rejected_bounds):
                status = "ambiguous"
                reasons.append("Offset screen intersects conservative bounds of a rejected source feature.")
            if any(item.reference.inconsistent_source_code for item in candidates):
                status = "ambiguous"
                reasons.append("Source unit code has inconsistent names/symbols; original attributes are preserved.")
        if not reasons:
            reasons.append("Single nominal unit under the selected offset screen; this is not validated georegistration.")
        boundary_distance = min((item.geometry.boundary.distance(point) for item in nominal), default=None)
        return GeologyAssociation(
            poi_id=poi.id, coordinate=coordinate, status=status,
            nominal_units=sorted([item.reference for item in nominal], key=lambda unit: unit.feature_id),
            possible_units=sorted([item.reference for item in candidates], key=lambda unit: unit.feature_id),
            screening_offset_m=offset_m, nearest_boundary_m=boundary_distance, reasons=reasons,
        )


def read_catalog(gdb: Path, prj: Path, *, version: str, provenance_ref: str) -> GeologyCatalog:
    import fiona

    source_crs = verified_mars_crs(prj.read_text(encoding="utf-8"))
    polygons = []
    rejected_ids = []
    rejected_bounds = []
    with fiona.open(gdb, layer="GeoUnits_v1", mode="r") as source:
        crs = verified_mars_crs(source.crs_wkt)
        # Both CRS definitions passed the same complete numeric profile check.
        for feature in source:
            geometry = shape(feature.geometry) if feature.geometry else None
            props = feature.properties
            try:
                reference = UnitReference(feature_id=str(feature.id), unit_code=props["unit"], symbol=props["symbol"], name=props["name"])
                if geometry is None or geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                    raise ValueError("Invalid source geometry.")
                polygons.append(UnitPolygon(reference, geometry))
            except (ValueError, KeyError, TypeError):
                rejected_ids.append(str(feature.id))
                if geometry is not None and not geometry.is_empty and all(math.isfinite(value) for value in geometry.bounds):
                    rejected_bounds.append(box(*geometry.bounds))
                else:
                    raise ValueError("An unlocatable rejected geology feature prevents reliable coverage screening.")
    variants = defaultdict(set)
    for item in polygons:
        variants[item.reference.unit_code].add((item.reference.symbol, item.reference.name))
    conflicts = {code for code, values in variants.items() if len(values) > 1}
    polygons = [UnitPolygon(item.reference.model_copy(update={"inconsistent_source_code": item.reference.unit_code in conflicts}), item.geometry) for item in polygons]
    with fiona.open(gdb, layer="MapBoundary", mode="r") as boundary:
        verified_mars_crs(boundary.crs_wkt)
        areas = [shape(feature.geometry) for feature in boundary]
        if not areas or any(area.is_empty or not area.is_valid or area.geom_type not in ("Polygon", "MultiPolygon") for area in areas):
            raise ValueError("Invalid source map boundary.")
    return GeologyCatalog(polygons=polygons, coverage=unary_union(areas), crs=source_crs, provenance_ref=provenance_ref,
                          version=version, rejected_bounds=rejected_bounds, rejected_ids=rejected_ids)


def build_report(catalog: GeologyCatalog, *, pois: list[SciencePOI], roi: EvidenceRoi, evidence_version: str,
                 evidence_provenance_ref: str, offset_m: float = 200) -> GeologyReport:
    if len({poi.id for poi in pois}) != len(pois):
        raise ValueError("POI identifiers must be unique before geology matching.")
    return GeologyReport(
        geology_version=catalog.version, evidence_version=evidence_version, evidence_provenance_ref=evidence_provenance_ref, roi=roi,
        source_crs_wkt=catalog.crs.to_wkt(), screening_offset_m=offset_m,
        associations=[catalog.associate(poi, roi, offset_m) for poi in sorted(pois, key=lambda point: point.id)],
        accepted_polygons=len(catalog.polygons), rejected_feature_ids=catalog.rejected_ids,
        inconsistent_unit_codes=sorted({item.reference.unit_code for item in catalog.polygons if item.reference.inconsistent_source_code}),
        provenance_ref=catalog.provenance_ref, warnings=[
            "Source reports approximate random offsets of 100–200 m from the rover operations mosaic. No fixed shift is applied.",
            "The offset screen is a diagnostic scenario, not a statistical error bound or validated registration.",
            "Geology map scale is 1:75,000; classifications are regional context, not sampling priority or terrain safety.",
            "Invalid polygons are excluded without automatic repair; their bounds remain conservative uncertainty regions.",
            "Names, symbols and source unit-code inconsistencies are preserved rather than silently corrected.",
            "WMTS/wire/DEM alignment remains unverified. Public routing remains mock; priorities remain unranked.",
        ],
    )
