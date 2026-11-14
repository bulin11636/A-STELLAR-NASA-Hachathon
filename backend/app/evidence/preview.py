import asyncio
import json
import hashlib
from pathlib import Path

from app.agents.registry import WorkerRegistry
from app.contracts.api import COORDINATE_SYSTEM, MarsCoordinate
from app.contracts.workers import ArtifactMetadata, SourceReference, WorkerContext
from app.coordinator.dispatcher import AgentDispatcher
from app.evidence.adapters import SOURCE_URLS, normalize_evidence
from app.evidence.models import EvidenceRoi, PREVIEW_ROI
from app.evidence.places import parse_places, PDS_SIS
from app.evidence.snapshots import load_snapshots
from app.agents.a6 import RoverEvidenceWorker
from app.agents.a4 import ScienceEvidenceWorker


def prepare_dataset(manifest_path: Path, roi: EvidenceRoi = PREVIEW_ROI, output_root: Path | None = None):
    manifest, content = load_snapshots(manifest_path)
    controls, control_id, control_warnings = parse_places(content["places"], content["places_label"])
    roi_digest = hashlib.sha256(roi.model_dump_json().encode()).hexdigest()[:12]
    processed_version = f"{manifest.dataset_version}:roi-{roi_digest}:evidence-v2"
    artifact_root = output_root.resolve() if output_root else manifest_path.resolve().parent
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_root / f"normalized-{roi.roi_id}-{roi_digest}-evidence-v2.json"
    # ROI IDs are labels, never arbitrary output paths.
    if artifact_path.resolve().parent != artifact_root:
        raise ValueError("ROI ID must not contain path separators.")
    dataset = normalize_evidence(
        waypoints=json.loads(content["waypoints"]), traverse=json.loads(content["traverse"]), samples=json.loads(content["samples"]),
        controls=controls, roi=roi, dataset_version=processed_version,
        provenance_ref=str(manifest_path.resolve()), artifact_ref=str(artifact_path.resolve()),
    )
    dataset = dataset.model_copy(update={"dataset_ids": dataset.dataset_ids + [control_id], "warnings": dataset.warnings + control_warnings})
    metadata = ArtifactMetadata(
        artifact_id=f"{processed_version}:vectors",
        source=SourceReference(dataset_id=dataset.dataset_ids[0], source_url=SOURCE_URLS["waypoints"], mission="Mars 2020", instrument="Derived mission mapping / localization"),
        acquisition_time=None, downloaded_at=manifest.snapshots["waypoints"].downloaded_at,
        bounding_region=[MarsCoordinate(longitude=x, latitude=y) for x, y in [(roi.west, roi.south), (roi.east, roi.south), (roi.east, roi.north), (roi.west, roi.north)]],
        coordinate_system=COORDINATE_SYSTEM, projection="Native Mars planetocentric longitude/latitude; PLACES equidistant cylindrical controls",
        grid_transform=None, resolution_m=None, nodata_value=None, coverage_ref=roi.roi_id, unknown_mask_ref=None,
        resampling="None; vector selection with source feature boundaries preserved", processing_version="evidence-v2",
        uncertainties=dataset.warnings + [f"Coordinate evidence: {PDS_SIS}. Other original sources and hashes are in the snapshot manifest."],
    )
    artifact_path.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
    artifact_path.with_suffix(".metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    return dataset


async def preview(manifest_path: Path, roi: EvidenceRoi, query_point: MarsCoordinate | None):
    dataset = prepare_dataset(manifest_path, roi)
    registry = WorkerRegistry()
    registry.register(ScienceEvidenceWorker(dataset))
    registry.register(RoverEvidenceWorker(dataset, query_point))
    context = WorkerContext(mission_id="evidence-preview", region_id="jezero", roi_id=roi.roi_id, dataset_version=dataset.dataset_version)
    report = await AgentDispatcher(registry, timeout_seconds=10).run(context, ("A4", "A6"))
    # Only a small summary is printed. Large vectors remain referenced artifacts.
    print(json.dumps({
        "dataset_version": dataset.dataset_version, "roi_id": roi.roi_id,
        "science_sites": len(dataset.pois), "rover_stops": len(dataset.stops), "source_segments": len(dataset.segments),
        "workers": [{"agent_id": item.agent_id, "status": item.status, "data_kind": item.data_kind} for item in report.results],
        "nearest_track_distance_m": report.results[1].nearest_track_distance_m,
        "artifact_ref": dataset.artifact_ref, "warnings": dataset.warnings,
    }, indent=2))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Inspect source-backed A4/A6 evidence without changing the v1 API or claiming DEM alignment.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--roi", type=Path, help="JSON EvidenceRoi; defaults to the explicitly non-planning Jezero preview window")
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--latitude", type=float)
    args = parser.parse_args()
    if (args.longitude is None) != (args.latitude is None):
        parser.error("Longitude and latitude must be supplied together.")
    try:
        roi = EvidenceRoi.model_validate_json(args.roi.read_text()) if args.roi else PREVIEW_ROI
        point = MarsCoordinate(longitude=args.longitude, latitude=args.latitude) if args.longitude is not None else None
        asyncio.run(preview(args.manifest.resolve(), roi, point))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Evidence preview failed: {error}\n")


if __name__ == "__main__":
    main()
