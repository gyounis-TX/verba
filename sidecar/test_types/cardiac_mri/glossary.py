"""
Cardiac MRI glossary: medical term -> plain English explanation.

Each definition is written at a 6th-8th grade reading level for
patient-facing explanations.
"""

CMR_GLOSSARY: dict[str, str] = {
    # --- General ---
    "Cardiac MRI": (
        "A type of imaging test that uses a strong magnet and radio waves to create "
        "detailed pictures of the heart. Unlike X-rays or CT scans, it does not use "
        "radiation. It can show the heart's structure, how well it pumps, and whether "
        "there is any scarring or damage to the heart muscle."
    ),
    "CMR": (
        "Short for Cardiac Magnetic Resonance. This is another name for a cardiac MRI -- "
        "a detailed imaging test of the heart using magnets and radio waves."
    ),
    "Cine Imaging": (
        "A type of cardiac MRI movie that shows the heart beating in real time. It is "
        "used to measure how well the heart chambers are squeezing and relaxing, and to "
        "check the size of the heart chambers."
    ),
    # --- Tissue Characterization ---
    "Late Gadolinium Enhancement (LGE)": (
        "A special part of the cardiac MRI that highlights areas of scarring or damage "
        "in the heart muscle. A contrast dye called gadolinium is given through an IV, "
        "and damaged areas of the heart hold onto the dye longer than healthy tissue, "
        "making scars show up bright white on the images."
    ),
    "Gadolinium": (
        "A contrast dye given through an IV during some MRI scans. It helps highlight "
        "certain tissues and makes it easier to see areas of damage or scarring in the "
        "heart muscle. It is generally safe but is not used in patients with severe "
        "kidney problems."
    ),
    "T1 Mapping": (
        "A special MRI technique that measures a property of the heart tissue called T1. "
        "Changes in T1 values can indicate problems like scarring (fibrosis), swelling "
        "(edema), or deposits in the heart muscle, even before they become visible on "
        "standard images."
    ),
    "Native T1": (
        "The T1 value of the heart muscle measured before any contrast dye is given. "
        "Higher-than-normal native T1 values can suggest swelling, scarring, or certain "
        "diseases affecting the heart muscle."
    ),
    "T2 Mapping": (
        "A special MRI technique that measures a property of the heart tissue called T2. "
        "Higher T2 values suggest that the heart muscle has extra water in it, which is "
        "a sign of swelling (edema) or active inflammation."
    ),
    "Extracellular Volume (ECV)": (
        "A measurement from cardiac MRI that estimates the amount of space between heart "
        "muscle cells. A higher ECV suggests there is more scar tissue or other material "
        "between the cells, which can happen with fibrosis (scarring) or diseases that "
        "deposit substances in the heart."
    ),
    "Myocardial Edema": (
        "Swelling of the heart muscle caused by extra fluid. It can be a sign of active "
        "inflammation or a recent injury to the heart, such as a heart attack. Cardiac "
        "MRI can detect edema using T2 mapping or special imaging sequences."
    ),
    "Myocardial Fibrosis": (
        "Scarring of the heart muscle. This happens when normal heart muscle is replaced "
        "by scar tissue, often after a heart attack or due to long-term heart disease. "
        "Cardiac MRI can detect both focal scars (using LGE) and diffuse fibrosis "
        "(using T1 mapping and ECV)."
    ),
    "Scar Burden": (
        "The total amount of scarring in the heart muscle, usually given as a percentage "
        "of the total heart muscle. A higher scar burden means more of the heart has been "
        "damaged and replaced by scar tissue. This is measured using late gadolinium "
        "enhancement (LGE) on cardiac MRI."
    ),
    "Delayed Enhancement": (
        "Another name for late gadolinium enhancement (LGE). It refers to areas of the "
        "heart that hold onto contrast dye longer than normal, indicating scarring or "
        "damage."
    ),
    # --- Function Measurements ---
    "Strain": (
        "A measurement of how much the heart muscle stretches and squeezes during each "
        "heartbeat. Lower strain values may indicate that the heart muscle is not "
        "contracting as well as it should, even when the overall pumping strength "
        "(ejection fraction) appears normal."
    ),
    "LVEF": (
        "Left Ventricular Ejection Fraction -- the percentage of blood the left "
        "ventricle (the heart's main pumping chamber) pumps out with each beat. "
        "Normal is typically 52-70%. On cardiac MRI, this is measured very accurately "
        "from cine images."
    ),
    "LVEDV": (
        "Left Ventricular End-Diastolic Volume -- the total amount of blood in the left "
        "ventricle when it is fully relaxed and filled. A larger-than-normal volume may "
        "mean the heart chamber is stretched or dilated."
    ),
    "LVESV": (
        "Left Ventricular End-Systolic Volume -- the amount of blood remaining in the "
        "left ventricle after it has finished squeezing. A larger-than-normal volume may "
        "suggest the heart is not pumping strongly enough."
    ),
    "LV Mass": (
        "The weight of the left ventricle's muscle. An increase in LV mass may indicate "
        "the heart wall has thickened (hypertrophy), often caused by high blood pressure "
        "or other conditions that make the heart work harder."
    ),
    "LV Mass Index": (
        "The weight of the left ventricle's muscle adjusted for body size (body surface "
        "area). Indexing to body size allows for fairer comparison between people of "
        "different sizes."
    ),
    "RVEF": (
        "Right Ventricular Ejection Fraction -- the percentage of blood the right "
        "ventricle pumps out with each beat. The right ventricle pumps blood to the "
        "lungs. Normal RVEF is typically 45-70%."
    ),
    "RVEDV": (
        "Right Ventricular End-Diastolic Volume -- the total amount of blood in the "
        "right ventricle when it is fully relaxed and filled. An enlarged right ventricle "
        "may indicate lung or heart valve problems."
    ),
    "RVESV": (
        "Right Ventricular End-Systolic Volume -- the amount of blood remaining in the "
        "right ventricle after it has finished squeezing."
    ),
    # --- Perfusion ---
    "Perfusion Defect": (
        "An area of the heart muscle that does not receive enough blood flow. On cardiac "
        "MRI, this appears as a dark area during stress perfusion imaging. A perfusion "
        "defect may indicate a blockage in one of the heart's arteries."
    ),
    "Ischemia": (
        "A condition where part of the heart muscle does not get enough blood and oxygen, "
        "usually because of a narrowed or blocked artery. If the blood flow is not "
        "restored, it can lead to damage (heart attack). Cardiac MRI stress perfusion "
        "can detect ischemia."
    ),
    # --- Conditions ---
    "Cardiomyopathy": (
        "A disease of the heart muscle that makes it harder for the heart to pump blood. "
        "There are several types, and cardiac MRI is one of the best tests for figuring "
        "out which type a patient has based on the pattern of scarring and other findings."
    ),
    "Hypertrophic Cardiomyopathy": (
        "A condition where the heart muscle becomes abnormally thick, making it harder "
        "for the heart to pump. It is often inherited (runs in families). Cardiac MRI "
        "can show the thickness of the walls and detect any scarring."
    ),
    "Dilated Cardiomyopathy": (
        "A condition where the heart's main pumping chamber (left ventricle) becomes "
        "enlarged and weakened, so it cannot pump blood as efficiently. Cardiac MRI "
        "helps measure the chamber size and look for scarring patterns that may point "
        "to the cause."
    ),
    "Amyloidosis": (
        "A condition where abnormal proteins build up in the heart muscle, making it "
        "stiff and harder for the heart to fill with blood. Cardiac MRI can show "
        "characteristic patterns on LGE images and elevated T1/ECV values that suggest "
        "this diagnosis."
    ),
    "Sarcoidosis": (
        "A condition where clumps of inflammatory cells (granulomas) form in the body, "
        "including sometimes the heart. Cardiac sarcoidosis can cause heart rhythm "
        "problems and weakened heart function. Cardiac MRI can detect inflammation "
        "and scarring caused by sarcoidosis."
    ),
    "Myocarditis": (
        "Inflammation of the heart muscle, often caused by a viral infection. Symptoms "
        "can include chest pain, shortness of breath, and abnormal heart rhythms. "
        "Cardiac MRI is one of the best tests for diagnosing myocarditis because it "
        "can show swelling (edema) and scarring in the heart muscle."
    ),
    "Iron Overload": (
        "A condition where too much iron builds up in the heart muscle, which can weaken "
        "the heart. It is seen in patients who need frequent blood transfusions or have "
        "certain genetic conditions. Cardiac MRI can measure the amount of iron in the "
        "heart using a special technique called T2* mapping."
    ),
}
