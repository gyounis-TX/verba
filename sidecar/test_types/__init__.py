from .registry import TestTypeRegistry
from .echo import EchocardiogramHandler
from .labs import LabResultsHandler
from .stress import StressTestHandler
from .carotid import CarotidDopplerHandler
from .arterial import ArterialDopplerHandler
from .venous import VenousDopplerHandler
from .coronary_diagram import CoronaryDiagramHandler
from .cardiac_mri import CardiacMRIHandler
from .right_heart_cath import RightHeartCathHandler
from .tee import TEEHandler
from .cta_coronary import CTACoronaryHandler
from .pft import PFTHandler
from ._registry_data import GENERIC_TYPES

registry = TestTypeRegistry()

# Specialized handlers (with structured measurement parsing)
registry.register(EchocardiogramHandler())
registry.register(LabResultsHandler())
_stress_handler = StressTestHandler()
registry.register(_stress_handler)
registry.register(CarotidDopplerHandler())
registry.register(ArterialDopplerHandler())
registry.register(VenousDopplerHandler())
registry.register(CoronaryDiagramHandler())
registry.register(CardiacMRIHandler())
registry.register(RightHeartCathHandler())
registry.register(TEEHandler())
registry.register(CTACoronaryHandler())
registry.register(PFTHandler())

# Register stress subtype IDs so they resolve to the family handler
for _subtype_id in (
    "exercise_treadmill_test", "pharma_spect_stress", "exercise_spect_stress",
    "pharma_pet_stress", "exercise_pet_stress",
    "exercise_stress_echo", "pharma_stress_echo",
):
    registry.register_subtype(_subtype_id, _stress_handler)

# Generic keyword + LLM types (defined in _registry_data.py)
for gt in GENERIC_TYPES:
    registry.register(gt)

__all__ = ["registry", "TestTypeRegistry"]
