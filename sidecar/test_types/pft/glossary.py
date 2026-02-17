"""
Pulmonary function test glossary: medical term -> plain English explanation.

Each definition is written at a 6th-8th grade reading level for
patient-facing explanations.
"""

PFT_GLOSSARY: dict[str, str] = {
    # --- General ---
    "Pulmonary Function Test": (
        "A group of breathing tests that measure how well your lungs work. "
        "These tests show how much air your lungs can hold, how quickly you "
        "can move air in and out, and how well your lungs transfer oxygen "
        "into your blood."
    ),
    "Spirometry": (
        "The most common lung function test. You blow into a mouthpiece as "
        "hard and as fast as you can. It measures how much air you can blow "
        "out and how quickly, which helps detect conditions like asthma "
        "and COPD."
    ),
    # --- Key Measurements ---
    "FEV1": (
        "Forced Expiratory Volume in 1 Second -- the amount of air you can "
        "forcefully blow out in the first second of a big breath out. A lower "
        "number may mean your airways are narrowed or blocked."
    ),
    "FVC": (
        "Forced Vital Capacity -- the total amount of air you can forcefully "
        "blow out after taking the deepest breath possible. This helps "
        "determine if your lungs can hold a normal amount of air."
    ),
    "FEV1/FVC Ratio": (
        "The proportion of your total forced breath that comes out in the "
        "first second. A ratio below 70% usually means there is an obstruction "
        "(blockage) in the airways, as seen in conditions like asthma or COPD."
    ),
    "DLCO": (
        "Diffusing Capacity of the Lungs for Carbon Monoxide -- a test that "
        "measures how well oxygen passes from your lungs into your bloodstream. "
        "A low DLCO may indicate damage to the lung tissue or blood vessels "
        "in the lungs."
    ),
    "Diffusing Capacity": (
        "A measurement of how efficiently gases (like oxygen) move from the "
        "air in your lungs into your blood. It is tested by having you breathe "
        "in a small, safe amount of carbon monoxide and measuring how much "
        "is absorbed."
    ),
    "Total Lung Capacity": (
        "The total amount of air your lungs can hold when you take the deepest "
        "breath possible. If this number is low, it may mean your lungs are "
        "restricted (cannot fully expand). If it is high, it may mean air is "
        "trapped in your lungs."
    ),
    "Residual Volume": (
        "The amount of air that stays in your lungs after you breathe out as "
        "hard as you can. You can never completely empty your lungs. A high "
        "residual volume may mean air is getting trapped, which can happen "
        "with conditions like emphysema."
    ),
    "Functional Residual Capacity": (
        "The amount of air left in your lungs after a normal, relaxed breath "
        "out. This is the resting volume of your lungs and helps doctors "
        "understand how your lungs function during normal breathing."
    ),
    "Peak Expiratory Flow": (
        "The fastest speed at which you can blow air out of your lungs. It is "
        "often used to monitor asthma. A lower peak flow may mean your airways "
        "are narrowing."
    ),
    "FEF25-75": (
        "Forced Expiratory Flow at 25-75% of FVC -- the average speed of air "
        "flow during the middle portion of a forced breath out. This measurement "
        "is sensitive to problems in the smaller airways and may be reduced "
        "early in lung disease."
    ),
    # --- Test Components ---
    "Flow Volume Loop": (
        "A graph that shows the speed of air flow as you breathe in and out "
        "forcefully. The shape of the loop helps doctors identify different "
        "types of airway problems, including obstruction inside the lungs "
        "and blockages in the upper airway or throat."
    ),
    "Bronchodilator Response": (
        "A comparison of your breathing test results before and after inhaling "
        "a bronchodilator (a medicine that opens the airways). If your results "
        "improve significantly after the medicine, it suggests your airway "
        "narrowing is at least partly reversible, which is common in asthma."
    ),
    # --- Patterns ---
    "Obstructive Pattern": (
        "A pattern on lung testing where the airways are narrowed or blocked, "
        "making it hard to blow air out quickly. The FEV1/FVC ratio is low "
        "(below 70%). This pattern is seen in conditions like asthma, COPD, "
        "and emphysema."
    ),
    "Restrictive Pattern": (
        "A pattern on lung testing where the lungs cannot fully expand, so "
        "they hold less air than normal. The Total Lung Capacity is low "
        "(below 80% predicted). This can be caused by scarring of the lungs, "
        "chest wall problems, or muscle weakness."
    ),
    "Mixed Pattern": (
        "A combination of both obstructive and restrictive patterns on lung "
        "testing. Both the FEV1/FVC ratio and the Total Lung Capacity are "
        "reduced, meaning the airways are narrowed and the lungs also cannot "
        "fully expand."
    ),
    # --- Severity / Classification ---
    "GOLD Classification": (
        "A grading system from the Global Initiative for Chronic Obstructive "
        "Lung Disease used to rate how severe COPD is, based on FEV1 % predicted: "
        "GOLD 1 (Mild) = 80% or above, GOLD 2 (Moderate) = 50-79%, "
        "GOLD 3 (Severe) = 30-49%, GOLD 4 (Very Severe) = below 30%."
    ),
    # --- Conditions ---
    "Asthma": (
        "A common lung condition where the airways become inflamed and narrowed, "
        "causing wheezing, shortness of breath, and coughing. Asthma symptoms "
        "often come and go, and the airway narrowing is usually at least partly "
        "reversible with bronchodilator medicine."
    ),
    "COPD": (
        "Chronic Obstructive Pulmonary Disease -- a long-term lung disease "
        "usually caused by smoking. It includes emphysema and chronic bronchitis. "
        "The airways become permanently narrowed, making it hard to breathe out. "
        "Unlike asthma, the obstruction is mostly not reversible."
    ),
    "Interstitial Lung Disease": (
        "A group of conditions that cause scarring (fibrosis) of the lung tissue. "
        "The scarring makes the lungs stiff and reduces their ability to transfer "
        "oxygen into the blood. PFTs typically show a restrictive pattern with "
        "low DLCO."
    ),
    # --- Other Terms ---
    "Air Trapping": (
        "A condition where air gets stuck in the lungs and cannot be fully "
        "breathed out. It is detected on PFTs when the Residual Volume is "
        "elevated (above 120% predicted). Air trapping is common in COPD "
        "and emphysema."
    ),
    "Hyperinflation": (
        "An increase in the total amount of air in the lungs, seen when the "
        "Total Lung Capacity is above 120% predicted. It happens when air "
        "gets trapped over time, causing the lungs to over-expand. This is "
        "common in severe COPD and emphysema."
    ),
    "% Predicted": (
        "Your test result expressed as a percentage of the normal expected "
        "value for someone of your age, height, sex, and ethnicity. For example, "
        "an FEV1 of 90% predicted means your result is 90% of what is expected "
        "for a healthy person with similar characteristics. Results above 80% "
        "predicted are generally considered normal."
    ),
    "Lower Limit of Normal (LLN)": (
        "The lowest value that is still considered normal for a person of your "
        "age, height, sex, and ethnicity. Values below the LLN are considered "
        "abnormal. The LLN is statistically determined and is considered more "
        "accurate than a fixed cutoff like 70% for the FEV1/FVC ratio."
    ),
}
