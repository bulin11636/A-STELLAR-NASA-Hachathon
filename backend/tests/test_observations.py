"""Synthetic fixtures only; live archive results are kept in ignored caches."""
import asyncio
from decimal import Decimal as D
import hashlib
import json

import pytest

from app.contracts.api import MarsCoordinate
from app.contracts.workers import SourceReference, WorkerContext
from app.evidence.models import EvidenceDataset, LocalizedStop, PREVIEW_ROI
from app.agents.a6.observations import (CLOCK_FIELDS, OBS_FIELDS, ClockRange, Exposure, ObservationMatch,
                                       ObservationReport, checked_input, join_observations, parse_ancillary)
from app.agents.a6.images import (ATLAS, BUNDLE, URI_PREFIX, allowed, load_images, reference_url, validate_image)
from app.agents.a6 import RoverEvidenceWorker
from app.agents.a6 import observations


def interval(start='10', end='20', *, position=2, pose=0, arm=0, exact=True, frame='ROVER'):
    return ClockRange(D(start), D(end), D(start), D(end), (3,position,pose,arm,0,0,0,0,0,0), frame, exact)


def join(ranges, start='12', duration='1', stops=None):
    return join_observations([Exposure(D(start), 'NAVCAM_LEFT', D(duration))], ranges, {'3_2'} if stops is None else stops)[0]


@pytest.mark.parametrize('ranges,start,duration,status', [
    ([interval()], '12', '1', 'exact'),
    ([interval()], '20', '0', 'exact'),
    ([interval()], '20', '.001', 'unknown_rmc'),
    ([interval()], '9', '2', 'unknown_rmc'),
    ([interval()], '21', '1', 'unmatched'),
    ([interval(position=3)], '12', '1', 'moving'),
    ([interval(pose=1)], '12', '1', 'moving'),
    ([interval(arm=1)], '12', '1', 'moving'),
    ([interval(arm=-1)], '12', '1', 'unknown_rmc'),
    ([interval(frame='INMOTION')], '12', '1', 'moving'),
    ([interval(exact=False)], '12', '1', 'approximate'),
    ([interval(), interval(position=4)], '12', '1', 'ambiguous'),
    ([interval(), interval('12.5', '14', position=4)], '12', '1', 'ambiguous'),
    ([interval(), interval(arm=-1)], '12', '1', 'exact'),
])
def test_whole_exposure_interval_join(ranges, start, duration, status):
    result = join(ranges, start, duration)
    assert result.status == status
    assert result.stop_id == ('3_2' if status == 'exact' else None)


def test_missing_position_no_nearest_sol_fallback_and_decimal_precision():
    assert join([interval()], stops=set()).status == 'missing_position'
    assert join([interval('668191860.522', '668191860.523')], '668191860.522999999', '.000000002').status == 'unknown_rmc'
    assert join([interval()], '0', '30').status == 'unknown_rmc'


def test_sweep_is_order_independent_and_keeps_future_intervals_for_next_exposure():
    exposures = [Exposure(D('15'), 'NAVCAM_RIGHT', D('0')), Exposure(D('11'), 'NAVCAM_LEFT', D('5'))]
    ranges = [interval('14', '17', position=4), interval('10', '12')]
    actual = join_observations(exposures, ranges, {'3_2', '3_4'})
    assert [m.status for m in actual] == ['ambiguous', 'exact']
    assert actual[1].stop_id == '3_4'
    assert actual == join_observations(list(reversed(exposures)), list(reversed(ranges)), {'3_2', '3_4'})


def labeled(fields, rows, name, version='16.0'):
    table = (','.join(fields)+'\n'+'\n'.join(','.join(row) for row in rows)+'\n').encode()
    label = f'''<Product_Ancillary xmlns="http://pds.nasa.gov/pds4/pds/v1"><Identification_Area>
    <logical_identifier>urn:nasa:pds:mars2020_rover_places:data_ancillary:{name}</logical_identifier>
    <version_id>{version}</version_id></Identification_Area><Table_Delimited><records>{len(rows)}</records>
    <Record_Delimited>{''.join('<Field_Delimited><name>'+f+'</name></Field_Delimited>' for f in fields)}</Record_Delimited>
    </Table_Delimited></Product_Ancillary>'''.encode()
    return table, label


