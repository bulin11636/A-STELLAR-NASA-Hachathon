"""A1: opt-in standalone terrain prototype behind the shared worker API."""
from .worker import TraversabilityConfig, TraversabilityWorker

Worker = TraversabilityWorker

__all__ = ['Worker', 'TraversabilityConfig', 'TraversabilityWorker']
