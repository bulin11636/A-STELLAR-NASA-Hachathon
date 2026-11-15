"""Download a bounded NASA Jezero WMTS mosaic as a QGIS-ready visual reference.

This utility never verifies registration. The output is a planetographic WMTS
image intended for independent feature picking beside a local DEM; it is not a
replacement for the immutable capability/measurement evidence package.
"""
from __future__ import annotations

import argparse
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

LAYER = "NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018"
CAPABILITIES = f"https://trek.nasa.gov/tiles/Mars/EQ/{LAYER}/1.0.0/WMTSCapabilities.xml"
TILE = f"https://trek.nasa.gov/tiles/Mars/EQ/{LAYER}/1.0.0//default/default028mm/{{z}}/{{row}}/{{col}}.png"
LAYER_BOUNDS = (76.7912789, 17.5791654, 77.7314417, 18.6926322)  # NASA-published planetographic degrees


def planetographic(latitude: float) -> float:
    semi_major = 3396190.0
    semi_minor = semi_major * (1 - 1 / 169.894447223612)
    return math.degrees(math.atan((semi_major / semi_minor) ** 2 * math.tan(math.radians(latitude))))


def dem_bounds_planetographic(path: Path) -> tuple[float, float, float, float]:
    with rasterio.open(path) as dataset:
        crs = CRS.from_wkt(dataset.crs.to_wkt())
        transformer = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        bounds = dataset.bounds
        corners = [transformer.transform(x, y) for x, y in (
            (bounds.left, bounds.bottom), (bounds.left, bounds.top),
            (bounds.right, bounds.bottom), (bounds.right, bounds.top),
        )]
    longitudes = [point[0] for point in corners]
    latitudes = [planetographic(point[1]) for point in corners]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if west >= east or south >= north:
        raise ValueError("The DEM does not intersect the advertised NASA Jezero mosaic coverage.")
    return west, south, east, north


def tile_range(bounds: tuple[float, float, float, float], zoom: int) -> tuple[int, int, int, int]:
    columns, rows = 2 ** (zoom + 1), 2 ** zoom
    west, south, east, north = bounds
    col0 = max(0, min(columns - 1, math.floor((west + 180) / 360 * columns)))
    col1 = max(0, min(columns - 1, math.floor((east + 180) / 360 * columns)))
    row0 = max(0, min(rows - 1, math.floor((90 - north) / 180 * rows)))
    row1 = max(0, min(rows - 1, math.floor((90 - south) / 180 * rows)))
    return col0, row0, col1, row1


def fetch_tile(zoom: int, row: int, col: int) -> tuple[int, int, np.ndarray]:
    request = Request(TILE.format(z=zoom, row=row, col=col), headers={"User-Agent": "A-STELLAR-registration-preview/1"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f"NASA tile {zoom}/{row}/{col} returned HTTP {response.status}")
        payload = response.read()
    with MemoryFile(payload) as memory:
        with memory.open() as dataset:
            if dataset.width != 256 or dataset.height != 256 or dataset.count < 1:
                raise ValueError(f"NASA tile {zoom}/{row}/{col} has unexpected raster dimensions/bands")
            if dataset.count < 3:
                image = np.repeat(dataset.read(1)[..., None], 3, axis=2)
            else:
                image = np.moveaxis(dataset.read([1, 2, 3]), 0, -1)
    return row, col, image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dem", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--capabilities-output", required=True, type=Path)
    parser.add_argument("--zoom", type=int, default=12, choices=range(0, 18))
    parser.add_argument("--workers", type=int, default=8, choices=range(1, 17))
    args = parser.parse_args()
    dem_bounds = dem_bounds_planetographic(args.dem)
    bounds = intersect(dem_bounds, LAYER_BOUNDS)
    col0, row0, col1, row1 = tile_range(bounds, args.zoom)
    tile_count = (col1 - col0 + 1) * (row1 - row0 + 1)
    if tile_count > 800:
        raise ValueError(f"Refusing to download {tile_count} tiles; choose a lower zoom.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.capabilities_output.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(Request(CAPABILITIES, headers={"User-Agent": "A-STELLAR-registration-preview/1"}), timeout=30) as response:
        args.capabilities_output.write_bytes(response.read())
    rows, cols = row1 - row0 + 1, col1 - col0 + 1
    mosaic = np.zeros((rows * 256, cols * 256, 3), dtype=np.uint8)
    futures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in range(row0, row1 + 1):
            for col in range(col0, col1 + 1):
                futures.append(pool.submit(fetch_tile, args.zoom, row, col))
        for future in as_completed(futures):
            row, col, image = future.result()
            top, left = (row - row0) * 256, (col - col0) * 256
            mosaic[top:top + 256, left:left + 256] = image
    columns, _ = 2 ** (args.zoom + 1), 2 ** args.zoom
    degrees_per_pixel = 360 / (columns * 256)
    west = -180 + col0 * 256 * degrees_per_pixel
    north = 90 - row0 * 256 * degrees_per_pixel
    transform = from_origin(west, north, degrees_per_pixel, degrees_per_pixel)
    with rasterio.open(args.output, "w", driver="GTiff", width=mosaic.shape[1], height=mosaic.shape[0], count=3,
                       dtype="uint8", crs="ESRI:104905", transform=transform, compress="deflate", tiled=True) as target:
        target.write(np.moveaxis(mosaic, -1, 0))
        target.update_tags(source_layer=LAYER, source_capabilities=CAPABILITIES,
                           purpose="Visual reference for independent feature picking; not registration verification.",
                           wmts_zoom=args.zoom, coverage_planetographic=str(bounds))
    print(f"Downloaded {tile_count} tiles at zoom {args.zoom}.")
    print(f"Preview: {args.output}")
    print(f"Capabilities: {args.capabilities_output}")
    print(f"Coverage (planetographic): {bounds}")


if __name__ == "__main__":
    main()
