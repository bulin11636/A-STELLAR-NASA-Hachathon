import os
import json
import argparse
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform
from rasterio.crs import CRS
from typing import TypedDict

DATA_ROOT = Path(__file__).resolve().parents[4] / "data"

class TraversabilityContext(TypedDict):
    status: str
    instrument: str
    spatial_context: str
    safety_summary: dict
    grid_file_path: str
    interpretation: str

class EdgeSurfaceAnalyzer:
    """
    Analyzes surface traversability on edge devices using local DEM/DTM GeoTIFF files.
    Implements memory-safe windowed reading (Lazy Loading) and dynamic CRS reprojection.
    """
    def __init__(self, local_tiff_path: str):
        """
        Initializes the analyzer with a local GeoTIFF file.
        
        Args:
            local_tiff_path (str): The file path to the local Digital Elevation Model (DEM) GeoTIFF.
        """
        if not os.path.exists(local_tiff_path):
            raise FileNotFoundError(f"Elevation map file not found: {local_tiff_path}")
        self.local_tiff_path = local_tiff_path
        self.mars_radius_m = 3389500.0 # Standard Mars radius in meters
        self.meters_per_degree = (2 * np.pi * self.mars_radius_m) / 360.0 

    def analyze_roi_local(
        self, 
        center_lon: float, 
        center_lat: float, 
        radius_m: float, 
        tile_size_m: float, 
        max_slope_deg: float = 15.0,
        output_directory: str | Path | None = None
    ) -> TraversabilityContext:
        """
        Analyzes the Region of Interest (ROI) and generates a traversability grid.
        
        Args:
            center_lon (float): Target longitude (EPSG:4326). Represents the X-coordinate of the rover or target location.
            center_lat (float): Target latitude (EPSG:4326). Represents the Y-coordinate of the rover or target location.
            radius_m (float): The scan radius in meters around the center coordinates, defining the total bounding box size.
            tile_size_m (float): The physical resolution of the safety grid in meters (e.g., 5.0 groups pixels into 5x5m navigational tiles).
            max_slope_deg (float): The maximum traversable slope threshold in degrees. Slopes exceeding this are flagged as hazards (default: 15.0).
        
        Returns:
            TraversabilityContext: A dictionary containing safety statistics, file paths, and LLM-ready interpretations.
        """
        try:
            with rasterio.open(self.local_tiff_path) as src:
                # 1. Coordinate Transformation
                # Define standard Mars Geographic CRS
                mars_geo_crs = CRS.from_string("+proj=longlat +R=3389500 +no_defs")
                
                # Convert input (Lon, Lat) to the target CRS of the GeoTIFF
                xs, ys = transform(mars_geo_crs, src.crs, [center_lon], [center_lat])
                center_x, center_y = xs[0], ys[0]

                # 2. Calculate Bounding Box and Resolution
                if src.crs.is_projected:
                    # GeoTIFF is in projected CRS (meters)
                    min_x, max_x = center_x - radius_m, center_x + radius_m
                    min_y, max_y = center_y - radius_m, center_y + radius_m
                    dx_m = src.res[0]
                    dy_m = abs(src.res[1])
                else:
                    # GeoTIFF is in geographic CRS (degrees)
                    radius_deg = radius_m / self.meters_per_degree
                    min_x, max_x = center_x - radius_deg, center_x + radius_deg
                    min_y, max_y = center_y - radius_deg, center_y + radius_deg
                    dx_m = src.res[0] * self.meters_per_degree
                    dy_m = abs(src.res[1]) * self.meters_per_degree

                # 3. JIT Windowed Reading (Lazy Loading)
                window = from_bounds(min_x, min_y, max_x, max_y, src.transform)
                window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                
                if window.width <= 0 or window.height <= 0:
                    raise ValueError(f"Transformed coordinates are completely outside the layer bounds. Check if ({center_lon}, {center_lat}) falls within this GeoTIFF.")

                # Read only the ROI into memory, applying the NoData mask
                roi_dem = src.read(1, window=window, masked=True)

            # 4. Metric Slope Calculation
            dy, dx = np.gradient(roi_dem, dy_m, dx_m)
            slope_deg = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))

            # 5. Tile Aggregation
            pixels_per_tile = max(1, int(tile_size_m / dx_m))
            tiles_y = slope_deg.shape[0] // pixels_per_tile
            tiles_x = slope_deg.shape[1] // pixels_per_tile
            
            safety_grid = np.zeros((tiles_y, tiles_x), dtype=np.float32)
            hazard_count, safe_count, nodata_count = 0, 0, 0

            for i in range(tiles_y):
                for j in range(tiles_x):
                    tile_data = slope_deg[i*pixels_per_tile:(i+1)*pixels_per_tile, j*pixels_per_tile:(j+1)*pixels_per_tile]
                    
                    if tile_data.mask.all():
                        # Assign infinity for missing data blocks
                        safety_grid[i, j] = np.inf
                        nodata_count += 1
                    else:
                        # Use the maximum slope within the tile for safety conservatism
                        max_slope = np.max(tile_data.compressed())
                        safety_grid[i, j] = max_slope
                        if max_slope > max_slope_deg: 
                            hazard_count += 1
                        else: 
                            safe_count += 1

            # 6. Export Data Plane for A* Navigation
            output_directory = Path(output_directory) if output_directory is not None else DATA_ROOT / "processed" / "a1"
            output_directory.mkdir(parents=True, exist_ok=True)
            output_grid_path = str(output_directory / f"a1_edge_grid_{center_lon}_{center_lat}.npy")
            np.save(output_grid_path, safety_grid)

            # 7. Generate Status Report
            total_valid = safe_count + hazard_count
            hazard_ratio = (hazard_count / total_valid * 100) if total_valid > 0 else 0.0
            instrument_name = "HiRISE (1m)" if "hirise" in self.local_tiff_path.lower() else "CTX (20m)"

            interpretation = (
                f"Terrain scan complete ({instrument_name}). "
                f"Within a {radius_m}m radius, {hazard_ratio:.1f}% of tiles exceed the {max_slope_deg}-degree hazard threshold."
            )

            return TraversabilityContext(
                status="complete",
                instrument=instrument_name,
                spatial_context=f"Center: ({center_lon}, {center_lat}), Radius: {radius_m}m",
                safety_summary={
                    "total_tiles": int(tiles_y * tiles_x), 
                    "safe_tiles": safe_count, 
                    "hazardous_tiles": hazard_count, 
                    "nodata_tiles": nodata_count
                },
                grid_file_path=output_grid_path,
                interpretation=interpretation
            )

        except Exception as e:
            return TraversabilityContext(
                status="unavailable", 
                instrument="Local DEM", 
                spatial_context=f"Center: ({center_lon}, {center_lat})",
                safety_summary={}, 
                grid_file_path="", 
                interpretation=f"Analysis failed: {str(e)}"
            )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A1 Traversability Edge Agent: Dynamic ROI slope analysis.")
    parser.add_argument("--tiff", type=str, default=str(DATA_ROOT / "raw/dem/M20_JezeroCrater_CTXDEM_20m.tif"), help="Path to the local DEM GeoTIFF file.")
    parser.add_argument("--lon", type=float, default=77.5, help="Target longitude (EPSG:4326).")
    parser.add_argument("--lat", type=float, default=18.4, help="Target latitude (EPSG:4326).")
    parser.add_argument("--radius", type=float, default=200.0, help="Scan radius in meters.")
    parser.add_argument("--tile", type=float, default=5.0, help="Safety grid tile size in meters.")
    args = parser.parse_args()

    agent = EdgeSurfaceAnalyzer(local_tiff_path=args.tiff)
    result = agent.analyze_roi_local(args.lon, args.lat, args.radius, args.tile)
    print(json.dumps(result, indent=4, ensure_ascii=False))
