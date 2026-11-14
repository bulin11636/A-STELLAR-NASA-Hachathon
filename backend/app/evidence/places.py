import csv
import io
import xml.etree.ElementTree as ET

from app.contracts.api import MarsCoordinate
from app.evidence.coordinates import from_places_projected

PDS_BASE = "https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/"
PDS_TABLE = PDS_BASE + "data_localizations/best_tactical.csv"
PDS_LABEL = PDS_TABLE + ".xml"
PDS_SIS = PDS_BASE + "document/Mars2020_Rover_PLACES_PDS_SIS.pdf"
NS = {"pds": "http://pds.nasa.gov/pds4/pds/v1"}


def parse_places(table: bytes, label: bytes) -> tuple[dict[str, MarsCoordinate], str, list[str]]:
    """Read label-described planetocentric fields; never substitute -detic Y.

    Used as an independent coordinate control source, not as a continuous path.
    Preserve distinct RMCs on the same sol. Skip unknown sol/site-frame rows.
    """
    if b"<!DOCTYPE" in label.upper() or b"<!ENTITY" in label.upper():
        raise ValueError("External XML entities are not supported.")
    try:
        root = ET.fromstring(label)
    except ET.ParseError as error:
        raise ValueError("Invalid PDS label XML.") from error
    identity = root.findtext("pds:Identification_Area/pds:logical_identifier", namespaces=NS)
    version = root.findtext("pds:Identification_Area/pds:version_id", namespaces=NS)
    if identity != "urn:nasa:pds:mars2020_rover_places:data_localizations:best_tactical.csv" or not version:
        raise ValueError("Unexpected PDS product identity/version.")
    fields = root.findall(".//pds:Record_Delimited/pds:Field_Delimited", NS)
    names = [field.findtext("pds:name", namespaces=NS) for field in fields]
    if not {"frame", "site", "drive", "sol", "planetocentric_latitude", "longitude", "northing", "easting"}.issubset(names):
        raise ValueError("PDS table is missing required localization fields.")
    for required, unit in [("planetocentric_latitude", "DEGREE"), ("longitude", "DEGREE"), ("northing", "METER"), ("easting", "METER")]:
        field = next((field for field in fields if field.findtext("pds:name", namespaces=NS) == required), None)
        if field is None or field.findtext("pds:unit", namespaces=NS) != unit:
            raise ValueError("Missing or incompatible PDS coordinate units.")
    reader = csv.DictReader(io.StringIO(table.decode("utf-8-sig")))
    if reader.fieldnames != names:
        raise ValueError("CSV fields disagree with the PDS label.")
    rows = list(reader)
    count = root.findtext(".//pds:Table_Delimited/pds:records", namespaces=NS)
    if count is None or not count.isdigit() or len(rows) != int(count):
        raise ValueError("PDS table row count differs from its label.")
    controls = {}
    excluded = 0
    for row in rows:
        if row["frame"] != "ROVER":
            excluded += 1
            continue
        try:
            if int(row["sol"]) < 0:
                raise ValueError("Unknown sol.")
            site, drive = int(row["site"]), int(row["drive"])
            if site < 0 or drive < 0:
                raise ValueError("Unknown rover position.")
            point = MarsCoordinate(longitude=float(row["longitude"]), latitude=float(row["planetocentric_latitude"]))
            expected = from_places_projected(float(row["northing"]), float(row["easting"]))
            if abs(point.longitude - expected.longitude) > 2e-7 or abs(point.latitude - expected.latitude) > 2e-7:
                raise ValueError("PDS angular/projected coordinate mismatch.")
        except (ValueError, TypeError):
            excluded += 1
            continue
        key = f"{site}_{drive}"
        if key in controls and controls[key] != point:
            raise ValueError("Conflicting localization for the same site/drive; do not guess.")
        controls[key] = point
    if not controls:
        raise ValueError("No valid PDS coordinate controls.")
    return controls, f"{identity}::{version}", [f"PDS control rows excluded (SITE, unknown sol or invalid position): {excluded}."]
