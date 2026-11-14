"""Explicit offline A6 preparation, with optional bounded image acquisition."""
import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from app.contracts.workers import WorkerContext
from app.agents.a6.images import acquire_images, load_images
from app.agents.a6.observations import acquire_ancillary, prepare_observations
from app.evidence.preview import prepare_dataset
from app.agents.a6 import RoverEvidenceWorker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True, help='Validated traverse snapshot manifest')
    parser.add_argument('--places', type=Path, required=True, help='Directory containing receipted ancillary tables/labels')
    parser.add_argument('--download-places', action='store_true', help='Explicitly refresh the four fixed PLACES ancillary files before processing')
    parser.add_argument('--images', type=Path, help='Previously acquired image manifest for offline validation')
    parser.add_argument('--download-images', type=Path, help='Explicitly acquire a bounded Navcam sample into this cache')
    parser.add_argument('--site', type=int, default=3)
    parser.add_argument('--drive', type=int, default=110)
    parser.add_argument('--limit', type=int, default=8)
    args = parser.parse_args()
    if args.images and args.download_images:
        parser.error('Choose an existing image manifest or a new download.')
    try:
        dataset = prepare_dataset(args.manifest.resolve())
        if args.download_places:
            acquire_ancillary(args.places)
        image_path = acquire_images(args.download_images, args.site, args.drive, args.limit) if args.download_images else args.images
        report = prepare_observations(dataset, args.places, load_images(image_path) if image_path else [])
        if image_path:
            report = report.model_copy(update={'image_manifest_ref': str(image_path.resolve()),
                'input_hashes': {**report.input_hashes, 'image_manifest': hashlib.sha256(image_path.read_bytes()).hexdigest()}})
        content = report.model_dump_json()
        digest = hashlib.sha256(content.encode()).hexdigest()[:16]
        path = args.manifest.resolve().parent / f'a6-observations-{digest}.json'
        path.write_text(content, encoding='utf-8')
        context = WorkerContext(mission_id='a6-preview', region_id='jezero', roi_id=dataset.roi.roi_id, dataset_version=dataset.dataset_version)
        result = asyncio.run(RoverEvidenceWorker(dataset, observation_report=report, observation_ref=str(path)).run(context))
        print(json.dumps({'observations': len(report.matches), 'matches': dict(Counter(m.status for m in report.matches)),
                          'duplicates_removed': report.duplicates_removed, 'verified_products': len(report.images),
                          'stops_with_verified_images': len({i.stop_id for i in report.images}),
                          'image_manifest': str(image_path) if image_path else None, 'report_ref': str(path),
                          'worker_status': result.status, 'warnings': report.warnings}, indent=2))
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        parser.exit(1, f'A6 preview failed: {error}\n')


if __name__ == '__main__':
    main()
