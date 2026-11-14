from __future__ import annotations

from typing import TYPE_CHECKING

from app.contracts.api import MarsCoordinate
from app.contracts.workers import ScienceResult, WorkerContext
from app.evidence.models import EvidenceDataset, context_matches
from app.evidence.adapters import GEOLOGY_NOT_LOADED

if TYPE_CHECKING:
    from app.agents.a4.geology import GeologyReport


class ScienceEvidenceWorker:
    agent_id = "A4"

    def __init__(self, dataset: EvidenceDataset, categories: frozenset[str] | None = None,
                 geology_report: GeologyReport | None = None, geology_ref: str | None = None):
        self.dataset = dataset
        self.categories = categories
        self.geology_report = geology_report
        self.geology_ref = geology_ref

    async def run(self, context: WorkerContext) -> ScienceResult:
        if not context_matches(self.dataset, context):
            return ScienceResult(status="unavailable", data_kind="unavailable", warnings=["A4 evidence ROI/version does not match the requested context."])
        pois = [poi for poi in self.dataset.pois if self.categories is None or poi.category in self.categories]
        warnings = list(self.dataset.warnings)
        geology_ref = None
        dataset_ids = list(self.dataset.dataset_ids)
        report = self.geology_report
        if report is not None:
            locations = {item.poi_id: item.coordinate for item in report.associations}
            expected = {poi.id: MarsCoordinate(longitude=poi.longitude, latitude=poi.latitude) for poi in self.dataset.pois}
            if (report.evidence_version == self.dataset.dataset_version and report.roi == self.dataset.roi and
                    report.evidence_provenance_ref == self.dataset.provenance_ref and
                    locations == expected and len(locations) == len(report.associations) and self.geology_ref):
                geology_ref = self.geology_ref
                warnings = [warning for warning in warnings if warning != GEOLOGY_NOT_LOADED]
                warnings.extend(report.warnings)
                dataset_ids.append(report.source_doi)
                selected_ids = {poi.id for poi in pois}
                selected_matches = [item for item in report.associations if item.poi_id in selected_ids]
                ambiguous = sum(item.status != "nominal_match" for item in selected_matches)
                warnings.append(f"Geology context attached; {ambiguous} of {len(selected_matches)} selected POIs have ambiguous, unmapped or out-of-coverage classifications.")
            else:
                warnings.append("Geology report version, ROI or POI coordinates do not match; its classifications are not applied.")
        artifacts = {"science_sites": self.dataset.artifact_ref}
        if geology_ref:
            artifacts["geology_associations"] = geology_ref
        return ScienceResult(status="partial" if pois else "unavailable", data_kind="observed",
                             pois=pois, dataset_ids=dataset_ids, warnings=warnings +
                             (["No science sites match this ROI/category selection; this is not evidence of no science value."] if not pois else []),
                             artifacts=artifacts, geology_ref=geology_ref, provenance_ref=self.dataset.provenance_ref)
