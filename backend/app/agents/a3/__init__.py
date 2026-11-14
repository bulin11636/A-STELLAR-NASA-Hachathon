"""A3: explicit mission-level radiation scenarios; no raster model."""
from .mock import MockRadiationWorker
from .worker import RadiationScenario, ScenarioRadiationWorker

Worker = ScenarioRadiationWorker

__all__ = ["Worker", "RadiationScenario", "ScenarioRadiationWorker", "MockRadiationWorker"]
