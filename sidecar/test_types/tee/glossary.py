"""
Transesophageal echocardiogram (TEE) glossary: medical term -> plain English explanation.

Each definition is written at a 6th-8th grade reading level for
patient-facing explanations.
"""

TEE_GLOSSARY: dict[str, str] = {
    # --- General ---
    "Transesophageal Echocardiogram": (
        "A heart ultrasound performed by passing a small probe down the esophagus "
        "(the tube from your mouth to your stomach). Because the esophagus sits "
        "right behind the heart, this test provides very clear, detailed pictures "
        "of heart structures that may be hard to see from the chest wall."
    ),
    "TEE Probe": (
        "A thin, flexible tube with a tiny ultrasound camera on the tip. It is "
        "gently guided down your throat into the esophagus to take pictures of "
        "the heart from behind. You are given medication to help you relax and "
        "numb your throat before the probe is inserted."
    ),
    # --- LAA ---
    "Left Atrial Appendage (LAA)": (
        "A small, ear-shaped pouch attached to the left atrium (upper left chamber) "
        "of the heart. Blood can sometimes pool and form clots in this pouch, "
        "especially in people with atrial fibrillation. TEE is the best test to "
        "check for clots in the LAA."
    ),
    "LAA Thrombus": (
        "A blood clot inside the left atrial appendage. If a clot breaks loose, "
        "it can travel to the brain and cause a stroke. Finding an LAA thrombus "
        "may change treatment decisions, such as starting blood-thinning medication "
        "or postponing certain heart procedures."
    ),
    "LAA Emptying Velocity": (
        "The speed at which blood flows out of the left atrial appendage. A normal "
        "velocity (40 cm/s or higher) means blood is moving well and is less likely "
        "to form clots. A low velocity (below 40 cm/s) suggests sluggish blood flow, "
        "which increases the risk of clot formation."
    ),
    # --- Interatrial Septum ---
    "Interatrial Septum": (
        "The wall of tissue that separates the left and right upper chambers (atria) "
        "of the heart. TEE can closely examine this wall for holes or defects that "
        "may allow blood to cross between the two chambers."
    ),
    "Patent Foramen Ovale (PFO)": (
        "A small flap-like opening in the wall between the upper heart chambers that "
        "did not close after birth. Everyone has this opening before birth, but in "
        "about 25% of people it remains partially open. A PFO can sometimes allow "
        "blood clots to cross from the right to the left side of the heart and "
        "travel to the brain, potentially causing a stroke."
    ),
    "Atrial Septal Defect (ASD)": (
        "A hole in the wall between the two upper chambers (atria) of the heart. "
        "Unlike a PFO, an ASD is a true structural defect. Depending on its size, "
        "it can cause extra blood to flow to the lungs and may need to be closed "
        "with a procedure or surgery."
    ),
    "Bubble Study/Agitated Saline": (
        "A test performed during TEE where tiny air bubbles are injected into a vein. "
        "The bubbles normally stay on the right side of the heart. If bubbles appear "
        "on the left side, it means there is an opening (such as a PFO or ASD) "
        "allowing blood to cross between the upper chambers."
    ),
    # --- Aortic Findings ---
    "Aortic Atheroma": (
        "A buildup of cholesterol and fatty material (plaque) on the wall of the "
        "aorta, the body's main artery. TEE can detect these plaques, especially in "
        "the descending aorta and aortic arch. Large or protruding atheromas may "
        "increase the risk of stroke."
    ),
    # --- Endocarditis ---
    "Vegetation": (
        "A clump of bacteria, blood cells, and debris attached to a heart valve. "
        "Vegetations are a hallmark of endocarditis (heart valve infection). TEE is "
        "more sensitive than a regular echocardiogram at detecting these growths."
    ),
    "Endocarditis": (
        "An infection of the inner lining of the heart, usually involving one or more "
        "heart valves. Bacteria in the bloodstream can settle on damaged or artificial "
        "valves and form infected clumps called vegetations. TEE is the preferred test "
        "to look for signs of endocarditis."
    ),
    # --- Prosthetic Valve ---
    "Prosthetic Valve": (
        "An artificial heart valve placed during surgery to replace a damaged natural "
        "valve. Prosthetic valves can be mechanical (made of metal and carbon) or "
        "bioprosthetic (made from animal tissue). TEE provides excellent images of "
        "prosthetic valves and can detect complications such as leaks or infections."
    ),
    "Paravalvular Leak": (
        "A leak of blood around the edge of a prosthetic (artificial) heart valve, "
        "rather than through it. This happens when the seal between the valve and the "
        "heart tissue is not complete. Small leaks are common and may not cause "
        "problems, but larger leaks can lead to symptoms and may need repair."
    ),
    # --- Valves ---
    "Mitral Valve": (
        "The valve between the left atrium and left ventricle. It opens to let blood "
        "flow from the upper to lower left chamber and closes to prevent blood from "
        "flowing backward."
    ),
    "Aortic Valve": (
        "The valve between the left ventricle and the aorta (the main artery leaving "
        "the heart). It opens when the heart pumps and closes to prevent blood from "
        "leaking back."
    ),
    "Mitral Regurgitation": (
        "Backward leaking of blood through the mitral valve. Mild regurgitation is "
        "common and often harmless. Moderate to severe regurgitation may cause symptoms "
        "and require monitoring or treatment."
    ),
    "Aortic Regurgitation": (
        "Backward leaking of blood through the aortic valve into the left ventricle. "
        "This makes the heart work harder to pump enough blood to the body."
    ),
    "Valve Area": (
        "The effective opening size of a heart valve, measured in square centimeters. "
        "A smaller valve area means the valve is narrower (stenotic) and blood has a "
        "harder time flowing through it."
    ),
    "Mean Gradient": (
        "The average pressure difference across a heart valve during blood flow. A "
        "higher gradient means the valve is narrower and the heart must work harder "
        "to push blood through it. It is measured in millimeters of mercury (mmHg)."
    ),
    "Peak Gradient": (
        "The highest pressure difference across a heart valve at any single moment "
        "during blood flow. Like the mean gradient, a higher peak gradient suggests "
        "a narrower valve opening."
    ),
    # --- Aorta ---
    "Ascending Aorta": (
        "The first section of the aorta as it rises upward from the heart. TEE can "
        "measure its diameter to check for dilation (widening) or aneurysm. Normal "
        "diameter is about 2.0 to 3.7 cm."
    ),
    # --- Imaging Techniques ---
    "3D Reconstruction": (
        "A TEE imaging technique that creates a three-dimensional picture of heart "
        "structures. This is especially helpful for evaluating valve anatomy, planning "
        "valve repair, and guiding certain heart procedures."
    ),
    "Spontaneous Echo Contrast (SEC/\"Smoke\")": (
        "A swirling, smoke-like pattern seen on the ultrasound image, caused by "
        "sluggish blood flow. It is often seen in the left atrium or left atrial "
        "appendage in patients with atrial fibrillation. SEC indicates an increased "
        "risk of blood clot formation."
    ),
    # --- TEE Views ---
    "Midesophageal View": (
        "A standard TEE imaging position with the probe in the middle of the "
        "esophagus. From this position, the probe can obtain clear views of the "
        "heart valves, atria, interatrial septum, and left atrial appendage."
    ),
    "Transgastric View": (
        "A TEE imaging position with the probe advanced into the stomach. This "
        "view provides short-axis images of the left and right ventricles and is "
        "useful for assessing ventricular wall motion and muscle thickness."
    ),
}
