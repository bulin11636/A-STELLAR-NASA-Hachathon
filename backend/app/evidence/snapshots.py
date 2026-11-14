import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from app.evidence.adapters import MAP_CONFIG, SOURCE_URLS
from app.evidence.models import Snapshot, SnapshotManifest
from app.evidence.places import PDS_LABEL, PDS_TABLE

URLS = {"config": MAP_CONFIG, **SOURCE_URLS, "places": PDS_TABLE, "places_label": PDS_LABEL}
FILES = {"config": "config.json", "waypoints": "waypoints.json", "traverse": "traverse.json",
         "samples": "samples.json", "places": "places.csv", "places_label": "places_label.xml"}
MAX_BYTES = 5_000_000


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_snapshots(cache_root: Path) -> Path:
    """Explicit CLI network action only; application requests never download data.

    Only fixed, verified source URLs are used. Local checksums identify snapshots;
    they are not claims of cryptographic authenticity from the original provider.
    """
    downloaded_at = datetime.now(timezone.utc)
    content = {}
    for key, url in URLS.items():
        with urlopen(Request(url, headers={"User-Agent": "A-STELLAR-research/0.1"}), timeout=25) as response:
            if response.url.split("?", 1)[0] != url.split("?", 1)[0]:
                raise ValueError("Unexpected source redirect; review the manifest before ingesting.")
            data = response.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise ValueError(f"Source {key} is empty or exceeds the size limit.")
        content[key] = data
    config = json.loads(content["config"])
    linked = {layer.get("url") for layer in config.get("layers", [])}
    if not set(SOURCE_URLS.values()).issubset(linked):
        raise ValueError("NASA mission configuration no longer advertises the expected exports.")
    version_hash = checksum("".join(f"{key}:{checksum(data)}\n" for key, data in sorted(content.items())).encode())
    version = "jezero-evidence-" + version_hash[:16]
    directory = cache_root.resolve() / version
    directory.mkdir(parents=True, exist_ok=True)
    manifest = SnapshotManifest(dataset_version=version, snapshots={
        key: Snapshot(file_name=FILES[key], source_url=URLS[key], sha256=checksum(data), downloaded_at=downloaded_at,
                      credit="NASA/JPL-Caltech; PDS Geosciences Node where applicable",
                      usage_terms_url="https://www.nasa.gov/nasa-brand-center/images-and-media/")
        for key, data in content.items()
    })
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        load_snapshots(manifest_path)
        return manifest_path
    for key, data in content.items():
        path = directory / FILES[key]
        if path.exists() and checksum(path.read_bytes()) != checksum(data):
            raise ValueError("Existing snapshot content disagrees with its stable version.")
        path.write_bytes(data)
    # Publish the complete manifest last; failed downloads never look complete.
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest_path


def load_snapshots(path: Path) -> tuple[SnapshotManifest, dict[str, bytes]]:
    manifest = SnapshotManifest.model_validate_json(path.read_text(encoding="utf-8"))
    if set(manifest.snapshots) != set(URLS):
        raise ValueError("Snapshot manifest must name all verified evidence sources.")
    content = {}
    for key, snapshot in manifest.snapshots.items():
        if str(snapshot.source_url) != URLS[key] or snapshot.file_name != FILES[key]:
            raise ValueError("Snapshot source URL or file name is not allowlisted.")
        source = (path.parent / snapshot.file_name).resolve()
        if source.parent != path.parent.resolve() or source.stat().st_size > MAX_BYTES:
            raise ValueError("Invalid snapshot path or size.")
        data = source.read_bytes()
        if checksum(data) != snapshot.sha256:
            raise ValueError("Snapshot checksum mismatch; do not use stale or modified data.")
        content[key] = data
    expected = "jezero-evidence-" + checksum("".join(f"{key}:{checksum(data)}\n" for key, data in sorted(content.items())).encode())[:16]
    if manifest.dataset_version != expected:
        raise ValueError("Dataset version disagrees with snapshot content.")
    config = json.loads(content["config"])
    if not set(SOURCE_URLS.values()).issubset({layer.get("url") for layer in config.get("layers", [])}):
        raise ValueError("Source exports are not linked by the saved mission configuration.")
    return manifest, content


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Download bounded official NASA/PDS evidence snapshots; no raster data.")
    parser.add_argument("--cache-dir", type=Path, default=Path(__file__).resolve().parents[3] / "data/cache/evidence")
    args = parser.parse_args()
    try:
        print(fetch_snapshots(args.cache_dir))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Evidence download failed: {error}\n")


if __name__ == "__main__":
    main()
