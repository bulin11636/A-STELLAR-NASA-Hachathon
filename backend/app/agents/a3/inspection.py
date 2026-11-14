"""Narrow, offline inspection of MSL RAD RDR dosimetry, not a Jezero model."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from pydantic import Field

from app.contracts.api import ContractModel

RAD_BASE = 'https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/'
DATASET_ID = 'MSL-M-RAD-3-RDR-V1.0'
PRODUCT = 'RAD_RDR_2012_220_02_25_0001_V00'
PRODUCT_DIR = 'DATA/SOL_00000_00089/'
SIS_URL = RAD_BASE + 'DOCUMENT/RAD_RDR_SIS.PDF'
MAX_BYTES = 20_000_000


def verified_file(path: Path, expected_url: str) -> bytes:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Radiation input exceeds size limit.')
    data = path.read_bytes()
    receipt = json.loads(path.with_name(path.name + '.source.json').read_text())
    if (receipt['source_url'] != expected_url or receipt['resolved_url'] != expected_url or
            receipt['bytes'] != len(data) or receipt['sha256'] != hashlib.sha256(data).hexdigest()):
        raise ValueError(f'Invalid source receipt for {path.name}.')
    return data


def assignments(text: str) -> dict[str, str]:
    """Only scalar lines in a known subsection; no executable PDS expressions."""
    result = {}
    for key, value in re.findall(r'^\s*([A-Z_]+)\s*=\s*([^\r\n]+)', text, re.M):
        value = value.strip().strip('"').strip()
        if key in result:
            raise ValueError(f'Duplicate scalar field: {key}.')
        result[key] = value
    return result


def nonnegative(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Invalid dosimetry number.') from error
    if not number.is_finite() or number < 0:
        raise ValueError('Dosimetry value is missing, negative or nonfinite.')
    return number


class AbsorbedDoseObservation(ContractModel):
    observation_id: str
    observed_at: datetime | None
    qc: str | None
    detector_b_ugy_per_hour: float | None = Field(default=None, ge=0)
    detector_e_ugy_per_hour: float | None = Field(default=None, ge=0)
    baseline_eligible: bool
    exclusions: list[str]


class RadInspection(ContractModel):
    processing_version: str = 'a3-rdr-inspection-v1'
    dataset_id: str = DATASET_ID
    product_id: str
    start_time: datetime
    stop_time: datetime | None
    observations: list[AbsorbedDoseObservation]
    source_hashes: dict[str, str] = Field(default_factory=dict)
    source_urls: dict[str, str] = Field(default_factory=dict)
    warnings: list[str]


def parse_rdr(data: bytes, label: bytes) -> RadInspection:
    text, description = data.decode('ascii'), label.decode('ascii')
    top = assignments(description.split('/* For Observation', 1)[0])
    product_id = top.get('PRODUCT_ID', '')
    if (top.get('DATA_SET_ID') != DATASET_ID or top.get('INSTRUMENT_ID') != 'RAD' or
            top.get('INSTRUMENT_HOST_ID') != 'MSL' or top.get('TARGET_NAME') != 'MARS' or
            top.get('PDS_VERSION_ID') != 'PDS3' or top.get('RECORD_TYPE') != 'STREAM' or
            not re.fullmatch(r'RAD_RDR_\d{4}_\d{3}_\d{2}_\d{2}_\d{4}_V\d{2}', product_id)):
        raise ValueError('Unsupported RAD surface product identity.')
    record_count_matches = int(top['FILE_RECORDS']) == len(data.splitlines())
    start = datetime.strptime(top['START_TIME'], '%Y-%jT%H:%M:%S').replace(tzinfo=timezone.utc)
    stop = None if top.get('STOP_TIME') == 'UNK' else datetime.strptime(top['STOP_TIME'], '%Y-%jT%H:%M:%S').replace(tzinfo=timezone.utc)
    sections = {}
    headers = list(re.finditer(r'^\[([A-Z_0-9]+)(?::\s*(\d+))?\]\s*$', text, re.M))
    for index, header in enumerate(headers):
        kind, number = header.group(1), header.group(2)
        key = (kind, int(number) if number is not None else None)
        if key in sections:
            raise ValueError('Duplicate RAD section/observation ID.')
        end = headers[index+1].start() if index+1 < len(headers) else len(text)
        sections[key] = text[header.end():end].strip()
    file_header = assignments(sections[('FILE', None)])
    if file_header['START_TIME'] != top['START_TIME'].replace('T', ' ') or int(file_header['START_SOL']) != int(product_id.split('_')[-2]):
        raise ValueError('RAD file header and label disagree.')
    values = {}
    pointers = re.findall(r'\^OBS(\d+)_TOT_DOSE_([BE])_ELEMENT\s*=\s*\("([^"]+)",\s*(\d+)\s*<BYTES>\)', description)
    for number, detector, filename, offset_text in pointers:
        number_int = int(number)
        object_name = f'OBS{number}_TOT_DOSE_{detector}_ELEMENT'
        objects = re.findall(r'\bOBJECT\s*=\s*'+object_name+r'\s+(.*?)END_OBJECT\s*=\s*'+object_name+r'\b', description, re.S)
        if len(objects) != 1 or filename != product_id + '.TXT':
            raise ValueError('Missing/conflicting dose object or external pointer.')
        fields = assignments(objects[0])
        if fields.get('UNIT') != 'microGray / Hour' or fields.get('DATA_TYPE') != 'ASCII_REAL' or fields.get('START_BYTE') != '1':
            raise ValueError('Unsupported absorbed-dose unit/encoding.')
        offset, width = int(offset_text)-1, int(fields['BYTES'])
        if offset < 0 or not 0 < width <= 64 or offset+width > len(data):
            raise ValueError('Invalid RAD byte pointer.')
        scalar = data[offset:offset+width].decode('ascii').strip()
        section = sections.get((f'DOSIMETRY_TOTAL_DOSE_{detector}', number_int))
        if scalar != section:
            raise ValueError('Dose byte pointer and named section disagree.')
        if (number_int, detector) in values:
            raise ValueError('Duplicate RAD dose pointer.')
        values[number_int, detector] = scalar
    section_doses = {(n, kind[-1]) for kind,n in sections if kind in ('DOSIMETRY_TOTAL_DOSE_B', 'DOSIMETRY_TOTAL_DOSE_E')}
    if set(values) != section_doses:
        raise ValueError('RAD dose sections and label pointers disagree.')
    observations = []
    previous = None
    for kind, number in sections:
        if kind != 'OBSERVATION':
            continue
        fields = assignments(sections[kind,number])
        exclusions = []
        if not record_count_matches:
            exclusions.append('Product record count differs from label; inspection only, excluded from baseline use.')
        observed_at = None
        try:
            observed_at = datetime.strptime(fields['START_OBS_UTC'], '%Y-%j %H:%M:%S').replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            exclusions.append('Missing/invalid observation UTC.')
        if observed_at is not None:
            if observed_at < start or (stop is not None and observed_at > stop):
                exclusions.append('Observation outside labeled time range.')
            if previous is not None and observed_at <= previous:
                exclusions.append('Non-increasing observation time; not reordered or interpolated.')
            previous = observed_at
        qc = fields.get('QC')
        if qc != '00000000':
            exclusions.append('Quality flags are missing, malformed or nonzero; excluded from quiet-baseline use.')
        doses = {}
        for detector in ('B','E'):
            try:
                doses[detector] = float(nonnegative(values[number,detector]))
            except (KeyError, ValueError):
                doses[detector] = None
                exclusions.append(f'Missing/invalid detector {detector} absorbed-dose rate.')
        observations.append(AbsorbedDoseObservation(observation_id=f'{number:03}', observed_at=observed_at, qc=qc,
            detector_b_ugy_per_hour=doses['B'], detector_e_ugy_per_hour=doses['E'],
            baseline_eligible=not exclusions, exclusions=exclusions))
    if not observations or any(n not in {int(o.observation_id) for o in observations} for n,d in values):
        raise ValueError('Dose data without a matching RAD observation.')
    return RadInspection(product_id=product_id, start_time=start, stop_time=stop, observations=observations, warnings=(
        [f"Source record-count discrepancy: label {top['FILE_RECORDS']}, actual {len(data.splitlines())}; all observations excluded from baseline use."] if not record_count_matches else []) + [
        'MSL RAD observations are historical Gale Crater detector absorbed-dose rates in microGy/hour, not Jezero EVA dose equivalent.',
        'B and E are separate detector responses; they are not summed and no assumed Gy-to-Sv conversion is applied.',
        'RDR rover coordinates are documented placeholders; no radiation raster or spatial registration is inferred.',
        'Archive errata report timing/redundancy issues. Unknown stop time and exposure durations prevent continuous dose integration.',
        'QC=0 means no issue flagged, not independent calibration validation. A single-sol subset is not a representative mission model.'
    ])


def inspect_cached(root: Path) -> RadInspection:
    names = [PRODUCT_DIR+PRODUCT+'.TXT', PRODUCT_DIR+PRODUCT+'.LBL',
             'DOCUMENT/RAD_RDR_SIS.PDF', 'ERRATA.TXT', 'DOCUMENT/TIMING_ERRORS.TXT', 'CATALOG/RAD_INST.CAT', 'CATALOG/RAD_RDR_DS.CAT']
    contents = {name: verified_file(root/name, RAD_BASE+name) for name in names}
    report = parse_rdr(contents[names[0]], contents[names[1]])
    return report.model_copy(update={'source_hashes': {name:hashlib.sha256(data).hexdigest() for name,data in contents.items()},
                                     'source_urls': {name:RAD_BASE+name for name in names}})
