"""Offline PLACES exposure joins. SCLK is decimal seconds, never Earth time.

See PLACES SIS sections 2.2 and 5.6. Intervals are closed; boundary overlaps
remain ambiguous. An observation does not establish traversability or safety.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime
import csv
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Literal
from urllib.request import Request, urlopen

from pydantic import Field, HttpUrl, field_validator

from app.contracts.api import ContractModel, MarsCoordinate
from app.evidence.models import EvidenceDataset, EvidenceRoi
from app.evidence.places import NS, PDS_BASE

RMC = ('site', 'drive', 'pose', 'arm', 'sha', 'drill', 'rsm', 'hga', 'bitcar', 'seal')
OBS_FIELDS = ['sclk', 'inst', 'duration']
CLOCK_FIELDS = ['frame', *RMC, 'min_sclk', 'max_sclk', 'min_approx_sclk', 'max_approx_sclk']
ANCILLARY_FILES = ['observations.csv', 'observations.csv.xml', 'sclk_table.csv', 'sclk_table.csv.xml']


def acquire_ancillary(directory: Path):
    """Explicit CLI action; fixed URLs, bounded files, receipts checked offline."""
    from datetime import timezone
    directory.mkdir(parents=True, exist_ok=True)
    for name in ANCILLARY_FILES:
        url = PDS_BASE + 'data_ancillary/' + name
        with urlopen(Request(url, headers={'User-Agent': 'A-STELLAR-research/0.1'}), timeout=30) as response:
            if response.url != url:
                raise ValueError('Unexpected PLACES redirect.')
            content = response.read(25_000_001)
        if not content or len(content) > 25_000_000:
            raise ValueError('Ancillary table is empty or exceeds the size limit.')
        path = directory / name
        path.write_bytes(content)
        path.with_suffix(path.suffix + '.source.json').write_text(json.dumps({
            'source_url': url, 'resolved_url': url, 'bytes': len(content),
            'sha256': hashlib.sha256(content).hexdigest(), 'downloaded_at': datetime.now(timezone.utc).isoformat()
        }, indent=2), encoding='utf-8')


def clock(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Invalid spacecraft clock/duration.') from error
    if not result.is_finite() or result < 0:
        raise ValueError('Spacecraft clock/duration must be finite and nonnegative.')
    return result


def labeled_rows(table: bytes, label: bytes, name: str, fields: list[str]):
    if b'<!DOCTYPE' in label.upper() or b'<!ENTITY' in label.upper():
        raise ValueError('External XML entities are not supported.')
    root = ET.fromstring(label)
    identity = root.findtext('pds:Identification_Area/pds:logical_identifier', namespaces=NS)
    version = root.findtext('pds:Identification_Area/pds:version_id', namespaces=NS)
    if identity != f'urn:nasa:pds:mars2020_rover_places:data_ancillary:{name}' or not version:
        raise ValueError('Unexpected ancillary product identity/version.')
    names = [field.findtext('pds:name', namespaces=NS) for field in root.findall('.//pds:Record_Delimited/pds:Field_Delimited', NS)]
    reader = csv.DictReader(io.StringIO(table.decode('utf-8-sig')))
    if names != fields or reader.fieldnames != fields:
        raise ValueError('Ancillary fields disagree with the PDS label or supported schema.')
    rows = list(reader)
    count = root.findtext('.//pds:Table_Delimited/pds:records', namespaces=NS)
    if count is None or not count.isdigit() or len(rows) != int(count) or any(None in row or None in row.values() for row in rows):
        raise ValueError('Ancillary row count/shape differs from its label.')
    return rows, f'{identity}::{version}'


@dataclass(frozen=True)
class Exposure:
    sclk: Decimal
    instrument: str
    duration: Decimal


@dataclass(frozen=True)
class ClockRange:
    start: Decimal
    end: Decimal
    approx_start: Decimal
    approx_end: Decimal
    rmc: tuple[int, ...]
    frame: str = 'ROVER'
    exact: bool = True

    @property
    def position(self):
        return f'{self.rmc[0]}_{self.rmc[1]}' if self.rmc[0] >= 1 and self.rmc[1] >= 0 else None

    @property
    def static(self):
        return self.frame == 'ROVER' and self.rmc[0] >= 1 and all(v >= 0 and v % 2 == 0 for v in self.rmc[1:])


def parse_ancillary(observations: bytes, observations_label: bytes, clocks: bytes, clocks_label: bytes):
    obs_rows, obs_id = labeled_rows(observations, observations_label, 'observations.csv', OBS_FIELDS)
    clock_rows, clock_id = labeled_rows(clocks, clocks_label, 'sclk_table.csv', CLOCK_FIELDS)
    if obs_id.rsplit('::', 1)[1] != clock_id.rsplit('::', 1)[1]:
        raise ValueError('Ancillary release versions differ.')
    exposures = set()
    for row in obs_rows:
        if not row['inst'].strip():
            raise ValueError('Missing observation instrument.')
        exposures.add(Exposure(clock(row['sclk']), row['inst'], clock(row['duration'])))
    intervals = set()
    for row in clock_rows:
        rmc = tuple(int(row[key]) for key in RMC)
        if any(v < -1 for v in rmc) or row['frame'] not in ('ROVER', 'INMOTION'):
            raise ValueError('Invalid RMC/frame.')
        lo, hi = row['min_sclk'], row['max_sclk']
        if bool(lo) != bool(hi):
            raise ValueError('Incomplete exact clock interval.')
        a, b = clock(row['min_approx_sclk']), clock(row['max_approx_sclk'])
        start, end = (clock(lo), clock(hi)) if lo else (a, b)
        if start > end or a > b or (lo and not a <= start <= end <= b):
            raise ValueError('Invalid clock interval bounds.')
        intervals.add(ClockRange(start, end, a, b, rmc, row['frame'], bool(lo)))
    return sorted(exposures, key=lambda o: (o.sclk, o.instrument, o.duration)), list(intervals), [obs_id, clock_id], len(obs_rows)-len(exposures)


class ObservationMatch(ContractModel):
    sclk: str
    instrument: str
    duration_s: str
    status: Literal['exact', 'approximate', 'ambiguous', 'moving', 'unknown_rmc', 'missing_position', 'unmatched']
    candidates: list[str]
    stop_id: str | None = None


def join_observations(exposures: list[Exposure], intervals: list[ClockRange], stop_ids: set[str]) -> list[ObservationMatch]:
    """Sweep by exposure start; retain intervals starting during the exposure.

    Partial mechanism RMCs may corroborate a position but cannot certify a
    static exposure. Approximate ranges never upgrade an exact-range gap.
    """
    ordered = sorted(intervals, key=lambda r: (r.approx_start, r.approx_end, r.rmc))
    starts = [r.approx_start for r in ordered]
    active: dict[int, ClockRange] = {}
    cursor = 0
    matches = []
    for obs in sorted(exposures, key=lambda o: (o.sclk, o.instrument, o.duration)):
        end = obs.sclk + obs.duration
        while cursor < len(ordered) and ordered[cursor].approx_start <= obs.sclk:
            active[cursor] = ordered[cursor]
            cursor += 1
        active = {i: r for i, r in active.items() if r.approx_end >= obs.sclk}
        overlapping = list(active.values()) + ordered[cursor:bisect_right(starts, end)]
        exact = [r for r in overlapping if r.exact and r.start <= end and r.end >= obs.sclk]
        positions = sorted({r.position for r in exact if r.position is not None})
        certain = [r for r in exact if r.static and r.start <= obs.sclk and end <= r.end]
        moving = any(r.frame == 'INMOTION' or any(v >= 0 and v % 2 for v in r.rmc[1:]) for r in exact)
        status, stop = 'unmatched', None
        if len(positions) > 1:
            status = 'ambiguous'
        elif moving:
            status = 'moving'
        elif certain and any(r.position is None for r in exact):
            status = 'ambiguous'
        elif certain:
            position = certain[0].position
            status = 'exact' if position in stop_ids else 'missing_position'
            stop = position if status == 'exact' else None
        elif exact:
            status = 'unknown_rmc'
        elif overlapping:
            status = 'approximate'
            positions = sorted({r.position for r in overlapping if r.position is not None})
        matches.append(ObservationMatch(sclk=str(obs.sclk), instrument=obs.instrument, duration_s=str(obs.duration),
                                        status=status, candidates=positions, stop_id=stop))
    return matches


class ImageReference(ContractModel):
    lidvid: str = Field(pattern=r'^urn:nasa:pds:mars2020_navcam_ops_raw:data:[a-z0-9_]+::[0-9]+\.[0-9]+$')
    sclk: str
    instrument: Literal['NAVCAM_LEFT', 'NAVCAM_RIGHT']
    stop_id: str = Field(pattern=r'^[1-9][0-9]*_[0-9]+$')
    sol: int = Field(ge=0)
    label_url: HttpUrl
    browse_url: HttpUrl
    label_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    browse_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    verified_at: datetime

    @field_validator('label_url', 'browse_url')
    @classmethod
    def official_resolver(cls, value):
        if not str(value).startswith('https://pds-imaging.jpl.nasa.gov/api/data/atlas:pds4:mars_2020:perseverance:/mars2020_navcam_ops_raw/') or value.query or value.fragment:
            raise ValueError('Image links must use the official stable Navcam resolver.')
        return value

    @field_validator('sclk')
    @classmethod
    def valid_clock(cls, value):
        clock(value)
        return value


class ObservationReport(ContractModel):
    processing_version: Literal['a6-observations-v1'] = 'a6-observations-v1'
    evidence_version: str
    evidence_provenance_ref: str
    roi: EvidenceRoi
    stop_coordinates: dict[str, MarsCoordinate]
    dataset_ids: list[str]
    input_hashes: dict[str, str]
    observation_time_end: datetime | None = None
    image_manifest_ref: str | None = None
    matches: list[ObservationMatch]
    images: list[ImageReference]
    duplicates_removed: int = Field(ge=0)
    warnings: list[str]


def checked_input(path: Path, expected_url: str) -> bytes:
    content = path.read_bytes()
    receipt = json.loads(path.with_suffix(path.suffix + '.source.json').read_text())
    if (receipt['source_url'] != expected_url or receipt['resolved_url'] != expected_url or
            receipt['sha256'] != hashlib.sha256(content).hexdigest() or receipt['bytes'] != len(content)):
        raise ValueError(f'Invalid source receipt for {path.name}.')
    return content


def prepare_observations(dataset: EvidenceDataset, directory: Path, images: list[ImageReference] | None = None):
    names = ANCILLARY_FILES
    content = [checked_input(directory / name, PDS_BASE + 'data_ancillary/' + name) for name in names]
    exposures, ranges, ids, duplicates = parse_ancillary(*content)
    matches = join_observations(exposures, ranges, {s.record_id for s in dataset.stops})
    keys = {(clock(m.sclk), m.instrument, m.stop_id) for m in matches if m.status == 'exact'}
    uncertain = {(clock(m.sclk), m.instrument) for m in matches if m.status != 'exact'}
    accepted = [image for image in images or [] if (clock(image.sclk), image.instrument, image.stop_id) in keys
                and (clock(image.sclk), image.instrument) not in uncertain]
    time_end = ET.fromstring(content[1]).findtext('.//pds:Time_Coordinates/pds:stop_date_time', namespaces=NS)
    return ObservationReport(evidence_version=dataset.dataset_version, evidence_provenance_ref=dataset.provenance_ref,
                             roi=dataset.roi, stop_coordinates={s.record_id: MarsCoordinate(longitude=s.longitude, latitude=s.latitude) for s in dataset.stops},
                             dataset_ids=ids, input_hashes={n: hashlib.sha256(c).hexdigest() for n,c in zip(names,content)},
                             observation_time_end=time_end,
                             matches=matches, images=accepted, duplicates_removed=duplicates,
                             warnings=['Observation localization requires the entire exposure inside a known static exact RMC interval; other matches stay unlocalized.',
                                       'Only a bounded Navcam archive sample is verified; image availability can change. Mastcam-Z clock differences are not approximated.',
                                       'Rover observations are historical evidence, not proof of astronaut safety or DEM/map registration.'])
