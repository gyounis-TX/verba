"""
Right heart catheterization glossary: medical term -> plain English explanation.

Each definition is written at a 6th-8th grade reading level for
patient-facing explanations.
"""

RHC_GLOSSARY: dict[str, str] = {
    # --- General ---
    "Right Heart Catheterization": (
        "A test where a thin, flexible tube (catheter) is guided through a vein "
        "into the right side of the heart and the lung arteries. It directly measures "
        "blood pressures inside the heart and lungs, and how well the heart is pumping."
    ),
    "Swan-Ganz Catheter": (
        "A special catheter with a small balloon at its tip that is floated through "
        "the right side of the heart into the pulmonary artery. It is the main tool "
        "used during a right heart catheterization to measure pressures and blood flow."
    ),
    # --- Chambers & Pressures ---
    "Right Atrium": (
        "The upper right chamber of the heart. It receives blood returning from "
        "the body and passes it to the right ventricle."
    ),
    "Right Atrial Pressure": (
        "The blood pressure measured inside the right atrium. It reflects how much "
        "blood is returning to the heart and how well the right side of the heart is "
        "handling that blood. Normal mean RA pressure is 0-5 mmHg."
    ),
    "Pulmonary Artery": (
        "The large blood vessel that carries blood from the right ventricle to the "
        "lungs to pick up oxygen. High pressure in this artery is called pulmonary "
        "hypertension."
    ),
    "PA Pressure": (
        "Pulmonary Artery Pressure -- the blood pressure measured in the artery "
        "going to the lungs. It is reported as systolic (when the heart squeezes), "
        "diastolic (when the heart relaxes), and mean (average). Normal mean PA "
        "pressure is 20 mmHg or less."
    ),
    "PCWP / Wedge Pressure": (
        "Pulmonary Capillary Wedge Pressure -- measured by inflating the balloon "
        "on the catheter tip to temporarily block a small lung artery. This indirectly "
        "measures the pressure in the left side of the heart. Normal is 12 mmHg or less."
    ),
    # --- Cardiac Output ---
    "Cardiac Output": (
        "The total amount of blood the heart pumps per minute, measured in liters "
        "per minute (L/min). A normal cardiac output is about 4-8 L/min. A low "
        "cardiac output means the heart is not pumping enough blood to meet the "
        "body's needs."
    ),
    "Cardiac Index": (
        "Cardiac output adjusted for body size (divided by body surface area). "
        "This allows a fair comparison between people of different sizes. Normal "
        "cardiac index is 2.5 L/min/m2 or higher."
    ),
    # --- Resistance ---
    "PVR": (
        "Pulmonary Vascular Resistance -- a measure of how much the blood vessels "
        "in the lungs resist blood flow. High PVR means the lung vessels are narrowed "
        "or stiff, making the right side of the heart work harder. Normal is less than "
        "2 Wood units."
    ),
    "Transpulmonary Gradient": (
        "The difference between the mean pulmonary artery pressure and the wedge "
        "pressure (TPG = mPAP - PCWP). It helps determine whether high lung pressure "
        "is coming from the lung vessels themselves or from the left side of the heart. "
        "Normal is 12 mmHg or less."
    ),
    # --- Oxygen ---
    "Mixed Venous Oxygen Saturation": (
        "The percentage of oxygen in the blood inside the pulmonary artery, which "
        "mixes blood from the entire body. It shows how well the body is using oxygen. "
        "Normal is 65-75%. A low value suggests the heart is not pumping enough blood "
        "or the body is using more oxygen than usual."
    ),
    # --- Methods ---
    "Thermodilution": (
        "A method used to measure cardiac output. A small amount of cold saline is "
        "injected through the catheter, and a sensor downstream measures how quickly "
        "the temperature changes. This tells doctors how fast blood is flowing."
    ),
    "Fick Method": (
        "Another way to calculate cardiac output. It uses the amount of oxygen the "
        "body consumes and the difference in oxygen levels between arterial and venous "
        "blood. It is often used when thermodilution results are unreliable."
    ),
    # --- Diagnoses ---
    "Pulmonary Hypertension": (
        "High blood pressure in the arteries that supply the lungs. It is defined "
        "as a mean pulmonary artery pressure greater than 20 mmHg. It makes the right "
        "side of the heart work harder and can lead to right heart failure if untreated."
    ),
    "Pre-capillary Pulmonary Hypertension": (
        "A type of pulmonary hypertension caused by problems in the lung blood vessels "
        "themselves (not the left heart). The wedge pressure is normal (15 mmHg or less) "
        "and the PVR is elevated (2 Wood units or more). Causes include blood clots in "
        "the lungs and diseases of the lung arteries."
    ),
    "Post-capillary Pulmonary Hypertension": (
        "A type of pulmonary hypertension caused by problems on the left side of the "
        "heart, such as heart failure or valve disease. The wedge pressure is elevated "
        "(greater than 15 mmHg). Blood backs up from the left heart into the lungs."
    ),
    "Combined Pre- and Post-capillary Pulmonary Hypertension": (
        "A type of pulmonary hypertension where both the left heart and the lung "
        "vessels contribute. The wedge pressure is elevated AND the PVR is also high "
        "(2 Wood units or more), meaning the lung vessels have developed their own "
        "disease on top of the left heart problem."
    ),
    "Heart Failure": (
        "A condition where the heart cannot pump enough blood to meet the body's "
        "needs. Right heart catheterization helps determine how severe the heart "
        "failure is and guides treatment decisions."
    ),
    "Right Heart Failure": (
        "A condition where the right side of the heart is too weak to pump blood "
        "effectively to the lungs. This causes blood to back up in the veins, "
        "leading to swelling in the legs, abdomen, and liver. Elevated RA pressure "
        "and low cardiac output are key findings."
    ),
    "Fluid Overload": (
        "A condition where there is too much fluid in the body, causing elevated "
        "pressures in the heart and lungs. Right heart catheterization shows elevated "
        "RA pressure, PA pressure, and wedge pressure. Treatment usually involves "
        "diuretics (water pills) to remove excess fluid."
    ),
}
