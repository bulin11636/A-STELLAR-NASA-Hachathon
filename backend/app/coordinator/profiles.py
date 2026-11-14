"""Trusted local configuration; no model-selected files or dynamic imports."""
from pathlib import Path
import hashlib

from pydantic import model_validator

from app.agents.registry import WorkerRegistry
from app.contracts.api import ContractModel
from app.contracts.workers import WorkerContext
from app.coordinator.tools import ToolBox


class RuntimeProfile(ContractModel):
    scope: WorkerContext
    radiation_scenario: Path | None = None
    evidence_manifest: Path | None = None
    geology_report: Path | None = None
    observation_report: Path | None = None
    a1_config: Path | None = None
    a2_config: Path | None = None

    @model_validator(mode='after')
    def report_inputs(self):
        if (self.geology_report or self.observation_report) and not self.evidence_manifest:
            raise ValueError('Geology/observation reports require a source evidence manifest.')
        return self


def read_local(path: Path, max_bytes: int = 128_000_000) -> bytes:
    if path.stat().st_size > max_bytes:
        raise ValueError('Local input exceeds the size limit.')
    return path.read_bytes()


def load_profile(path: Path) -> ToolBox:
    profile_bytes=read_local(path,1_000_000)
    profile=RuntimeProfile.model_validate_json(profile_bytes)
    hashes={'profile':hashlib.sha256(profile_bytes).hexdigest()}
    registry=WorkerRegistry()
    readiness={}
    def resolve(value):
        return (path.resolve().parent/value).resolve()
    def load(value, name, max_bytes=128_000_000):
        content=read_local(resolve(value),max_bytes)
        hashes[name]=hashlib.sha256(content).hexdigest()
        return content
    if profile.radiation_scenario:
        from app.agents.a3 import RadiationScenario, Worker
        scenario_path=resolve(profile.radiation_scenario)
        scenario=RadiationScenario.model_validate_json(load(profile.radiation_scenario,'radiation_scenario',1_000_000))
        if (scenario.region_id,scenario.roi_id,scenario.dataset_version)!=(profile.scope.region_id,profile.scope.roi_id,profile.scope.dataset_version):
            raise ValueError('Radiation scenario must explicitly match profile scope; no automatic rebinding.')
        registry.register(Worker(scenario,str(scenario_path)))
        readiness['A3']='scenario'
    if profile.evidence_manifest:
        from app.evidence.preview import prepare_dataset
        from app.evidence.models import context_matches
        from app.agents.a4 import Worker as ScienceWorker
        from app.agents.a6 import Worker as RoverWorker
        load(profile.evidence_manifest,'evidence_manifest',1_000_000)
        dataset=prepare_dataset(resolve(profile.evidence_manifest))
        if not context_matches(dataset,profile.scope):
            raise ValueError('Evidence manifest must match profile scope.')
        geology,observations=None,None
        if profile.geology_report:
            from app.agents.a4.geology import GeologyReport
            geology=GeologyReport.model_validate_json(load(profile.geology_report,'geology_report'))
        if profile.observation_report:
            from app.agents.a6.observations import ObservationReport
            observations=ObservationReport.model_validate_json(load(profile.observation_report,'observation_report'))
        registry.register(ScienceWorker(dataset,geology_report=geology,
                                        geology_ref=str(resolve(profile.geology_report)) if geology else None))
        registry.register(RoverWorker(dataset,observation_report=observations,
                                      observation_ref=str(resolve(profile.observation_report)) if observations else None))
        readiness.update(A4='evidence',A6='evidence')
    for agent,field_name in [('A1','a1_config'),('A2','a2_config')]:
        value=getattr(profile,field_name)
        if not value:
            continue
        if agent=='A1':
            from app.agents.a1 import TraversabilityConfig as Config, Worker
        else:
            from app.agents.a2 import ThermalConfig as Config, Worker
        config_path=resolve(value)
        config=Config.model_validate_json(load(value,field_name,1_000_000))
        # Resolve explicit file inputs relative to the config file, never CWD.
        updates={}
        for field_name in ('dem_path','day_path','night_path','output_root'):
            if hasattr(config,field_name):
                updates[field_name]=(config_path.parent/getattr(config,field_name)).resolve()
        config=Config.model_validate({**config.model_dump(),**updates})
        if not config.matches(profile.scope):
            raise ValueError(f'{agent} configuration must match profile scope.')
        registry.register(Worker(config))
        readiness[agent]='prototype'
    return ToolBox(registry,profile.scope,readiness,hashes)
