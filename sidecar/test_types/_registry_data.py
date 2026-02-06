"""
All generic (keyword + LLM) test type definitions.

Each entry is a GenericTestType with an ID, display name, keywords,
specialty, and category.  Imported by __init__.py and registered in bulk.
"""

from __future__ import annotations

from .generic import GenericTestType
from .extractors.dexa import (
    extract_dexa_measurements,
    DEXA_REFERENCE_RANGES,
    DEXA_GLOSSARY,
)
from .extractors.mammography import (
    extract_mammography_measurements,
    MAMMOGRAPHY_REFERENCE_RANGES,
    MAMMOGRAPHY_GLOSSARY,
)

# ---------------------------------------------------------------------------
# Cardiac
# ---------------------------------------------------------------------------
_CARDIAC: list[GenericTestType] = [
    GenericTestType("cta_coronary", "CTA Coronary", [
        "cta", "ct angiography", "coronary ct", "coronary cta", "ct coronary",
        "calcium score", "agatston",
    ], category="cardiac"),
    GenericTestType("cardiac_mri", "Cardiac MRI", [
        "cardiac mri", "cardiac magnetic", "cmr", "myocardial",
        "late gadolinium", "t1 mapping", "t2 mapping",
    ], category="cardiac"),
    GenericTestType("ekg", "EKG / ECG", [
        "ekg", "ecg", "electrocardiogram", "12-lead", "12 lead",
        "sinus rhythm", "qrs", "qt interval", "st segment",
    ], category="cardiac"),
    GenericTestType("holter_monitor", "Holter Monitor", [
        "holter", "ambulatory monitor", "24-hour monitor", "48-hour monitor",
        "event monitor", "continuous monitoring",
    ], category="cardiac"),
    GenericTestType("nuclear_stress", "Nuclear Stress Test", [
        "nuclear stress", "myocardial perfusion", "spect", "sestamibi",
        "lexiscan", "adenosine stress", "regadenoson", "persantine",
        "pharmacologic stress", "nuclear cardiology",
    ], category="cardiac"),
    GenericTestType("right_heart_cath", "Right Heart Catheterization", [
        "right heart cath", "right heart catheterization", "swan-ganz",
        "pulmonary artery pressure", "pulmonary capillary wedge",
        "pcwp", "cardiac output", "fick",
    ], category="cardiac"),
    GenericTestType("left_heart_cath", "Left Heart Catheterization", [
        "left heart cath", "coronary angiography", "coronary angiogram",
        "cardiac catheterization", "cardiac cath", "lvedp",
        "coronary arteries", "left main", "lad", "circumflex", "rca",
    ], category="cardiac"),
    GenericTestType("ct_calcium_score", "CT Calcium Score", [
        "calcium score", "agatston score", "coronary calcium",
        "cac score", "calcium scoring",
    ], category="cardiac"),
    GenericTestType("tee", "Transesophageal Echocardiogram", [
        "transesophageal", "tee", "tee echo",
    ], category="cardiac"),
    GenericTestType("event_monitor", "Event Monitor", [
        "event monitor", "event recorder", "loop recorder",
        "zio patch", "cardiac monitor",
    ], category="cardiac"),
]

# ---------------------------------------------------------------------------
# CT Imaging
# ---------------------------------------------------------------------------
_IMAGING_CT: list[GenericTestType] = [
    GenericTestType("ct_chest", "CT Chest", [
        "ct chest", "chest ct", "ct thorax", "pulmonary embolism",
        "ct pulmonary", "ctpa",
    ], specialty="radiology", category="imaging_ct"),
    GenericTestType("ct_scan", "CT Scan", [
        "ct scan", "computed tomography",
        "ct head", "ct brain", "ct abdomen", "ct pelvis",
        "ct spine", "ct cervical", "ct lumbar", "ct thoracic",
        "ct extremity", "ct neck", "ct sinus",
        "ct without contrast", "ct with contrast",
    ], specialty="radiology", category="imaging_ct"),
    GenericTestType("cta", "CT Angiography", [
        "ct angiography", "cta pulmonary", "cta aorta", "cta carotid",
        "cta renal", "cta extremity", "cta runoff", "ct angiogram",
    ], specialty="radiology", category="imaging_ct"),
]

# ---------------------------------------------------------------------------
# MRI
# ---------------------------------------------------------------------------
_IMAGING_MRI: list[GenericTestType] = [
    GenericTestType("mri", "MRI", [
        "mri", "magnetic resonance imaging",
        "mri brain", "mri spine", "mri knee", "mri shoulder",
        "mri hip", "mri ankle", "mri wrist",
        "mri abdomen", "mri pelvis",
        "mri cervical", "mri lumbar", "mri thoracic",
    ], specialty="radiology", category="imaging_mri"),
    GenericTestType("mra", "MR Angiography", [
        "mra", "mr angiography", "magnetic resonance angiography",
        "mra brain", "mra neck", "mra aorta", "mra renal",
    ], specialty="radiology", category="imaging_mri"),
]

