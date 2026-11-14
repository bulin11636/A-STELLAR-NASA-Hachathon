"""Bounded official Atlas Navcam acquisition; no network in worker requests."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

from app.agents.a6.observations import ImageReference, NS, clock

ATLAS = 'https://pds-imaging.jpl.nasa.gov/api'
SEARCH = ATLAS + '/search/atlas/_search'
BUNDLE = 'mars2020_navcam_ops_raw'
URI_PREFIX = f'atlas:pds4:mars_2020:perseverance:/{BUNDLE}/'
MAX_BYTES = 8_000_000


def allowed(url):
    parts = urlsplit(url)
    return (parts.scheme == 'https' and parts.hostname in ('pds-imaging.jpl.nasa.gov', 'd1ejlg980osaur.cloudfront.net')
            and parts.port in (None, 443) and not parts.username and not parts.password and not parts.query and not parts.fragment)


class ArchiveRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise ValueError('Unreviewed archive redirect.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, body=None):
    if not allowed(url):
        raise ValueError('Unreviewed archive URL.')
    request = Request(url, data=body, headers={'User-Agent': 'A-STELLAR-research/0.1', 'Content-Type': 'application/json'})
    with build_opener(ArchiveRedirects()).open(request, timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES or not allowed(response.url):
            raise ValueError('Invalid archive response size/redirect.')
        return data


def reference_url(uri: str, extension: str):
    if (not uri.startswith(URI_PREFIX) or not uri.endswith(extension) or
            any(part in ('.', '..') for part in uri[len(URI_PREFIX):].split('/')) or
            any(c in uri for c in ('?', '#', '%', '\\'))):
        raise ValueError('Unexpected archive file reference.')
    return ATLAS + '/data/' + uri


def validate_image(source: dict, label: bytes, browse: bytes, verified_at: str) -> ImageReference:
    if b'<!DOCTYPE' in label.upper() or b'<!ENTITY' in label.upper():
        raise ValueError('External XML entities are not supported.')
    if not browse.startswith(b'\x89PNG\r\n\x1a\n') or len(browse) < 33 or browse[12:16] != b'IHDR':
        raise ValueError('Browse response is not a PNG image.')
    root = ET.fromstring(label)
    lid = root.findtext('pds:Identification_Area/pds:logical_identifier', namespaces=NS)
    version = root.findtext('pds:Identification_Area/pds:version_id', namespaces=NS)
    archive = source['gather']['pds_archive']
    gathered = source['gather']
    def unique(name):
        values = {e.text for e in root.iter() if e.tag.rsplit('}', 1)[-1] == name}
        if len(values) != 1:
            raise ValueError(f'Missing/conflicting image {name}.')
        return next(iter(values))
    sclk, instrument, sol = unique('spacecraft_clock_start'), unique('ops_instrument_key'), int(unique('sol_number'))
    counters = {}
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1] != 'Motion_Counter_Index':
            continue
        entries = {child.tag.rsplit('}', 1)[-1]: child.text for child in element}
        key, value = entries['index_id'], int(entries['index_value_number'])
        if key in counters and counters[key] != value:
            raise ValueError('Conflicting label RMCs.')
        counters[key] = value
    site, drive = counters['SITE'], counters['DRIVE']
    indexed = gathered['landed_missions']
    if (source['bundle_id'] != BUNDLE or lid != archive['product_id'] or not version or
            source['pds4_label']['vid'] != version or gathered['common']['instrument'] != [instrument] or
            clock(sclk) != clock(gathered['time']['spacecraft_clock_start_count']) or
            (site, drive, sol) != (indexed['rmc_site'], indexed['rmc_drive'], indexed['planet_day_number']) or
            site < 1 or drive < 0 or drive % 2):
        raise ValueError('Image label and archive index disagree.')
    return ImageReference(lidvid=f'{lid}::{version}', sclk=str(clock(sclk)), instrument=instrument,
                          stop_id=f'{site}_{drive}', sol=sol,
                          label_url=reference_url(archive['related']['label']['uri'], '.xml'),
                          browse_url=reference_url(archive['related']['browse']['uri'], '.png'),
                          label_sha256=hashlib.sha256(label).hexdigest(), browse_sha256=hashlib.sha256(browse).hexdigest(),
                          verified_at=verified_at)


def acquire_images(directory: Path, site: int = 3, drive: int = 110, limit: int = 8):
    if not 1 <= limit <= 32 or site < 1 or drive < 0 or drive % 2:
        raise ValueError('Select a static site/drive and between 1 and 32 products.')
    query = {'size': limit, 'sort': [{'uri': 'asc'}], 'query': {'bool': {'filter': [
        {'term': {'bundle_id': BUNDLE}}, {'term': {'gather.landed_missions.rmc_site': site}},
        {'term': {'gather.landed_missions.rmc_drive': drive}}]}}}
    body = json.dumps(query, sort_keys=True).encode()
    response = fetch(SEARCH, body)
    parsed = json.loads(response)
    if parsed.get('timed_out') or parsed.get('_shards', {}).get('failed', 0):
        raise ValueError('Incomplete archive search response.')
    directory = directory / hashlib.sha256(body+response).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'query.json').write_bytes(body)
    (directory / 'search.json').write_bytes(response)
    verified_at = datetime.now(timezone.utc).isoformat()
    entries = []
    for index, hit in enumerate(parsed['hits']['hits']):
        source = hit['_source']
        related = source['gather']['pds_archive']['related']
        label = fetch(reference_url(related['label']['uri'], '.xml'))
        browse = fetch(reference_url(related['browse']['uri'], '.png'))
        image = validate_image(source, label, browse, verified_at)
        label_name, browse_name = f'{index}.xml', f'{index}.png'
        (directory / label_name).write_bytes(label)
        (directory / browse_name).write_bytes(browse)
        entries.append({'image': image.model_dump(mode='json'), 'label_file': label_name, 'browse_file': browse_name})
    manifest = {'search_url': SEARCH, 'query_sha256': hashlib.sha256(body).hexdigest(),
                'search_sha256': hashlib.sha256(response).hexdigest(), 'entries': entries}
    path = directory / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return path


def load_images(path: Path):
    manifest = json.loads(path.read_text())
    search = (path.parent / 'search.json').read_bytes()
    query = (path.parent / 'query.json').read_bytes()
    if (manifest['search_url'] != SEARCH or hashlib.sha256(search).hexdigest() != manifest['search_sha256'] or
            hashlib.sha256(query).hexdigest() != manifest['query_sha256']):
        raise ValueError('Image search provenance mismatch.')
    hits = json.loads(search)['hits']['hits']
    if len(hits) != len(manifest['entries']) or len(hits) > 32:
        raise ValueError('Image manifest count mismatch.')
    images = []
    for index, (entry, hit) in enumerate(zip(manifest['entries'], hits)):
        if entry['label_file'] != f'{index}.xml' or entry['browse_file'] != f'{index}.png':
            raise ValueError('Invalid cached image path.')
        image = ImageReference.model_validate(entry['image'])
        checked = validate_image(hit['_source'], (path.parent / entry['label_file']).read_bytes(),
                                 (path.parent / entry['browse_file']).read_bytes(), image.verified_at)
        if image != checked:
            raise ValueError('Cached image metadata/checksum mismatch.')
        images.append(image)
    return images
