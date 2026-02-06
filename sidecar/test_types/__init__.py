from .registry import TestTypeRegistry
from .echo import EchocardiogramHandler
from .labs import LabResultsHandler
from .stress import StressTestHandler
from .carotid import CarotidDopplerHandler
from .arterial import ArterialDopplerHandler
from .venous import VenousDopplerHandler
from ._registry_data import GENERIC_TYPES

registry = TestTypeRegistry()

# Specialized handlers (with structured measurement parsing)
registry.register(EchocardiogramHandler())
registry.register(LabResultsHandler())
registry.register(StressTestHandler())
registry.register(CarotidDopplerHandler())
registry.register(ArterialDopplerHandler())
registry.register(VenousDopplerHandler())

# Generic keyword + LLM types (defined in _registry_data.py)
for gt in GENERIC_TYPES:
    registry.register(gt)

__all__ = ["registry", "TestTypeRegistry"]
