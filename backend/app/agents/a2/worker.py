import asyncio
from pathlib import Path
from uuid import uuid4

from app.agents.standalone import DATA_ROOT, PrototypeConfig, write_report
from app.contracts.workers import ThermalResult, WorkerContext


class ThermalConfig(PrototypeConfig):
    day_path: Path
    night_path: Path
    output_root: Path = DATA_ROOT / 'processed/a2'


class ThermalWorker:
    """Records the standalone heuristics without claiming calibrated physics."""
    agent_id = 'A2'

    def __init__(self, config: ThermalConfig | None = None):
        self.config = config

    async def run(self, context: WorkerContext) -> ThermalResult:
        if self.config is None:
            return self._unavailable('A2 prototype inputs/provenance are not configured.')
        if not self.config.matches(context):
            return self._unavailable('A2 configuration does not match the requested region, ROI or dataset version.')
        try:
            return await asyncio.to_thread(self._execute)
        except ImportError:
            return self._unavailable('A2 optional raster dependencies are unavailable; install rasterio before explicit prototype execution.')
        except OSError:
            return self._unavailable('A2 could not read its configured inputs or write its prototype artifacts.')
        except (ValueError, KeyError, TypeError):
            return ThermalResult(status='failed', data_kind='unavailable', warnings=['A2 prototype returned an invalid report.'])

    @staticmethod
    def _unavailable(reason: str) -> ThermalResult:
        return ThermalResult(status='unavailable', data_kind='unavailable', warnings=[reason])

    def _analyze(self) -> dict:
        from .a2_thermal_agent import EdgeThermalAnalyzer
        config = self.config
        return EdgeThermalAnalyzer(str(config.day_path), str(config.night_path)).analyze_environment(
            config.point.longitude, config.point.latitude)

    def _execute(self) -> ThermalResult:
        config = self.config
        if not config.day_path.is_file() or not config.night_path.is_file():
            return self._unavailable('A2 requires both configured day/night input files; missing data do not imply a surface material.')
        result = self._analyze()
        if result['status'] == 'unavailable':
            return self._unavailable('A2 standalone analysis could not produce thermal context.')
        if result['status'] != 'complete':
            raise ValueError('Unexpected A2 prototype status.')
        warnings = ['A2 PROTOTYPE SCENARIO: DN-to-temperature mapping and material thresholds are uncalibrated heuristics, not measured thermal inertia or EVA loads.',
                    'Source-to-wire registration, observation time and physical thermal constraints remain unknown; no calibrated thermal raster is supplied.',
                    'Blocking raster work runs in a thread; cancellation does not forcibly terminate native GDAL computation.']
        directory = config.output_root.resolve() / uuid4().hex
        report = write_report(directory, self.agent_id, config, result, warnings)
        return ThermalResult(status='partial', data_kind='scenario', artifacts={'prototype_report': report},
                             dataset_ids=[config.source.dataset_id], provenance_ref=config.provenance_ref,
                             constraint_status='unknown', warnings=warnings)
