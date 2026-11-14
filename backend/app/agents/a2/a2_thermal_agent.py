import os
import json
import argparse
from pathlib import Path
import rasterio
from typing import TypedDict, Optional

DATA_ROOT = Path(__file__).resolve().parents[4] / "data"

class ThermalContext(TypedDict):
    status: str
    instrument: str
    spatial_footprint: str
    day_temperature_c: Optional[float]
    material_prediction: str
    interpretation: str

class EdgeThermalAnalyzer:
    """
    Analyzes environmental thermal loads and surface material properties on edge devices
    using local THEMIS (Thermal Emission Imaging System) GeoTIFFs.
    Extracts Day IR for temperature simulation and Night IR for thermal inertia estimation.
    """
    def __init__(self, day_ir_path: str, night_ir_path: str):
        """
        Initializes the thermal analyzer with local THEMIS mosaics.
        
        Args:
            day_ir_path (str): File path to the THEMIS Daytime Infrared mosaic (simulates environmental temperature).
            night_ir_path (str): File path to the THEMIS Nighttime Infrared mosaic (indicates thermal inertia/materials).
        """
        self.day_ir_path = day_ir_path
        self.night_ir_path = night_ir_path

    def _sample_pixel(self, tiff_path: str, lon: float, lat: float) -> Optional[float]:
        """
        Extracts the precise Digital Number (DN) pixel value for a given coordinate.
        
        Args:
            tiff_path (str): The path to the specific GeoTIFF to sample.
            lon (float): Target longitude (EPSG:4326).
            lat (float): Target latitude (EPSG:4326).
            
        Returns:
            Optional[float]: The raw pixel value (DN or Radiance). Returns None if the coordinate 
                             is outside the layer bounds or corresponds to a NoData value.
        """
        if not os.path.exists(tiff_path):
            return None
        try:
            with rasterio.open(tiff_path) as src:
                # Check if the coordinate falls within the geographic bounds of the GeoTIFF
                if not (src.bounds.left <= lon <= src.bounds.right and src.bounds.bottom <= lat <= src.bounds.top):
                    return None
                
                # rasterio.sample returns a generator yielding arrays of pixel values across all bands
                for val in src.sample([(lon, lat)]):
                    pixel_val = val[0]
                    # NASA THEMIS layers often use large negative numbers or 0 as NoData masks
                    if pixel_val == src.nodata or pixel_val <= -9999:
                        return None
                    return float(pixel_val)
        except Exception as e:
            print(f"[A2 Error] Failed to sample THEMIS pixel: {e}")
            return None
        return None

    def analyze_environment(self, lon: float, lat: float) -> ThermalContext:
        """
        Executes dual-spectrum thermal analysis to estimate environmental temperature and surface material.
        
        Args:
            lon (float): Target longitude (EPSG:4326).
            lat (float): Target latitude (EPSG:4326).
            
        Returns:
            ThermalContext: A dictionary containing temperature estimates and material predictions 
                            for rover slip-risk mitigation.
        """
        day_dn = self._sample_pixel(self.day_ir_path, lon, lat)
        night_dn = self._sample_pixel(self.night_ir_path, lon, lat)

        # Scenario: No data available in either layer
        if day_dn is None and night_dn is None:
            return ThermalContext(
                status="unavailable", 
                instrument="THEMIS-IR (Day/Night)", 
                spatial_footprint=f"Lat: {lat}, Lon: {lon}",
                day_temperature_c=None, 
                material_prediction="Unknown",
                interpretation="[System Warning] No valid THEMIS thermal data for this region. Do not estimate temperatures or surface materials."
            )

        # 1. Process Day IR: Simulate Radiometric Calibration for Environmental Temperature
        day_temp_c = None
        if day_dn is not None:
            # Note for NIW documentation: This is a linear mapping placeholder for PoC demonstration.
            # In production, this would be replaced with Planck's Law and atmospheric correction models.
            # Assuming 8-bit DN (0-255) maps roughly to -100C to 20C during Martian daylight.
            day_temp_c = round(-100.0 + (min(max(day_dn, 0), 255) / 255.0) * 120.0, 1)

        # 2. Process Night IR: Thermal Inertia Analysis for Material Classification
        # Nighttime radiation indicates how well the material retains heat.
        material_guess = "Moderate Thermal Inertia (Mixed Regolith/Gravel)"
        if night_dn is not None:
            if night_dn > 180:
                # High Thermal Inertia: Retains heat well overnight
                material_guess = "High Thermal Inertia (Exposed Bedrock/Boulders) - Excellent traction, low slip risk, but poses puncture hazards to EVA suits."
            elif night_dn < 80:
                # Low Thermal Inertia: Loses heat rapidly after sunset
                material_guess = "Low Thermal Inertia (Deep Dust/Sand) - [CRITICAL HAZARD] High risk of rover slippage and entrapment."

        return ThermalContext(
            status="complete",
            instrument="THEMIS-IR Dual Fusion",
            spatial_footprint=f"Lat: {lat}, Lon: {lon}",
            day_temperature_c=day_temp_c,
            material_prediction=material_guess,
            interpretation=f"Thermal analysis complete. Estimated daytime surface temperature: {day_temp_c}°C. Nighttime thermal inertia indicates: {material_guess}"
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A2 Thermal & Material Edge Agent: Dual-spectrum thermal inertia analysis.")
    parser.add_argument("--day_tiff", type=str, default=str(DATA_ROOT / "raw/thermal/Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12.tif"), help="Path to Daytime THEMIS IR GeoTIFF.")
    parser.add_argument("--night_tiff", type=str, default=str(DATA_ROOT / "raw/thermal/THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018.tif"), help="Path to Nighttime THEMIS IR GeoTIFF.")
    parser.add_argument("--lon", type=float, default=77.5, help="Target longitude (EPSG:4326).")
    parser.add_argument("--lat", type=float, default=18.4, help="Target latitude (EPSG:4326).")
    args = parser.parse_args()

    agent = EdgeThermalAnalyzer(day_ir_path=args.day_tiff, night_ir_path=args.night_tiff)
    result = agent.analyze_environment(args.lon, args.lat)
    print(json.dumps(result, indent=4, ensure_ascii=False))
