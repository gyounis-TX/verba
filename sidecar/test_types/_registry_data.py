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
from .extractors.cardiac_pet import (
    extract_cardiac_pet_measurements,
    CARDIAC_PET_REFERENCE_RANGES,
    CARDIAC_PET_GLOSSARY,
)
from .labs.lab_extractor import extract_lab_measurements

# ---------------------------------------------------------------------------
# Cardiac
# ---------------------------------------------------------------------------
_CARDIAC: list[GenericTestType] = [
    GenericTestType("cta_coronary", "CTA Coronary", [
        "cta", "ct angiography", "coronary ct", "coronary cta", "ct coronary",
        "calcium score", "agatston",
    ], category="cardiac",
        negative_keywords=["pulmonary embolism", "ctpa"],
    ),
    GenericTestType("cardiac_mri", "Cardiac MRI", [
        "cardiac mri", "cardiac magnetic", "cmr", "myocardial",
        "late gadolinium", "t1 mapping", "t2 mapping",
        "mr cardiac", "mri cardiac", "mri heart",
        "delayed enhancement", "gadolinium", "cine imaging", "t2 stir",
    ], category="cardiac",
        negative_keywords=["echocardiogram", "echocardiography", "transthoracic"],
    ),
    GenericTestType("ekg", "EKG / ECG", [
        "ekg", "ecg", "electrocardiogram", "12-lead", "12 lead",
        "sinus rhythm", "qrs", "qt interval", "st segment",
    ], category="cardiac",
        negative_keywords=["echocardiogram", "echocardiography", "transthoracic", "wall motion"],
    ),
    GenericTestType("holter_monitor", "Holter Monitor", [
        "holter", "ambulatory monitor", "24-hour monitor", "48-hour monitor",
        "event monitor", "continuous monitoring",
    ], category="cardiac",
        negative_keywords=["stress test", "exercise"],
    ),
    # Stress test subtypes — these provide dropdown entries and LLM detection
    # listings. The StressFamilyHandler (registered separately) handles actual
    # detection with higher confidence, so these generic entries serve as
    # fallback and type-listing purposes.
    GenericTestType("exercise_treadmill_test", "Exercise Treadmill Test", [
        "exercise treadmill", "treadmill test", "exercise stress test",
        "bruce protocol", "exercise tolerance test", "graded exercise test",
        "exercise ecg", "exercise ekg",
    ], category="cardiac",
        negative_keywords=["spect", "sestamibi", "nuclear", "pet/ct", "dobutamine"],
    ),
    GenericTestType("pharma_spect_stress", "Pharmacologic SPECT Nuclear Stress", [
        "pharmacologic stress", "lexiscan", "regadenoson", "adenosine stress",
        "spect", "sestamibi", "myocardial perfusion", "nuclear stress",
    ], category="cardiac"),
    GenericTestType("exercise_spect_stress", "Exercise SPECT Nuclear Stress", [
        "exercise spect", "exercise nuclear", "exercise myocardial perfusion",
        "spect", "sestamibi", "treadmill nuclear",
    ], category="cardiac"),
    GenericTestType("pharma_pet_stress", "Pharmacologic PET/PET-CT Stress", [
        "cardiac pet", "pet/ct", "pet-ct", "rb-82", "rubidium", "positron",
        "n-13 ammonia", "myocardial blood flow", "mbf", "coronary flow reserve",
        "pharmacologic", "lexiscan", "regadenoson", "adenosine",
    ], category="cardiac",
        measurement_extractor=extract_cardiac_pet_measurements,
        reference_ranges=CARDIAC_PET_REFERENCE_RANGES,
        glossary=CARDIAC_PET_GLOSSARY,
    ),
    GenericTestType("exercise_pet_stress", "Exercise PET/PET-CT Stress", [
        "cardiac pet", "pet/ct", "pet-ct", "rb-82", "rubidium", "positron",
        "exercise", "treadmill", "myocardial blood flow", "mbf",
    ], category="cardiac",
        measurement_extractor=extract_cardiac_pet_measurements,
        reference_ranges=CARDIAC_PET_REFERENCE_RANGES,
        glossary=CARDIAC_PET_GLOSSARY,
    ),
    GenericTestType("exercise_stress_echo", "Exercise Stress Echocardiogram", [
        "stress echocardiogram", "stress echo", "exercise echo",
        "bicycle stress", "treadmill echo", "exercise echocardiogram",
        "wall motion at stress",
    ], category="cardiac"),
    GenericTestType("pharma_stress_echo", "Pharmacologic Stress Echocardiogram", [
        "dobutamine stress", "dobutamine echo", "dobutamine echocardiogram",
        "pharmacologic stress echocardiogram", "pharmacologic echo",
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
# Interventional / Procedures
# ---------------------------------------------------------------------------
_INTERVENTIONAL: list[GenericTestType] = [
    GenericTestType("pci", "PCI / Coronary Intervention", [
        "percutaneous coronary intervention", "stent", "ptca",
        "drug-eluting stent", "bare metal stent", "balloon angioplasty",
    ], category="interventional"),
    GenericTestType("ep_study", "EP Study / Ablation", [
        "electrophysiology", "ablation", "pulmonary vein isolation",
        "ep study", "electrophysiology study", "catheter ablation",
        "radiofrequency ablation", "cryoablation",
    ], category="interventional"),
    GenericTestType("pacemaker_check", "Pacemaker / ICD Check", [
        "pacemaker", "icd", "device interrogation",
        "pacemaker check", "icd check", "device check",
        "crt", "cardiac resynchronization",
    ], category="interventional"),
    GenericTestType("ffr_ifr", "FFR / iFR", [
        "fractional flow reserve", "pressure wire", "ffr", "ifr",
        "instantaneous wave-free ratio",
    ], category="interventional"),
    GenericTestType("ivus", "IVUS", [
        "intravascular ultrasound", "ivus",
    ], category="interventional"),
    GenericTestType("peripheral_intervention", "Peripheral Angiogram / Intervention", [
        "pta", "peripheral stent", "iliac stent", "sfa",
        "peripheral angiogram", "peripheral angioplasty",
        "lower extremity angiogram", "upper extremity angiogram",
    ], category="interventional"),
    GenericTestType("aortogram", "Aortogram", [
        "aortogram", "aortography",
    ], category="interventional"),
    GenericTestType("venogram", "Venogram", [
        "venogram", "venography",
    ], category="interventional"),
    GenericTestType("embolization", "Embolization Procedure", [
        "embolization", "coil embolization", "tace",
        "y-90", "yttrium-90", "radioembolization",
    ], category="interventional"),
    GenericTestType("tips", "TIPS Procedure", [
        "tips", "portosystemic shunt",
        "transjugular intrahepatic portosystemic",
    ], category="interventional"),
    GenericTestType("ivc_filter", "IVC Filter", [
        "ivc filter", "retrievable filter",
        "inferior vena cava filter",
    ], category="interventional"),
    GenericTestType("fistulogram", "Dialysis Access Intervention", [
        "fistulogram", "av fistula", "dialysis access",
        "arteriovenous fistula", "graft thrombectomy",
    ], category="interventional"),
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
        "cta mesenteric", "cta visceral", "cta iliac", "cta peripheral",
        "cta lower extremity", "cta upper extremity",
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
        "mra carotid", "mra mesenteric", "mra visceral",
        "mra peripheral", "mra iliac", "mra runoff",
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
    GenericTestType("upper_extremity_arterial_duplex", "Upper Extremity Arterial Duplex", [
        "upper extremity arterial", "arm arterial duplex",
        "subclavian duplex", "brachial duplex",
    ], category="imaging_ultrasound"),
    GenericTestType("upper_extremity_venous_duplex", "Upper Extremity Venous Duplex", [
        "upper extremity venous", "arm venous duplex",
        "subclavian vein", "axillary vein duplex",
    ], category="imaging_ultrasound"),
    GenericTestType("mesenteric_doppler", "Mesenteric Doppler", [
        "mesenteric doppler", "celiac doppler", "sma doppler",
        "mesenteric duplex", "celiac artery duplex",
    ], category="imaging_ultrasound"),
    GenericTestType("aortic_stent_surveillance", "Aortic Stent Surveillance", [
        "evar surveillance", "aortic stent graft", "endoleak",
        "aortic stent surveillance", "tevar surveillance",
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
# Vascular
# ---------------------------------------------------------------------------
_VASCULAR: list[GenericTestType] = [
    GenericTestType("carotid_duplex", "Carotid Duplex", [
        "carotid duplex", "carotid ultrasound", "carotid doppler",
        "carotid stenosis", "ica velocity", "cca",
    ], specialty="vascular", category="vascular"),
    GenericTestType("lower_extremity_arterial_duplex", "Lower Extremity Arterial Duplex", [
        "lower extremity arterial", "leg arterial duplex",
        "femoral duplex", "popliteal duplex", "tibial duplex",
        "peripheral arterial duplex",
    ], specialty="vascular", category="vascular"),
    GenericTestType("lower_extremity_venous_duplex", "Lower Extremity Venous Duplex", [
        "lower extremity venous", "leg venous duplex", "dvt",
        "deep vein thrombosis", "femoral vein", "popliteal vein",
        "venous duplex lower", "venous insufficiency",
    ], specialty="vascular", category="vascular"),
    GenericTestType("abi", "Ankle-Brachial Index", [
        "ankle brachial index", "abi", "ankle-brachial",
        "segmental pressures", "pulse volume recording", "pvr",
    ], specialty="vascular", category="vascular"),
]

# ---------------------------------------------------------------------------
# Laboratory — General
# ---------------------------------------------------------------------------
_LAB_GENERAL: list[GenericTestType] = [
    GenericTestType("cbc", "Complete Blood Count", [
        "complete blood count", "cbc", "hemoglobin", "hematocrit",
        "white blood cell", "wbc", "platelet count", "mcv", "mch",
    ], specialty="internal_medicine", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("bmp", "Basic Metabolic Panel", [
        "basic metabolic panel", "bmp", "sodium", "potassium",
        "chloride", "bicarbonate", "bun", "creatinine", "glucose",
    ], specialty="internal_medicine", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("cmp", "Comprehensive Metabolic Panel", [
        "comprehensive metabolic panel", "cmp", "total protein",
        "albumin", "bilirubin", "alkaline phosphatase", "alt", "ast",
    ], specialty="internal_medicine", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("urinalysis", "Urinalysis", [
        "urinalysis", "urine analysis", "urine dipstick",
        "specific gravity", "urine protein", "urine glucose",
    ], specialty="internal_medicine", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("coagulation", "Coagulation Panel", [
        "coagulation", "pt", "inr", "ptt", "aptt",
        "prothrombin time", "fibrinogen", "d-dimer",
    ], specialty="internal_medicine", category="lab", measurement_extractor=extract_lab_measurements),
]

# ---------------------------------------------------------------------------
# Laboratory — Endocrine
# ---------------------------------------------------------------------------
_LAB_ENDOCRINE: list[GenericTestType] = [
    GenericTestType("thyroid_panel", "Thyroid Panel", [
        "thyroid panel", "tsh", "free t4", "free t3",
        "thyroid function", "thyroid stimulating",
    ], specialty="endocrinology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("hba1c", "HbA1c", [
        "hba1c", "hemoglobin a1c", "glycated hemoglobin",
        "a1c", "glycosylated hemoglobin",
    ], specialty="endocrinology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("cortisol", "Cortisol", [
        "cortisol", "am cortisol", "cortisol level",
        "acth stimulation", "dexamethasone suppression",
    ], specialty="endocrinology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("hormone_panel", "Hormone Panel", [
        "hormone panel", "testosterone", "estradiol",
        "fsh", "lh", "prolactin", "dhea", "igf-1",
    ], specialty="endocrinology", category="lab", measurement_extractor=extract_lab_measurements),
]

# ---------------------------------------------------------------------------
# Laboratory — Rheumatology
# ---------------------------------------------------------------------------
_LAB_RHEUMATOLOGY: list[GenericTestType] = [
    GenericTestType("ana_panel", "ANA Panel", [
        "ana panel", "antinuclear antibody", "ana",
        "anti-dsdna", "ena panel", "smith antibody",
    ], specialty="rheumatology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("rheumatoid_panel", "Rheumatoid Panel", [
        "rheumatoid factor", "anti-ccp", "rheumatoid panel",
        "cyclic citrullinated peptide",
    ], specialty="rheumatology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("inflammatory_markers", "Inflammatory Markers", [
        "esr", "crp", "sed rate", "c-reactive protein",
        "erythrocyte sedimentation rate", "inflammatory markers",
    ], specialty="rheumatology", category="lab", measurement_extractor=extract_lab_measurements),
]

# ---------------------------------------------------------------------------
# Laboratory — Hematology
# ---------------------------------------------------------------------------
_LAB_HEMATOLOGY: list[GenericTestType] = [
    GenericTestType("iron_studies", "Iron Studies", [
        "iron studies", "ferritin", "iron saturation", "tibc",
        "serum iron", "transferrin saturation",
    ], specialty="hematology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("hemoglobin_electrophoresis", "Hemoglobin Electrophoresis", [
        "hemoglobin electrophoresis", "hb electrophoresis",
        "sickle cell screen", "thalassemia screen",
    ], specialty="hematology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("tumor_markers", "Tumor Markers", [
        "tumor markers", "psa", "cea", "ca-125", "ca 19-9",
        "afp", "beta hcg", "ldh tumor",
    ], specialty="hematology", category="lab", measurement_extractor=extract_lab_measurements),
]

# ---------------------------------------------------------------------------
# Laboratory — Hepatology
# ---------------------------------------------------------------------------
_LAB_HEPATOLOGY: list[GenericTestType] = [
    GenericTestType("hepatic_panel", "Hepatic Panel", [
        "hepatic panel", "liver function", "hepatic function",
        "ggtp", "ggt", "direct bilirubin", "indirect bilirubin",
    ], specialty="hepatology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("hepatitis_serology", "Hepatitis Serology", [
        "hepatitis serology", "hepatitis b", "hepatitis c",
        "hbsag", "anti-hbs", "anti-hcv", "hcv rna", "hbv dna",
    ], specialty="hepatology", category="lab", measurement_extractor=extract_lab_measurements),
]

# ---------------------------------------------------------------------------
# Laboratory — Nephrology
# ---------------------------------------------------------------------------
_LAB_NEPHROLOGY: list[GenericTestType] = [
    GenericTestType("renal_function", "Renal Function Panel", [
        "renal function", "renal panel", "gfr", "egfr",
        "cystatin c", "urine albumin creatinine ratio",
        "microalbumin", "24-hour urine protein",
    ], specialty="nephrology", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("urine_studies", "Urine Studies", [
        "urine studies", "24-hour urine", "urine electrolytes",
        "urine osmolality", "urine sodium", "fractional excretion",
    ], specialty="nephrology", category="lab", measurement_extractor=extract_lab_measurements),
]

# ---------------------------------------------------------------------------
# Laboratory — Infectious Disease
# ---------------------------------------------------------------------------
_LAB_INFECTIOUS: list[GenericTestType] = [
    GenericTestType("blood_cultures", "Blood Cultures", [
        "blood cultures", "blood culture", "bacteremia",
        "gram stain", "sensitivity", "susceptibility",
    ], specialty="infectious_disease", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("sti_panel", "STI Panel", [
        "sti panel", "std panel", "chlamydia", "gonorrhea",
        "syphilis", "rpr", "vdrl", "hiv", "herpes",
    ], specialty="infectious_disease", category="lab", measurement_extractor=extract_lab_measurements),
    GenericTestType("serology_panel", "Serology Panel", [
        "serology panel", "igg", "igm", "titer",
        "antibody panel", "immunoglobulin", "quantiferon",
        "tb gold", "lyme serology",
    ], specialty="infectious_disease", category="lab", measurement_extractor=extract_lab_measurements),
]

# ---------------------------------------------------------------------------
# Allergy
# ---------------------------------------------------------------------------
_ALLERGY: list[GenericTestType] = [
    GenericTestType("allergy_testing", "Allergy Testing", [
        "allergy testing", "skin prick test", "allergen",
        "rast test", "specific ige", "allergy panel",
        "environmental allergies", "food allergies",
    ], specialty="allergy", category="allergy"),
    GenericTestType("immunoglobulins", "Immunoglobulins", [
        "immunoglobulins", "ige total", "iga", "igg subclasses",
        "immunoglobulin levels", "immune deficiency panel",
    ], specialty="allergy", category="allergy"),
]

# ---------------------------------------------------------------------------
# Dermatology
# ---------------------------------------------------------------------------
_DERMATOLOGY: list[GenericTestType] = [
    GenericTestType("skin_biopsy", "Skin Biopsy", [
        "skin biopsy", "punch biopsy", "shave biopsy",
        "dermatopathology", "melanoma", "basal cell",
        "squamous cell", "actinic keratosis",
    ], specialty="dermatology", category="dermatology"),
    GenericTestType("patch_testing", "Patch Testing", [
        "patch testing", "contact dermatitis", "patch test",
        "allergen patch", "true test",
    ], specialty="dermatology", category="dermatology"),
]

# ---------------------------------------------------------------------------
# Public export — order matters: more-specific types first so that keyword
# detection naturally prefers them over broad modality-level types.
# ---------------------------------------------------------------------------
GENERIC_TYPES: list[GenericTestType] = [
    *_CARDIAC,
    *_INTERVENTIONAL,
    *_VASCULAR,
    *_IMAGING_CT,
    *_IMAGING_MRI,
    *_IMAGING_ULTRASOUND,
    *_IMAGING_XRAY,
    *_PULMONARY,
    *_NEUROPHYSIOLOGY,
    *_ENDOSCOPY,
    *_PATHOLOGY,
    *_LAB_GENERAL,
    *_LAB_ENDOCRINE,
    *_LAB_RHEUMATOLOGY,
    *_LAB_HEMATOLOGY,
    *_LAB_HEPATOLOGY,
    *_LAB_NEPHROLOGY,
    *_LAB_INFECTIOUS,
    *_ALLERGY,
    *_DERMATOLOGY,
]