# ---------------------------------------------------------------------------
# Ultrasound
# ---------------------------------------------------------------------------
_IMAGING_ULTRASOUND: list[GenericTestType] = [
    GenericTestType("renal_artery_doppler", "Renal Artery Doppler", [
        "renal artery", "renal doppler", "renal ultrasound",
        "renal resistive index",
    ], category="imaging_ultrasound"),
    GenericTestType("abdominal_aorta", "Abdominal Aorta Ultrasound", [
        "abdominal aorta", "aaa screening", "aortic aneurysm",
        "aortic ultrasound", "aortic diameter",
    ], category="imaging_ultrasound"),
    GenericTestType("ultrasound", "Ultrasound", [
        "ultrasound", "sonography", "sonogram",
        "thyroid ultrasound", "renal ultrasound", "pelvic ultrasound",
        "obstetric ultrasound", "breast ultrasound", "abdominal ultrasound",
        "testicular ultrasound", "scrotal ultrasound", "soft tissue ultrasound",
    ], specialty="radiology", category="imaging_ultrasound"),
]

# ---------------------------------------------------------------------------
# X-Ray
# ---------------------------------------------------------------------------
_IMAGING_XRAY: list[GenericTestType] = [
    GenericTestType("chest_xray", "Chest X-Ray", [
        "chest x-ray", "chest xray", "cxr", "chest radiograph",
        "pa and lateral", "portable chest",
    ], specialty="radiology", category="imaging_xray"),
    GenericTestType("xray", "X-Ray", [
        "x-ray", "radiograph", "plain film", "skeletal survey",
        "bone xray", "spine xray", "abdominal xray", "kub",
        "knee xray", "shoulder xray", "hip xray",
        "ankle xray", "hand xray", "foot xray",
    ], specialty="radiology", category="imaging_xray"),
    GenericTestType(
        "dexa",
        "DEXA / Bone Density",
        [
            "dexa", "dxa", "bone density", "bone densitometry",
            "dual-energy x-ray absorptiometry",
            "t-score", "z-score", "osteoporosis screening",
        ],
        specialty="radiology",
        category="imaging_xray",
        measurement_extractor=extract_dexa_measurements,
        reference_ranges=DEXA_REFERENCE_RANGES,
        glossary=DEXA_GLOSSARY,
    ),
    GenericTestType(
        "mammography",
        "Mammography",
        [
            "mammography", "mammogram", "breast imaging",
            "bi-rads", "birads", "screening mammogram",
            "diagnostic mammogram", "tomosynthesis",
        ],
        specialty="radiology",
        category="imaging_xray",
        measurement_extractor=extract_mammography_measurements,
        reference_ranges=MAMMOGRAPHY_REFERENCE_RANGES,
        glossary=MAMMOGRAPHY_GLOSSARY,
    ),
]

# ---------------------------------------------------------------------------
# Pulmonary
# ---------------------------------------------------------------------------
_PULMONARY: list[GenericTestType] = [
    GenericTestType("pft", "Pulmonary Function Test", [
        "pulmonary function", "pft", "spirometry", "fev1", "fvc",
        "dlco", "lung volumes",
    ], specialty="pulmonology", category="pulmonary"),
    GenericTestType("sleep_study", "Sleep Study", [
        "polysomnography", "sleep study", "polysomnogram",
        "sleep apnea", "ahi", "apnea-hypopnea", "apnea hypopnea",
    ], specialty="pulmonology", category="neurophysiology"),
]

# ---------------------------------------------------------------------------
# Neurophysiology
# ---------------------------------------------------------------------------
_NEUROPHYSIOLOGY: list[GenericTestType] = [
    GenericTestType("eeg", "EEG", [
        "eeg", "electroencephalogram", "electroencephalography",
        "brain wave", "epilepsy monitoring", "seizure study",
    ], specialty="neurology", category="neurophysiology"),
    GenericTestType("emg_ncs", "EMG / Nerve Conduction Study", [
        "emg", "electromyography", "nerve conduction", "ncs",
        "nerve conduction study", "electrodiagnostic",
    ], specialty="neurology", category="neurophysiology"),
]

# ---------------------------------------------------------------------------
# Endoscopy
# ---------------------------------------------------------------------------
_ENDOSCOPY: list[GenericTestType] = [
    GenericTestType("endoscopy", "Endoscopy / Colonoscopy", [
        "colonoscopy", "endoscopy", "egd",
        "esophagogastroduodenoscopy", "upper endoscopy",
        "sigmoidoscopy", "polypectomy", "gastroscopy", "bronchoscopy",
    ], specialty="gastroenterology", category="endoscopy"),
]

# ---------------------------------------------------------------------------
# Pathology
# ---------------------------------------------------------------------------
_PATHOLOGY: list[GenericTestType] = [
    GenericTestType("pathology", "Pathology / Biopsy Report", [
        "pathology", "biopsy", "histopathology", "cytology",
        "surgical pathology", "microscopic examination",
        "immunohistochemistry", "pap smear",
    ], specialty="pathology", category="pathology"),
]

# ---------------------------------------------------------------------------
# Public export — order matters: more-specific types first so that keyword
# detection naturally prefers them over broad modality-level types.
# ---------------------------------------------------------------------------
GENERIC_TYPES: list[GenericTestType] = [
    *_CARDIAC,
    *_IMAGING_CT,
    *_IMAGING_MRI,
    *_IMAGING_ULTRASOUND,
    *_IMAGING_XRAY,
    *_PULMONARY,
    *_NEUROPHYSIOLOGY,
    *_ENDOSCOPY,
    *_PATHOLOGY,
]
