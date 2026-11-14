"""A2: opt-in thermal/material prototype behind the shared worker API."""
from .worker import ThermalConfig, ThermalWorker

Worker = ThermalWorker

__all__ = ['Worker', 'ThermalConfig', 'ThermalWorker']
