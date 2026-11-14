"""Acquire only products allowlisted in data/samples/download-manifest.json.

Scientific files and receipts remain ignored under data/. This utility is deliberately
small: it records local integrity/provenance, but does not certify scientific use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "samples" / "download-manifest.json"
CHUNK_BYTES = 1024 * 1024


def load_products(manifest_path: Path) -> dict[str, dict]:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if document.get("format_version") != "1" or not isinstance(document.get("products"), list):
        raise ValueError("Unsupported download manifest.")
    products = {item.get("id"): item for item in document["products"] if item.get("id")}
    if len(products) != len(document["products"]):
        raise ValueError("Download manifest contains duplicate or missing product IDs.")
    return products


def acquire(product: dict, *, allow_large: bool) -> Path:
    if product.get("status") not in {"verified_downloadable", "verified_downloadable_prototype_only"}:
        raise ValueError(f"{product['id']} is not eligible for download: {product.get('status')}")
    if product.get("large") and not allow_large:
        raise ValueError(f"{product['id']} is marked large ({product.get('provider_size')}); rerun only after approval with --allow-large.")
    destination = (ROOT / product["destination"]).resolve()
    if not destination.is_relative_to(ROOT / "data"):
        raise ValueError("Destination must stay under data/.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        raise ValueError(f"Refusing to overwrite incomplete file: {temporary}")
    request = Request(product["source_url"], headers={"User-Agent": "A-STELLAR-research/0.1"})
    digest = hashlib.sha256()
    total = 0
    try:
        with urlopen(request, timeout=60) as response, temporary.open("xb") as stream:
            resolved_url = response.geturl()
            if urlparse(resolved_url).hostname not in set(product["allowed_resolved_hosts"]):
                raise ValueError(f"Unexpected resolved host: {urlparse(resolved_url).hostname}")
            for chunk in iter(lambda: response.read(CHUNK_BYTES), b""):
                total += len(chunk)
                if total > int(product["max_bytes"]):
                    raise ValueError("Response exceeds the allowlisted size ceiling.")
                digest.update(chunk)
                stream.write(chunk)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    receipt = {
        "product_id": product["id"],
        "status": product["status"],
        "source_url": product["source_url"],
        "resolved_url": resolved_url,
        "provider_record_url": product["provider_record_url"],
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "bytes": total,
        "sha256": digest.hexdigest(),
        "manifest_path": str(DEFAULT_MANIFEST.relative_to(ROOT)),
        "identity": product["identity"],
        "coverage": product["coverage"],
        "coordinate_system": product["coordinate_system"],
        "resolution": product["resolution"],
        "units": product["units"],
        "limitations": product["limitations"],
    }
    receipt_path = ROOT / "data" / "cache" / "source-receipts" / f"{product['id']}.source.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    # Existing adapters validate adjacent receipts; retain the central index too.
    destination.with_name(destination.name + ".source.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Download verified A-STELLAR scientific products with source receipts.")
    parser.add_argument("product_id", nargs="+", help="Manifest product ID(s) to acquire")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--allow-large", action="store_true", help="Required for products marked multi-GB after human approval")
    args = parser.parse_args()
    products = load_products(args.manifest.resolve())
    for product_id in args.product_id:
        if product_id not in products:
            parser.error(f"Unknown product ID: {product_id}")
        try:
            print(acquire(products[product_id], allow_large=args.allow_large))
        except (OSError, ValueError) as error:
            parser.exit(1, f"Acquisition failed: {error}\n")


if __name__ == "__main__":
    main()
