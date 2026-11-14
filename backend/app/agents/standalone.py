"""Shared configuration/provenance for opt-in standalone prototype adapters."""
import json
from pathlib import Path
from typing import Literal

from app.contracts.api import ContractModel, MarsCoordinate, NonEmptyString
from app.contracts.workers import SourceReference, WorkerContext

DATA_ROOT = Path(__file__).resolve().parents[3] / 'data'


class PrototypeConfig(ContractModel):
    region_id: Literal['jezero'] = 'jezero'
    roi_id: NonEmptyString
    dataset_version: NonEmptyString
    point: MarsCoordinate
    source: SourceReference
    provenance_ref: NonEmptyString

    def matches(self, context: WorkerContext) -> bool:
        return ((self.region_id, self.roi_id, self.dataset_version) ==
                (context.region_id, context.roi_id, context.dataset_version))


def write_report(directory: Path, agent_id: str, config: PrototypeConfig,
                 result: dict, warnings: list[str]) -> str:
    """Record raw prototype output without promoting it to a validated grid."""
    content = json.dumps({'agent_id': agent_id, 'data_kind': 'scenario', 'planning_ready': False,
                          'configuration': config.model_dump(mode='json'),
                          'prototype_result': result, 'warnings': warnings}, indent=2, allow_nan=False)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'report.json'
    path.write_text(content, encoding='utf-8')
    return str(path)
