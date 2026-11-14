"""Offline A4 geology preview using cached, source-checked inputs."""
import asyncio
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

from app.contracts.api import COORDINATE_SYSTEM, MarsCoordinate
from app.contracts.workers import ArtifactMetadata, SourceReference, WorkerContext
from app.agents.a4.geology import PROCESSING_VERSION, SOURCE_DOI, build_report, extract_vectors, read_catalog
from app.evidence.models import EvidenceRoi, PREVIEW_ROI
from app.evidence.preview import prepare_dataset
from app.agents.a4 import ScienceEvidenceWorker


def run_preview(archive: Path, manifest_path: Path, output_root: Path, roi: EvidenceRoi = PREVIEW_ROI, offset_m: float = 200):
    dataset = prepare_dataset(manifest_path, roi)
    gdb, prj, extraction = extract_vectors(archive, output_root)
    # Find the extraction directory from the known prefix instead of assuming
    # an installation's working directory.
    directory = output_root.resolve() / extraction["archive"]["sha256"][:16]
    provenance = directory / "vector-extraction-manifest.json"
    version = extraction["archive"]["sha256"] + ":" + PROCESSING_VERSION
    catalog = read_catalog(gdb, prj, version=version, provenance_ref=str(provenance))
    report = build_report(catalog, pois=dataset.pois, roi=roi, evidence_version=dataset.dataset_version,
                          evidence_provenance_ref=dataset.provenance_ref, offset_m=offset_m)
    key = hashlib.sha256(json.dumps({"geology": version, "evidence": dataset.dataset_version, "offset_m": float(offset_m)}, sort_keys=True).encode()).hexdigest()[:16]
    artifact = directory / f"poi-geology-{key}.json"
    artifact.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    metadata = ArtifactMetadata(
        artifact_id=f"{version}:association-{key}",
        source=SourceReference(dataset_id="USGS SIM 3464 (2020)", source_url=SOURCE_DOI,
                               mission="USGS / NASA Mars mapping", instrument="CTX primary basemap; compiled geologic interpretation"),
        acquisition_time=None, downloaded_at=datetime.fromisoformat(extraction["archive"]["downloaded_at"]),
        bounding_region=[MarsCoordinate(longitude=x, latitude=y) for x, y in [(roi.west, roi.south), (roi.east, roi.south), (roi.east, roi.north), (roi.west, roi.north)]],
        coordinate_system=COORDINATE_SYSTEM, projection=report.source_crs_wkt,
        grid_transform=None, resolution_m=None, nodata_value=None, coverage_ref=str(artifact), unknown_mask_ref=None,
        resampling="No resampling or fixed shift; source polygons and nominal point projection only",
        processing_version=PROCESSING_VERSION, uncertainties=report.warnings,
    )
    artifact.with_suffix(".metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    worker = ScienceEvidenceWorker(dataset, geology_report=report, geology_ref=str(artifact))
    result = asyncio.run(worker.run(WorkerContext(mission_id="a4-geology-preview", region_id="jezero", roi_id=roi.roi_id, dataset_version=dataset.dataset_version)))
    if result.geology_ref is None:
        raise ValueError("A4 did not accept the generated geology report.")
    summary = {
        "worker_status": result.status, "data_kind": result.data_kind,
        "accepted_polygons": report.accepted_polygons, "rejected_feature_ids": report.rejected_feature_ids,
        "inconsistent_unit_codes": report.inconsistent_unit_codes,
        "science_sites": len(report.associations), "classifications": dict(Counter(item.status for item in report.associations)),
        "nominal_unit_symbols": sorted({unit.symbol for item in report.associations for unit in item.nominal_units}),
        "screening_offset_m": offset_m, "geology_ref": str(artifact), "provenance_ref": str(provenance),
        "ranked_pois": sum(poi.priority is not None for poi in result.pois), "warnings": result.warnings,
    }
    return summary, report


def main():
    import argparse

    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Inspect USGS regional geology context for A4 without changing API routing or asserting alignment.")
    parser.add_argument("--archive", type=Path, default=root / "data/cache/a4-geology/sim3464/sim3464_database.zip")
    parser.add_argument("--manifest", type=Path, required=True, help="Existing NASA/PDS evidence snapshot manifest")
    parser.add_argument("--output-dir", type=Path, default=root / "data/processed/a4-geology")
    parser.add_argument("--roi", type=Path)
    parser.add_argument("--offset-m", type=float, default=200)
    args = parser.parse_args()
    try:
        roi = EvidenceRoi.model_validate_json(args.roi.read_text(encoding="utf-8")) if args.roi else PREVIEW_ROI
        summary, _report = run_preview(args.archive.resolve(), args.manifest.resolve(), args.output_dir, roi, args.offset_m)
        print(json.dumps(summary, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"A4 geology preview failed: {error}\n")


if __name__ == "__main__":
    main()