def tables():
    obs = labeled(OBS_FIELDS, [['12','NAVCAM_LEFT','1'], ['12.0','NAVCAM_LEFT','1.0'], ['12','NAVCAM_RIGHT','1']], 'observations.csv')
    rows = [['ROVER', '3','2','0','0','0','0','0','0','0','0','10','20','10','20']]
    return *obs, *labeled(CLOCK_FIELDS, rows, 'sclk_table.csv')


def test_pds_parsing_deduplicates_exposures_without_collapsing_instruments():
    exposures, ranges, ids, duplicates = parse_ancillary(*tables())
    assert len(exposures) == 2 and duplicates == 1 and len(ranges) == 1
    assert all(i.endswith('::16.0') for i in ids)


@pytest.mark.parametrize('old,new', [(b',1\n',b',NaN\n'), (b'NAVCAM_LEFT', b''), (b'12,', b'-1,'), (b'12,', b'Infinity,')])
def test_invalid_observation_records_fail_closed(old, new):
    data = list(tables()); data[0] = data[0].replace(old, new)
    with pytest.raises(ValueError):
        parse_ancillary(*data)


def test_label_identity_count_header_and_release_mismatches_are_rejected():
    for index, old, new in [(1,b'observations.csv',b'other.csv'), (1,b'<records>3',b'<records>4'),
                            (3,b'16.0',b'15.0'), (0,b'sclk,inst',b'inst,sclk'), (2,b',10,20,10,20',b',20,10,10,20')]:
        data=list(tables()); data[index]=data[index].replace(old,new)
        with pytest.raises(ValueError):
            parse_ancillary(*data)


def image_fixture():
    lid = 'urn:nasa:pds:mars2020_navcam_ops_raw:data:synthetic'
    source = {'bundle_id': BUNDLE, 'pds4_label': {'vid':'3.0'}, 'gather': {
        'pds_archive': {'product_id':lid, 'related':{'label':{'uri':URI_PREFIX+'data/synthetic.xml'}, 'browse':{'uri':URI_PREFIX+'browse/synthetic.png'}}},
        'common':{'instrument':['NAVCAM_LEFT']}, 'time':{'spacecraft_clock_start_count':'12'},
        'landed_missions':{'rmc_site':3,'rmc_drive':2,'planet_day_number':5}}}
    label = f'''<Product xmlns="http://pds.nasa.gov/pds4/pds/v1"><Identification_Area><logical_identifier>{lid}</logical_identifier>
    <version_id>3.0</version_id></Identification_Area><spacecraft_clock_start>12</spacecraft_clock_start>
    <ops_instrument_key>NAVCAM_LEFT</ops_instrument_key><sol_number>5</sol_number>
    <Motion_Counter_Index><index_id>SITE</index_id><index_value_number>3</index_value_number></Motion_Counter_Index>
    <Motion_Counter_Index><index_id>DRIVE</index_id><index_value_number>2</index_value_number></Motion_Counter_Index></Product>'''.encode()
    png = b'\x89PNG\r\n\x1a\n'+b'\0\0\0\rIHDR'+b'\0'*17
    return source,label,png


def test_image_identity_clock_instrument_and_rmc_must_match_index():
    source,label,png=image_fixture()
    image=validate_image(source,label,png,'2026-11-12T00:00:00Z')
    assert image.stop_id=='3_2' and image.sol==5 and image.lidvid.endswith('::3.0')
    for old,new in [(b'>12<',b'>13<'),(b'>NAVCAM_LEFT<',b'>NAVCAM_RIGHT<'),(b'>2<',b'>4<'),(b'>3.0<',b'>2.0<')]:
        with pytest.raises(ValueError):
            validate_image(source,label.replace(old,new),png,image.verified_at)
    with pytest.raises(ValueError):
        validate_image(source,label,b'<html>Not an image</html>',image.verified_at)


def test_archive_references_cannot_escape_allowlisted_sources():
    for uri in ['https://example.com/a.xml', URI_PREFIX+'../a.xml', URI_PREFIX+'data/a.xml?token=x', URI_PREFIX+'data/%2e.xml']:
        with pytest.raises(ValueError):
            reference_url(uri,'.xml')
    assert allowed(ATLAS+'/data/example')
    assert not allowed('http://pds-imaging.jpl.nasa.gov/data')
    assert not allowed('https://example.com/data')
    assert not allowed(ATLAS+'/data?token=x')


def test_ancillary_receipt_detects_tampering(tmp_path):
    path=tmp_path/'observations.csv'; path.write_bytes(b'synthetic')
    receipt={'source_url':'https://example.com/observations.csv','resolved_url':'https://example.com/observations.csv',
             'bytes':9,'sha256':hashlib.sha256(b'synthetic').hexdigest()}
    path.with_suffix('.csv.source.json').write_text(json.dumps(receipt))
    assert checked_input(path,receipt['source_url'])==b'synthetic'
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError): checked_input(path,receipt['source_url'])


