"""
CTA Coronary glossary: medical term -> plain English explanation.

Each definition is written at a 6th-8th grade reading level for
patient-facing explanations.
"""

CTA_GLOSSARY: dict[str, str] = {
    # --- General ---
    "CTA Coronary": (
        "A CT scan of the heart's blood vessels (coronary arteries) using contrast "
        "dye injected through an IV. It creates detailed 3D images to check for "
        "blockages or narrowing in the arteries that supply blood to the heart."
    ),
    "Coronary CT Angiography": (
        "Another name for CTA Coronary. A non-invasive imaging test that uses a CT "
        "scanner and contrast dye to take detailed pictures of the coronary arteries "
        "and look for plaque buildup or blockages."
    ),
    # --- Calcium Scoring ---
    "Calcium Score (Agatston Score)": (
        "A number that measures how much calcium (hard deposits) has built up in the "
        "walls of the coronary arteries. A score of 0 means no calcium was found. "
        "Higher scores mean more calcium and a greater chance of coronary artery disease. "
        "The score is named after Dr. Arthur Agatston who developed the method."
    ),
    "Coronary Artery Calcium": (
        "Calcium deposits that build up in the walls of the heart's arteries over time. "
        "These deposits are a sign of atherosclerosis (plaque buildup). The amount of "
        "calcium can help predict the risk of a future heart attack."
    ),
    # --- Classification ---
    "CAD-RADS": (
        "Coronary Artery Disease - Reporting and Data System. A standardized way to "
        "report CTA coronary results on a scale from 0 (no disease) to 5 (total "
        "blockage). It helps doctors communicate findings clearly and decide on next "
        "steps for treatment."
    ),
    # --- Coronary Arteries ---
    "Left Main Coronary Artery": (
        "The short trunk artery that branches from the aorta and splits into the LAD "
        "and LCx arteries. It supplies blood to a large portion of the heart. A blockage "
        "here is especially serious because it affects blood flow to most of the left "
        "side of the heart."
    ),
    "LAD (Left Anterior Descending)": (
        "One of the main coronary arteries. It runs down the front of the heart and "
        "supplies blood to the largest area of heart muscle, including the front wall "
        "and the septum (the wall between the two lower chambers). It is sometimes "
        "called the 'widow maker' because a blockage here can be very dangerous."
    ),
    "LCx (Left Circumflex)": (
        "One of the main coronary arteries. It wraps around the left side of the heart "
        "and supplies blood to the back and side walls of the left ventricle. It branches "
        "off from the left main artery."
    ),
    "RCA (Right Coronary Artery)": (
        "One of the main coronary arteries. It runs along the right side of the heart and "
        "supplies blood to the bottom of the heart, the right ventricle, and part of the "
        "heart's electrical system."
    ),
    # --- Findings ---
    "Stenosis": (
        "Narrowing of a blood vessel. In CTA coronary reports, stenosis refers to "
        "narrowing of the coronary arteries caused by plaque buildup. The degree of "
        "narrowing is usually reported as a percentage."
    ),
    "Plaque (Calcified)": (
        "Hard, calcium-containing deposits in the artery wall. Calcified plaque is "
        "more stable and less likely to rupture suddenly, but it still narrows the "
        "artery and reduces blood flow."
    ),
    "Plaque (Non-calcified)": (
        "Soft plaque in the artery wall that does not contain calcium. Non-calcified "
        "or 'soft' plaque may be more likely to rupture and cause a sudden blockage "
        "(heart attack) compared to calcified plaque."
    ),
    "Plaque (Mixed)": (
        "Plaque in the artery wall that contains both calcified (hard) and "
        "non-calcified (soft) components. Mixed plaque is common and its risk "
        "depends on the overall amount and degree of narrowing."
    ),
    "Atherosclerosis": (
        "A condition where fatty deposits (plaque) build up inside the artery walls "
        "over time. This makes the arteries narrower and stiffer, reducing blood flow. "
        "It is the main cause of coronary artery disease."
    ),
    "Stent Patency": (
        "Whether a previously placed stent (a small metal mesh tube used to hold open "
        "a narrowed artery) is still open and allowing blood to flow through normally. "
        "A patent stent means it is open; an occluded stent means it is blocked."
    ),
    "Bypass Graft": (
        "A blood vessel (taken from the leg, chest, or arm) that has been surgically "
        "attached to reroute blood flow around a blocked coronary artery. CTA can check "
        "whether these grafts are still open and working."
    ),
    "Coronary Artery Disease": (
        "A condition where the coronary arteries become narrowed or blocked by plaque "
        "buildup (atherosclerosis). This reduces blood flow to the heart muscle and "
        "can cause chest pain (angina) or a heart attack."
    ),
    # --- Advanced Measurements ---
    "CT-FFR": (
        "CT-derived Fractional Flow Reserve. A computer calculation done on CTA images "
        "that estimates how much a blockage is limiting blood flow. A value above 0.80 "
        "is normal. A value of 0.80 or below suggests the blockage may be causing reduced "
        "blood flow (ischemia) and might need treatment."
    ),
    # --- Technical Terms ---
    "Prospective Gating": (
        "A technique used during the CT scan where images are taken only during a specific "
        "part of the heartbeat (usually when the heart is most still). This reduces the "
        "amount of radiation compared to scanning the entire heartbeat."
    ),
    "Contrast": (
        "A special dye (usually iodine-based) injected into a vein through an IV during "
        "the CT scan. The contrast dye makes the blood vessels show up brightly on the "
        "images, allowing the doctor to see blockages or narrowing."
    ),
    "Coronary Anomaly": (
        "An unusual pattern in how the coronary arteries are shaped or where they "
        "originate. Most coronary anomalies are harmless and found by chance, but some "
        "can affect blood flow and may need monitoring or treatment."
    ),
    "Myocardial Bridge": (
        "A condition where a segment of a coronary artery dips into the heart muscle "
        "instead of running along the surface. The overlying muscle can squeeze the "
        "artery during heartbeats. Most myocardial bridges are harmless and do not "
        "cause symptoms."
    ),
}
