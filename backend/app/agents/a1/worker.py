import asyncio
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from pydantic import Field

from app.agents.standalone import DATA_ROOT, PrototypeConfig, write_report
from app.contracts.workers import SurfaceResult, WorkerContext


class TraversabilityConfig(PrototypeConfig):
    dem_path: Path
    radius_m: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    tile_size_m: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    max_slope_deg: Annotated[float, Field(strict=True, gt=0, lt=90, allow_inf_nan=False)] = 15.0
    output_root: Path = DATA_ROOT / 'processed/a1'


class TraversabilityWorker:
    """Prototype adapter; does not certify canonical geometry or risk masks."""
    agent_id = 'A1'

    def __init__(self, config: TraversabilityConfig | None = None):
        self.config = config

    async def run(self, context: WorkerContext) -> SurfaceResult:
        if self.config is None:
            return self._unavailable('A1 prototype inputs/provenance are not configured.')
        if not self.config.matches(context):
            return self._unavailable('A1 configuration does not match the requested region, ROI or dataset version.')
        try:
            return await asyncio.to_thread(self._execute)
        except ImportError:
            return self._unavailable('A1 optional raster dependencies are unavailable; install rasterio and numpy before explicit prototype execution.')
        except OSError:
            return self._unavailable('A1 could not read its configured input or write its prototype artifacts.')
        except (ValueError, KeyError, TypeError):
            return SurfaceResult(status='failed', data_kind='unavailable', warnings=['A1 prototype returned an invalid report or grid reference.'])

    @staticmethod
    def _unavailable(reason: str) -> SurfaceResult:
        return SurfaceResult(status='unavailable', data_kind='unavailable', warnings=[reason])

    def _analyze(self, directory: Path) -> dict:
        # Lazy import keeps API startup and package discovery independent of GDAL.
        from .a1_traversability_agent import EdgeSurfaceAnalyzer
        config = self.config
        return EdgeSurfaceAnalyzer(str(config.dem_path)).analyze_roi_local(
            config.point.longitude, config.point.latitude, config.radius_m,
            config.tile_size_m, config.max_slope_deg, output_directory=directory)

    def _execute(self) -> SurfaceResult:
        config = self.config
        if not config.dem_path.is_file():
            return self._unavailable('A1 configured DEM file is missing; no terrain values are inferred.')
        directory = config.output_root.resolve() / uuid4().hex
        result = self._analyze(directory)
        if result['status'] == 'unavailable':
            return self._unavailable('A1 standalone analysis could not produce a terrain report.')
        if result['status'] != 'complete':
            raise ValueError('Unexpected A1 prototype status.')
        grid = Path(result['grid_file_path']).resolve()
        if not grid.is_relative_to(directory) or grid.suffix != '.npy' or not grid.is_file():
            raise ValueError('A1 grid must be a private artifact of this execution.')
        warnings = ['A1 PROTOTYPE SCENARIO: source CRS, metric slopes, partial NoData handling and wire/grid alignment remain unvalidated.',
                    'This slope artifact is not a canonical planning grid: grid_id, risk, blocked/unknown masks and geospatial metadata remain unavailable.',
                    'Blocking raster work runs in a thread; cancellation does not forcibly terminate native GDAL computation.']
        report = write_report(directory, self.agent_id, config, result, warnings)
        return SurfaceResult(status='partial', data_kind='scenario',
                             artifacts={'prototype_report': report, 'prototype_slope_grid': str(grid)},
                             dataset_ids=[config.source.dataset_id], provenance_ref=config.provenance_ref,
                             warnings=warnings)