def test_explicit_ancillary_download_writes_verifiable_receipts(tmp_path, monkeypatch):
    class Response:
        def __init__(self, url): self.url=url
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert size == 25_000_001
            return b'synthetic-download'
    monkeypatch.setattr(observations, 'urlopen', lambda request, timeout: Response(request.full_url))
    observations.acquire_ancillary(tmp_path)
    for name in observations.ANCILLARY_FILES:
        assert checked_input(tmp_path/name, observations.PDS_BASE+'data_ancillary/'+name)==b'synthetic-download'


def test_ancillary_download_rejects_unexpected_redirect(tmp_path, monkeypatch):
    class Response:
        url='https://example.com/unreviewed.csv'
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setattr(observations, 'urlopen', lambda request, timeout: Response())
    with pytest.raises(ValueError,match='redirect'):
        observations.acquire_ancillary(tmp_path)
    assert not list(tmp_path.iterdir())


def test_cached_image_catalog_revalidates_bytes_and_metadata(tmp_path):
    source,label,png=image_fixture()
    image=validate_image(source,label,png,'2026-11-12T00:00:00Z')
    query=b'{"synthetic":true}'
    search=json.dumps({'hits':{'hits':[{'_source':source}]}}).encode()
    (tmp_path/'query.json').write_bytes(query); (tmp_path/'search.json').write_bytes(search)
    (tmp_path/'0.xml').write_bytes(label); (tmp_path/'0.png').write_bytes(png)
    manifest={'search_url':ATLAS+'/search/atlas/_search', 'query_sha256':hashlib.sha256(query).hexdigest(),
              'search_sha256':hashlib.sha256(search).hexdigest(), 'entries':[
                  {'image':image.model_dump(mode='json'),'label_file':'0.xml','browse_file':'0.png'}]}
    path=tmp_path/'manifest.json'; path.write_text(json.dumps(manifest))
    assert load_images(path)==[image]
    (tmp_path/'0.png').write_bytes(png+b'tampered')
    with pytest.raises(ValueError,match='checksum'): load_images(path)
    (tmp_path/'0.png').write_bytes(png)
    manifest['entries'][0]['label_file']='../outside.xml'; path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='path'): load_images(path)


def test_worker_attaches_only_context_bound_exact_images_and_keeps_duplicate_sols():
    source,label,png=image_fixture()
    image=validate_image(source,label,png,'2026-11-12T00:00:00Z')
    src=SourceReference(dataset_id='synthetic',source_url='https://example.com/source',mission='synthetic',instrument='synthetic')
    stops=[LocalizedStop(record_id=f'3_{drive}',sol=5,longitude=77.4+drive/1000,latitude=18.4,source=src) for drive in (2,4)]
    dataset=EvidenceDataset(dataset_version='test',roi=PREVIEW_ROI,stops=stops,segments=[],pois=[],dataset_ids=['synthetic'],warnings=[],provenance_ref='test-manifest',artifact_ref='test-vectors')
    report=ObservationReport(evidence_version='test',evidence_provenance_ref='test-manifest',roi=PREVIEW_ROI,
                             stop_coordinates={s.record_id:MarsCoordinate(longitude=s.longitude,latitude=s.latitude) for s in stops},
                             dataset_ids=['synthetic-observations'],input_hashes={},matches=[join([interval()])],images=[image],duplicates_removed=0,warnings=['synthetic'])
    context=WorkerContext(mission_id='test',region_id='jezero',roi_id=PREVIEW_ROI.roi_id,dataset_version='test')
    def run(r): return asyncio.run(RoverEvidenceWorker(dataset,observation_report=r,observation_ref='report.json').run(context))
    result=run(report)
    assert result.status=='partial' and result.artifacts['observations']=='report.json'
    assert len(result.stops)==2 and result.stops[0].observation_urls==[image.browse_url] and result.stops[1].observation_urls==[]
    for updates in [{'evidence_version':'stale'}, {'evidence_provenance_ref':'other'}, {'stop_coordinates':{}},
                    {'images':[image.model_copy(update={'sclk':'13'})]}, {'matches':[]}]:
        result=run(report.model_copy(update=updates))
        assert 'observations' not in result.artifacts and not result.stops[0].observation_urls
