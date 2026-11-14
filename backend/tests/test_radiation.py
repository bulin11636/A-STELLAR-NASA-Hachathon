"""Synthetic RAD records and explicitly hypothetical radiation scenarios."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.a3 import RadiationScenario, ScenarioRadiationWorker
from app.agents.registry import WorkerRegistry
from app.contracts.workers import MissionParameters, WorkerContext
from app.coordinator.dispatcher import AgentDispatcher
from app.agents.a3.inspection import DATASET_ID, PRODUCT, parse_rdr, verified_file


def scenario(**changes):
    fields = dict(scenario_id='synthetic',roi_id='test-roi',dataset_version='test-v1',
                  source={'dataset_id':'synthetic-reference','source_url':'https://example.com/synthetic',
                          'mission':'synthetic','instrument':'synthetic'},source_locator='synthetic only',
                  source_observation_period='synthetic epoch',rate=12.0,rate_uncertainty=2.0,rate_unit='uSv/hour',
                  uncertainty_description='Synthetic sensitivity half-width, not a confidence bound.',
                  assumptions=['Constant synthetic rate.'],limitations=['No actual exposure data.'],max_duration_min=1440.0)
    return RadiationScenario(**{**fields,**changes})


def context(duration=60.0, budget=20.0, **changes):
    return WorkerContext(mission_id='test',region_id='jezero',roi_id='test-roi',dataset_version='test-v1',
                         parameters=MissionParameters(eva_duration_min=duration,radiation_budget_usv=budget),**changes)


def run(model=None, duration=60.0, budget=20.0):
    return asyncio.run(ScenarioRadiationWorker(model or scenario(),'synthetic-scenario.json').run(context(duration,budget)))


@pytest.mark.parametrize('budget,status', [(14.0,'pass'),(13.9,'unknown'),(12.0,'unknown'),(10.0,'unknown'),(9.9,'fail'),(0.0,'fail'),(None,'unknown')])
def test_budget_band_comparisons_are_inclusive_only_at_upper_bound(budget,status):
    result=run(budget=budget)
    assert result.constraint_status==status
    assert result.dose_estimate_usv==12.0 and result.dose_uncertainty_usv==2.0
    assert result.status=='partial' and result.data_kind=='scenario'
    assert result.provenance_ref and result.model_reference and result.dataset_ids


@pytest.mark.parametrize('unit,rate,spread', [('uSv/hour',24.0,6.0),('uSv/day',576.0,144.0),('mSv/day',0.576,0.144)])
def test_units_convert_using_24_earth_hours_per_day(unit,rate,spread):
    result=run(scenario(rate=rate,rate_uncertainty=spread,rate_unit=unit),duration=30.0)
    assert result.dose_rate_usv_per_hour==24.0
    assert result.dose_estimate_usv==12.0 and result.dose_uncertainty_usv==3.0


def test_linear_uncertainty_and_zero_duration():
    result=run(duration=180.0,budget=100.0)
    assert result.dose_estimate_usv==36.0 and result.dose_uncertainty_usv==6.0
    zero=run(duration=0.0,budget=0.0)
    assert zero.dose_estimate_usv==0.0 and zero.dose_uncertainty_usv==0.0 and zero.constraint_status=='pass'
    absent_uncertainty=run(scenario(rate_uncertainty=None))
    assert absent_uncertainty.dose_uncertainty_usv is None and absent_uncertainty.constraint_status=='unknown'
    assert run(scenario(rate_uncertainty=None),duration=0.0,budget=0.0).constraint_status=='pass'


def test_uncertainty_lower_band_is_clipped_at_zero():
    assert run(scenario(rate=1.0,rate_uncertainty=2.0),budget=0.0).constraint_status=='unknown'


def test_missing_model_source_duration_provenance_scope_stays_unknown():
    worker=ScenarioRadiationWorker()
    for result in [asyncio.run(worker.run(context())),run(duration=None),run(duration=1440.1),
                   asyncio.run(ScenarioRadiationWorker(scenario()).run(context())),
                   asyncio.run(ScenarioRadiationWorker(scenario(dataset_version='other'),'p').run(context())),
                   asyncio.run(ScenarioRadiationWorker(scenario(roi_id='other'),'p').run(context()))]:
        assert result.status=='unavailable' and result.dose_estimate_usv is None
        assert result.constraint_status=='unknown' and result.warnings
    missing=scenario().model_dump(); missing.pop('source')
    with pytest.raises(ValidationError): RadiationScenario(**missing)


@pytest.mark.parametrize('changes', [{'rate':-1.0},{'rate':float('nan')},{'rate_uncertainty':-0.1},
                                    {'rate_unit':'uGy/hour'},{'quantity':'absorbed_dose'},
                                    {'assumptions':[]},{'limitations':[]},{'max_duration_min':0.0},{'rate':True}])
def test_invalid_or_unsupported_scenarios_are_rejected(changes):
    with pytest.raises(ValidationError): scenario(**changes)


def test_large_numbers_do_not_emit_infinite_doses():
    result=run(scenario(rate=1e308,max_duration_min=1e308),duration=1e308)
    assert result.status=='unavailable' and result.dose_estimate_usv is None


def test_tiny_positive_values_are_not_rounded_to_zero_exposure():
    result=run(scenario(rate=1e-300),duration=1e-300)
    assert result.status=='unavailable' and result.dose_estimate_usv is None


def test_published_example_is_a_scenario_and_not_raw_absorbed_dose_conversion():
    path=Path(__file__).resolve().parents[2]/'data/samples/msl-rad-literature-scenario.json'
    model=RadiationScenario.model_validate_json(path.read_bytes())
    ctx=WorkerContext(mission_id='replay',region_id='jezero',roi_id=model.roi_id,dataset_version=model.dataset_version,
                      parameters=MissionParameters(eva_duration_min=360.0,radiation_budget_usv=200.0))
    registry=WorkerRegistry(); registry.register(ScenarioRadiationWorker(model,'published-scenario.json'))
    result=asyncio.run(AgentDispatcher(registry).run(ctx,('A3',))).results[0]
    assert result.data_kind=='scenario' and result.status=='partial'
    assert result.dose_estimate_usv==160.0 and result.dose_uncertainty_usv==30.0
    assert result.constraint_status=='pass' and any('Jezero' in w for w in result.warnings)


def product(rows=None):
    rows=rows or [('000','2012-220 02:25:43','00000000','8.98260','8.53545'),
                  ('001','2012-220 02:45:43','00000000','9.03815','8.48693')]
    text='[FILE]\r\nSTART_SOL=0001\r\nSTART_TIME="2012-220 02:25:43"\r\n\r\n'
    for number,utc,qc,b,e in rows:
        text+=f'[OBSERVATION: {int(number):02}]\r\nSTART_OBS_UTC="{utc}"\r\nQC={qc}\r\n'
        for detector,value in [('B',b),('E',e)]:
            if value is not None:
                text+=f'\r\n[DOSIMETRY_TOTAL_DOSE_{detector}: {int(number):02}]\r\n\r\n{value}\r\n'
        text+=f'\r\n[DOSIMETRY_LET_B_A1: {int(number):02}]\r\nnot parsed as total dose\r\n'
    data=text.encode('ascii')
    label=f'''PDS_VERSION_ID = PDS3
RECORD_TYPE = STREAM
FILE_RECORDS = {len(data.splitlines())}
DATA_SET_ID = "{DATASET_ID}"
PRODUCT_ID = "{PRODUCT}"
INSTRUMENT_ID = "RAD"
INSTRUMENT_HOST_ID = "MSL"
TARGET_NAME = "MARS"
START_TIME = 2012-220T02:25:43
STOP_TIME = "UNK"
/* For Observation 000 */
'''
    for number,utc,qc,b,e in rows:
        for detector,value in [('B',b),('E',e)]:
            if value is None: continue
            header=f'[DOSIMETRY_TOTAL_DOSE_{detector}: {int(number):02}]'
            offset=data.index(value.encode(),data.index(header.encode()))+1
            name=f'OBS{number}_TOT_DOSE_{detector}_ELEMENT'
            label+=f'''^{name} = ("{PRODUCT}.TXT",{offset} <BYTES>)
OBJECT = {name}
NAME = OBS_{number}_TOT_DOSE_{detector}
START_BYTE = 1
BYTES = {len(value)}
DATA_TYPE = ASCII_REAL
UNIT = "microGray / Hour"
END_OBJECT = {name}
'''
    return data,label.encode('ascii')


def test_rdr_byte_pointers_and_units_preserve_separate_detectors():
    result=parse_rdr(*product())
    assert len(result.observations)==2 and all(o.baseline_eligible for o in result.observations)
    assert result.observations[0].observed_at==datetime(2012,8,7,2,25,43,tzinfo=timezone.utc)
    assert result.observations[0].detector_e_ugy_per_hour==8.53545
    assert result.observations[0].detector_b_ugy_per_hour==8.98260
    assert result.stop_time is None


@pytest.mark.parametrize('qc,b,e', [('00000100','1.0','2.0'),('00001000','1.0','2.0'),
                                  ('bad','1.0','2.0'),('00000000','-1','2.0'),
                                  ('00000000','NaN','2.0'),('00000000','1.0',None)])
def test_quality_flags_sentinels_and_missing_values_are_not_baselines(qc,b,e):
    result=parse_rdr(*product([('000','2012-220 02:25:43',qc,b,e)]))
    assert not result.observations[0].baseline_eligible and result.observations[0].exclusions


def test_backward_or_invalid_timestamps_remain_excluded_and_are_not_reordered():
    report=parse_rdr(*product([('000','2012-220 02:45:43','00000000','1.0','2.0'),
                              ('001','2012-220 02:35:43','00000000','1.1','2.1'),
                              ('002','invalid','00000000','1.2','2.2')]))
    assert report.observations[0].baseline_eligible
    assert not report.observations[1].baseline_eligible
    assert report.observations[2].observed_at is None


def test_record_count_discrepancy_is_visible_and_excludes_baseline_use():
    data,label=product()
    label=label.replace(f'FILE_RECORDS = {len(data.splitlines())}'.encode(),b'FILE_RECORDS = 999')
    report=parse_rdr(data,label)
    assert not any(o.baseline_eligible for o in report.observations)
    assert 'discrepancy' in report.warnings[0]


@pytest.mark.parametrize('old,new', [(b'microGray / Hour',b'microSv / Hour'),(b'ASCII_REAL',b'ASCII_INTEGER'),
                                    (b'INSTRUMENT_ID = "RAD"',b'INSTRUMENT_ID = "MEDA"'),
                                    (b'START_BYTE = 1',b'START_BYTE = 2'),
                                    (b'<BYTES>',b'<RECORDS>')])
def test_unsupported_labels_do_not_silently_change_meaning(old,new):
    data,label=product()
    with pytest.raises(ValueError): parse_rdr(data,label.replace(old,new))


def test_data_tampering_byte_pointer_and_duplicate_sections_fail_closed():
    data,label=product()
    with pytest.raises(ValueError): parse_rdr(data.replace(b'8.98260',b'8.982600'),label)
    with pytest.raises(ValueError): parse_rdr(data+b'[OBSERVATION: 00]\r\n',label)
    with pytest.raises(ValueError): parse_rdr(data[:-80],label)


def test_source_receipts_detect_wrong_source_or_changed_bytes(tmp_path):
    path=tmp_path/'synthetic.TXT'; content=b'synthetic'; path.write_bytes(content)
    receipt={'source_url':'https://example.com/a','resolved_url':'https://example.com/a',
             'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
    path.with_name(path.name+'.source.json').write_text(json.dumps(receipt))
    assert verified_file(path,receipt['source_url'])==content
    with pytest.raises(ValueError): verified_file(path,'https://example.com/other')
    path.write_bytes(b'changed')
    with pytest.raises(ValueError): verified_file(path,receipt['source_url'])
