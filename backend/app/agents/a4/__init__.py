"""A4: source-backed science opportunities and regional geology."""
from .mock import MockScienceWorker
from .worker import ScienceEvidenceWorker

Worker = ScienceEvidenceWorker

__all__ = ["Worker", "ScienceEvidenceWorker", "MockScienceWorker"]
