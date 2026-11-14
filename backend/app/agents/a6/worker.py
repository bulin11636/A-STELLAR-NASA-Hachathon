from __future__ import annotations

from typing import TYPE_CHECKING

from app.contracts.api import MarsCoordinate
from app.contracts.workers import RoverStop, RoverTraverseResult, WorkerContext
from app.evidence.models import EvidenceDataset, context_matches
from app.evidence.coordinates import nearest_track_distance_m

if TYPE_CHECKING:
    from app.agents.a6.observations import ObservationReport


class RoverEvidenceWorker:
    agent_id = "A6"

    def __init__(self, dataset: EvidenceDataset, query_point: MarsCoordinate | None = None,
                 observation_report: ObservationReport | None = None, observation_ref: str | None = None):
        self.dataset = dataset
        self.query_point = query_point
        self.observation_report = observation_report
        self.observation_ref = observation_ref

    async def run(self, context: WorkerContext) -> RoverTraverseResult:
        if not context_matches(self.dataset, context):
            return RoverTraverseResult(status="unavailable", data_kind="unavailable", warnings=["A6 evidence ROI/version does not match the requested context."])
        warnings = list(self.dataset.warnings)
        artifacts = {"historical_traverse": self.dataset.artifact_ref}
        dataset_ids = list(self.dataset.dataset_ids)
        verified_urls = {}
        report = self.observation_report
        if report is not None:
            from app.agents.a6.observations import clock
            expected = {s.record_id: MarsCoordinate(longitude=s.longitude, latitude=s.latitude) for s in self.dataset.stops}
            keys = {(clock(m.sclk), m.instrument, m.stop_id) for m in report.matches if m.status == 'exact'}
            uncertain = {(clock(m.sclk), m.instrument) for m in report.matches if m.status != 'exact'}
            valid_images = all(i.stop_id in expected and (clock(i.sclk), i.instrument, i.stop_id) in keys
                               and (clock(i.sclk), i.instrument) not in uncertain for i in report.images)
            if (report.evidence_version == self.dataset.dataset_version and report.roi == self.dataset.roi and
                    report.evidence_provenance_ref == self.dataset.provenance_ref and
                    report.stop_coordinates == expected and valid_images and self.observation_ref):
                artifacts['observations'] = self.observation_ref
                if report.image_manifest_ref:
                    artifacts['image_catalog'] = report.image_manifest_ref
                dataset_ids.extend(report.dataset_ids)
                dataset_ids.extend(i.lidvid for i in report.images)
                warnings.extend(report.warnings)
                if report.observation_time_end:
                    warnings.append(f"Observation acquisition cutoff: {report.observation_time_end.isoformat()}; not a current-coverage guarantee.")
                for image in report.images:
                    verified_urls.setdefault(image.stop_id, set()).add(str(image.browse_url))
                warnings.append(f"Attached {len(report.images)} verified Navcam products; original NASA panorama references remain unverified.")
            else:
                warnings.append('Observation report version, ROI, coordinates or image joins do not match; its image links are not applied.')
        distance = None
        if self.query_point is not None:
            try:
                distance = nearest_track_distance_m(self.query_point, self.dataset.segments, self.dataset.roi)
                if distance is None:
                    warnings.append("Nearest-track distance is unknown outside the selected ROI or without valid segments.")
            except ImportError:
                warnings.append("Metric proximity unavailable: install the optional evidence dependency.")
        return RoverTraverseResult(
            status="partial" if self.dataset.stops else "unavailable", data_kind="observed",
            stops=[RoverStop(**{**stop.model_dump(exclude={"record_id"}),
                               'observation_urls': list(stop.observation_urls) + sorted(verified_urls.get(stop.record_id, set()))})
                   for stop in self.dataset.stops],
            traverse_ref=self.dataset.artifact_ref, artifacts=artifacts,
            dataset_ids=list(dict.fromkeys(dataset_ids)), provenance_ref=self.dataset.provenance_ref,
            coverage_ref=self.dataset.roi.roi_id, nearest_track_distance_m=distance, warnings=warnings,
            data_timestamp=report.observation_time_end if 'observations' in artifacts else None,
        )
