"""
Secondary Conditions Data and Service

This module provides comprehensive data about secondary service connection relationships
between VA-recognized conditions. Secondary conditions are disabilities caused or
aggravated by an already service-connected condition.

Reference: 38 CFR 3.310 - Disabilities that are proximately due to, or aggravated by,
service-connected disease or injury.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class SecondaryCondition:
    """A potential secondary condition related to a primary condition."""

    condition: str
    connection_type: str  # "caused_by" or "aggravated_by"
    medical_rationale: str
    evidence_tips: List[str] = field(default_factory=list)
    diagnostic_code: str = ""
    max_rating: str = ""
    strength: str = "established"  # "established", "strong", "moderate", "emerging"


@dataclass
class PrimaryCondition:
    """A primary service-connected condition with its secondary relationships."""

    condition: str
    category: str
    diagnostic_codes: List[str] = field(default_factory=list)
    secondary_conditions: List[SecondaryCondition] = field(default_factory=list)
    description: str = ""


# Comprehensive secondary conditions database
SECONDARY_CONDITIONS_DATA: List[Dict[str, Any]] = [
    # =========================================================================
    # MENTAL HEALTH CONDITIONS
    # =========================================================================
    {
        "condition": "PTSD",
        "category": "Mental Health",
        "diagnostic_codes": ["9411"],
        "description": "Post-Traumatic Stress Disorder is commonly linked to many secondary physical and mental conditions.",
        "secondary_conditions": [
            {
                "condition": "Sleep Apnea",
                "connection_type": "caused_by",
                "medical_rationale": "Research demonstrates a strong bidirectional relationship between PTSD and sleep apnea. PTSD causes chronic sleep disruption, hyperarousal, and weight gain from medications - all risk factors for OSA.",
                "strength": "established",
                "diagnostic_code": "6847",
                "max_rating": "100%",
                "evidence_tips": [
                    "Sleep study (polysomnography) confirming diagnosis",
                    "Medical opinion linking sleep apnea to PTSD",
                    "Documentation of sleep disturbance from PTSD records",
                    "Research studies showing PTSD-sleep apnea connection",
                ],
            },
            {
                "condition": "Hypertension",
                "connection_type": "caused_by",
                "medical_rationale": "PTSD causes chronic elevated stress hormones (cortisol, adrenaline), hyperarousal, and dysregulation of the autonomic nervous system, all of which contribute to elevated blood pressure.",
                "strength": "strong",
                "diagnostic_code": "7101",
                "max_rating": "60%",
                "evidence_tips": [
                    "Blood pressure readings over time",
                    "Medical opinion linking hypertension to PTSD",
                    "Documentation of medication use",
                    "Studies on PTSD and cardiovascular effects",
                ],
            },
            {
                "condition": "Migraines/Headaches",
                "connection_type": "caused_by",
                "medical_rationale": "PTSD-related chronic stress, sleep deprivation, muscle tension, and hypervigilance are known triggers for chronic migraines and tension headaches.",
                "strength": "established",
                "diagnostic_code": "8100",
                "max_rating": "50%",
                "evidence_tips": [
                    "Headache diary documenting frequency and severity",
                    "Medical records showing headache treatment",
                    "Nexus letter from neurologist or primary care",
                    "Documentation of headache onset timing relative to PTSD",
                ],
            },
            {
                "condition": "Gastrointestinal Disorders (GERD, IBS)",
                "connection_type": "caused_by",
                "medical_rationale": "Chronic stress from PTSD affects the gut-brain axis, increases stomach acid production, and causes gastrointestinal dysfunction.",
                "strength": "established",
                "diagnostic_code": "7346/7319",
                "max_rating": "60%",
                "evidence_tips": [
                    "Endoscopy or other diagnostic testing",
                    "Medication records for GI conditions",
                    "Medical opinion connecting GI issues to PTSD stress",
                ],
            },
            {
                "condition": "Erectile Dysfunction",
                "connection_type": "caused_by",
                "medical_rationale": "PTSD medications (especially SSRIs) commonly cause ED as a side effect. Additionally, PTSD-related anxiety and depression can directly cause ED.",
                "strength": "established",
                "diagnostic_code": "7522",
                "max_rating": "SMC-K",
                "evidence_tips": [
                    "List of medications causing ED as side effect",
                    "Medical records documenting ED diagnosis",
                    "Note: ED qualifies for Special Monthly Compensation (SMC-K)",
                ],
            },
            {
                "condition": "Weight Gain/Obesity",
                "connection_type": "caused_by",
                "medical_rationale": "PTSD medications (antidepressants, antipsychotics) commonly cause significant weight gain. Additionally, PTSD-related depression affects motivation for exercise.",
                "strength": "strong",
                "diagnostic_code": "N/A",
                "max_rating": "N/A (supports other claims)",
                "evidence_tips": [
                    "Weight records before and after PTSD treatment",
                    "Medication documentation with weight gain side effects",
                    "This can support secondary claims for sleep apnea, heart disease, diabetes",
                ],
            },
            {
                "condition": "Substance Abuse Disorder",
                "connection_type": "caused_by",
                "medical_rationale": "Self-medication with alcohol or drugs to cope with PTSD symptoms is well-documented. The VA recognizes substance abuse secondary to mental health conditions.",
                "strength": "established",
                "diagnostic_code": "9431",
                "max_rating": "100%",
                "evidence_tips": [
                    "Treatment records for substance abuse",
                    "Mental health records showing self-medication pattern",
                    "Therapist statements linking substance use to PTSD symptoms",
                ],
            },
            {
                "condition": "Depression/Anxiety",
                "connection_type": "caused_by",
                "medical_rationale": "PTSD commonly co-occurs with or causes major depressive disorder and generalized anxiety disorder due to shared neurobiological pathways.",
                "strength": "established",
                "diagnostic_code": "9434/9400",
                "max_rating": "Note: Only ONE mental health rating allowed",
                "evidence_tips": [
                    "Mental health evaluations documenting both conditions",
                    "Note: Mental health conditions are rated together under the General Rating Formula",
                ],
            },
        ],
    },
    # =========================================================================
    # TBI (TRAUMATIC BRAIN INJURY)
    # =========================================================================
    {
        "condition": "Traumatic Brain Injury (TBI)",
        "category": "Neurological",
        "diagnostic_codes": ["8045"],
        "description": "TBI often causes multiple secondary conditions that can be rated separately from the TBI itself.",
        "secondary_conditions": [
            {
                "condition": "Migraine Headaches",
                "connection_type": "caused_by",
                "medical_rationale": "Post-traumatic headaches are one of the most common residuals of TBI. They can develop immediately after injury or emerge months later.",
                "strength": "established",
                "diagnostic_code": "8100",
                "max_rating": "50%",
                "evidence_tips": [
                    "Headache diary with frequency and severity",
                    "Documentation of headache onset after TBI",
                    "Medical records showing headache treatment",
                ],
            },
            {
                "condition": "Tinnitus",
                "connection_type": "caused_by",
                "medical_rationale": "TBI, especially from blast exposure, commonly damages the auditory system and causes persistent tinnitus.",
                "strength": "established",
                "diagnostic_code": "6260",
                "max_rating": "10%",
                "evidence_tips": [
                    "Audiology evaluation",
                    "Documentation of TBI mechanism (blast, impact)",
                    "Statement describing tinnitus onset relative to TBI",
                ],
            },
            {
                "condition": "Hearing Loss",
                "connection_type": "caused_by",
                "medical_rationale": "TBI, particularly from explosions, causes sensorineural hearing loss through damage to the inner ear or auditory processing centers.",
                "strength": "established",
                "diagnostic_code": "6100",
                "max_rating": "100%",
                "evidence_tips": [
                    "Audiogram results",
                    "Documentation of noise exposure or blast in service",
                    "Comparison of hearing before and after TBI event",
                ],
            },
            {
                "condition": "Sleep Apnea",
                "connection_type": "caused_by",
                "medical_rationale": "TBI can damage brain centers controlling breathing during sleep, leading to central or obstructive sleep apnea.",
                "strength": "strong",
                "diagnostic_code": "6847",
                "max_rating": "100%",
                "evidence_tips": [
                    "Sleep study confirming diagnosis",
                    "Medical opinion linking to TBI",
                    "Research on TBI and sleep-disordered breathing",
                ],
            },
            {
                "condition": "PTSD/Depression/Anxiety",
                "connection_type": "caused_by",
                "medical_rationale": "TBI commonly causes emotional and behavioral changes through direct brain damage and the psychological trauma of the injury.",
                "strength": "established",
                "diagnostic_code": "9411/9434/9400",
                "max_rating": "100%",
                "evidence_tips": [
                    "Mental health evaluation",
                    "Documentation of personality/mood changes after TBI",
                    "Buddy statements describing behavioral changes",
                ],
            },
            {
                "condition": "Vestibular Disorder (Vertigo/Dizziness)",
                "connection_type": "caused_by",
                "medical_rationale": "TBI frequently damages the vestibular system, causing chronic dizziness, balance problems, and vertigo.",
                "strength": "established",
                "diagnostic_code": "6204",
                "max_rating": "100%",
                "evidence_tips": [
                    "Vestibular function testing",
                    "Balance assessment",
                    "Documentation of dizziness symptoms",
                ],
            },
            {
                "condition": "Seizure Disorder",
                "connection_type": "caused_by",
                "medical_rationale": "TBI can cause post-traumatic epilepsy, with seizures developing months or years after the initial injury.",
                "strength": "established",
                "diagnostic_code": "8910-8914",
                "max_rating": "100%",
                "evidence_tips": [
                    "EEG results",
                    "Seizure diary",
                    "Neurologist evaluation",
                ],
            },
            {
                "condition": "Erectile Dysfunction",
                "connection_type": "caused_by",
                "medical_rationale": "TBI can affect hormonal regulation and neurological pathways involved in sexual function.",
                "strength": "strong",
                "diagnostic_code": "7522",
                "max_rating": "SMC-K",
                "evidence_tips": [
                    "Medical documentation of ED diagnosis",
                    "Hormone level testing",
                    "Note: Qualifies for Special Monthly Compensation (SMC-K)",
                ],
            },
        ],
    },
    # =========================================================================
    # BACK CONDITIONS
    # =========================================================================
    {
        "condition": "Back Condition (Lumbar/Thoracolumbar Spine)",
        "category": "Musculoskeletal",
        "diagnostic_codes": ["5237", "5242", "5243"],
        "description": "Back conditions commonly cause secondary conditions, especially neurological symptoms in the lower extremities.",
        "secondary_conditions": [
            {
                "condition": "Radiculopathy (Lower Extremity)",
                "connection_type": "caused_by",
                "medical_rationale": "Disc herniation, stenosis, or other spine pathology can compress nerve roots, causing radiating pain, numbness, and weakness in the legs.",
                "strength": "established",
                "diagnostic_code": "8520/8521",
                "max_rating": "80% per extremity",
                "evidence_tips": [
                    "EMG/nerve conduction study",
                    "MRI showing nerve compression",
                    "Neurological examination documenting sensory/motor deficits",
                    "Each leg is rated separately",
                ],
            },
            {
                "condition": "Depression",
                "connection_type": "caused_by",
                "medical_rationale": "Chronic pain from back conditions frequently leads to depression due to loss of function, sleep disruption, and reduced quality of life.",
                "strength": "established",
                "diagnostic_code": "9434",
                "max_rating": "100%",
                "evidence_tips": [
                    "Mental health evaluation",
                    "Documentation of chronic pain",
                    "Research on chronic pain and depression",
                ],
            },
            {
                "condition": "Bowel/Bladder Dysfunction",
                "connection_type": "caused_by",
                "medical_rationale": "Severe spine conditions can affect nerve pathways controlling bowel and bladder function.",
                "strength": "established",
                "diagnostic_code": "7332/7517",
                "max_rating": "100%",
                "evidence_tips": [
                    "Urological evaluation",
                    "Documentation of cauda equina symptoms",
                    "MRI showing significant nerve compression",
                ],
            },
            {
                "condition": "Knee Condition (Secondary)",
                "connection_type": "caused_by",
                "medical_rationale": "Altered gait from back pain causes uneven weight distribution and stress on the knees, leading to degenerative changes.",
                "strength": "strong",
                "diagnostic_code": "5260/5261",
                "max_rating": "60%",
                "evidence_tips": [
                    "Gait analysis or documentation of abnormal gait",
                    "X-rays showing degenerative changes",
                    "Medical opinion on altered biomechanics",
                ],
            },
            {
                "condition": "Hip Condition",
                "connection_type": "caused_by",
                "medical_rationale": "Compensating for back pain alters hip mechanics and can cause or accelerate hip degeneration.",
                "strength": "strong",
                "diagnostic_code": "5252",
                "max_rating": "90%",
                "evidence_tips": [
                    "Documentation of altered gait",
                    "Imaging of hip joints",
                    "Medical opinion on compensatory mechanics",
                ],
            },
        ],
    },
    # =========================================================================
    # KNEE CONDITIONS
    # =========================================================================
    {
        "condition": "Knee Condition",
        "category": "Musculoskeletal",
        "diagnostic_codes": ["5256", "5257", "5260", "5261"],
        "description": "Knee conditions often lead to secondary conditions in other joints due to altered gait and weight distribution.",
        "secondary_conditions": [
            {
                "condition": "Opposite Knee Condition",
                "connection_type": "caused_by",
                "medical_rationale": "Favoring one knee puts excessive stress on the contralateral knee, accelerating wear and degenerative changes.",
                "strength": "established",
                "diagnostic_code": "5260/5261",
                "max_rating": "60%",
                "evidence_tips": [
                    "Imaging showing degeneration in both knees",
                    "Gait analysis documentation",
                    "Medical opinion on compensatory stress",
                ],
            },
            {
                "condition": "Hip Condition",
                "connection_type": "caused_by",
                "medical_rationale": "Abnormal gait from knee problems alters hip mechanics, causing pain and accelerated degeneration.",
                "strength": "established",
                "diagnostic_code": "5252",
                "max_rating": "90%",
                "evidence_tips": [
                    "Imaging of hips",
                    "Documentation of gait abnormality",
                    "Orthopedic opinion on biomechanical relationship",
                ],
            },
            {
                "condition": "Back Condition",
                "connection_type": "caused_by",
                "medical_rationale": "Altered gait and posture from knee problems places abnormal stress on the lumbar spine.",
                "strength": "established",
                "diagnostic_code": "5237/5242",
                "max_rating": "100%",
                "evidence_tips": [
                    "Spine imaging",
                    "Documentation of onset after knee injury",
                    "Medical opinion on compensatory spinal stress",
                ],
            },
            {
                "condition": "Depression",
                "connection_type": "caused_by",
                "medical_rationale": "Chronic pain and loss of mobility from knee conditions commonly leads to depression.",
                "strength": "established",
                "diagnostic_code": "9434",
                "max_rating": "100%",
                "evidence_tips": [
                    "Mental health evaluation",
                    "Documentation of functional limitations",
                    "Impact on quality of life",
                ],
            },
        ],
    },
    # =========================================================================
    # DIABETES
    # =========================================================================
    {
        "condition": "Diabetes Mellitus Type II",
        "category": "Endocrine",
        "diagnostic_codes": ["7913"],
        "description": "Diabetes causes numerous secondary complications affecting multiple body systems.",
        "secondary_conditions": [
            {
                "condition": "Peripheral Neuropathy",
                "connection_type": "caused_by",
                "medical_rationale": "High blood sugar damages peripheral nerves, causing pain, numbness, and weakness in extremities.",
                "strength": "established",
                "diagnostic_code": "8520/8521",
                "max_rating": "80% per extremity",
                "evidence_tips": [
                    "EMG/nerve conduction studies",
                    "Documentation of symptoms",
                    "Each extremity rated separately",
                ],
            },
            {
                "condition": "Coronary Artery Disease",
                "connection_type": "caused_by",
                "medical_rationale": "Diabetes significantly accelerates atherosclerosis and increases risk of heart disease.",
                "strength": "established",
                "diagnostic_code": "7005",
                "max_rating": "100%",
                "evidence_tips": [
                    "Cardiac testing (stress test, echo, catheterization)",
                    "Medical records documenting CAD diagnosis",
                    "Research on diabetes and cardiovascular disease",
                ],
            },
            {
                "condition": "Hypertension",
                "connection_type": "caused_by",
                "medical_rationale": "Diabetes damages blood vessels and kidneys, contributing to elevated blood pressure.",
                "strength": "established",
                "diagnostic_code": "7101",
                "max_rating": "60%",
                "evidence_tips": [
                    "Blood pressure records",
                    "Medication documentation",
                    "Kidney function tests",
                ],
            },
            {
                "condition": "Kidney Disease (Nephropathy)",
                "connection_type": "caused_by",
                "medical_rationale": "Diabetic nephropathy is a common complication caused by damage to kidney blood vessels.",
                "strength": "established",
                "diagnostic_code": "7541",
                "max_rating": "100%",
                "evidence_tips": [
                    "Kidney function tests (eGFR, creatinine)",
                    "Urinalysis showing protein",
                    "Nephrology evaluation",
                ],
            },
            {
                "condition": "Vision Problems (Retinopathy)",
                "connection_type": "caused_by",
                "medical_rationale": "Diabetic retinopathy damages blood vessels in the retina, leading to vision impairment.",
                "strength": "established",
                "diagnostic_code": "6006",
                "max_rating": "100%",
                "evidence_tips": [
                    "Ophthalmology evaluation",
                    "Retinal imaging",
                    "Documentation of vision changes",
                ],
            },
            {
                "condition": "Erectile Dysfunction",
                "connection_type": "caused_by",
                "medical_rationale": "Diabetes damages blood vessels and nerves involved in erectile function.",
                "strength": "established",
                "diagnostic_code": "7522",
                "max_rating": "SMC-K",
                "evidence_tips": [
                    "Urology evaluation",
                    "Note: Qualifies for Special Monthly Compensation (SMC-K)",
                ],
            },
        ],
    },
    # =========================================================================
    # SLEEP APNEA
    # =========================================================================
    {
        "condition": "Sleep Apnea",
        "category": "Respiratory",
        "diagnostic_codes": ["6847"],
        "description": "Sleep apnea causes secondary conditions through chronic oxygen deprivation and sleep disruption.",
        "secondary_conditions": [
            {
                "condition": "Hypertension",
                "connection_type": "caused_by",
                "medical_rationale": "Repeated oxygen desaturation and sympathetic activation from sleep apnea causes and worsens hypertension.",
                "strength": "established",
                "diagnostic_code": "7101",
                "max_rating": "60%",
                "evidence_tips": [
                    "Blood pressure records",
                    "Sleep study showing oxygen desaturation",
                    "Research on OSA and hypertension",
                ],
            },
            {
                "condition": "Heart Disease",
                "connection_type": "caused_by",
                "medical_rationale": "Sleep apnea increases risk of arrhythmias, heart failure, and coronary artery disease.",
                "strength": "established",
                "diagnostic_code": "7005/7007",
                "max_rating": "100%",
                "evidence_tips": [
                    "Cardiac evaluation",
                    "Documentation of arrhythmias",
                    "Research on OSA and cardiovascular disease",
                ],
            },
            {
                "condition": "Stroke",
                "connection_type": "caused_by",
                "medical_rationale": "Sleep apnea significantly increases stroke risk through effects on blood pressure and oxygen levels.",
                "strength": "established",
                "diagnostic_code": "8007-8009",
                "max_rating": "100%",
                "evidence_tips": [
                    "Medical records documenting stroke",
                    "Sleep study results",
                    "Research on OSA and stroke risk",
                ],
            },
            {
                "condition": "Depression",
                "connection_type": "caused_by",
                "medical_rationale": "Chronic sleep disruption and fatigue from sleep apnea commonly causes depression.",
                "strength": "established",
                "diagnostic_code": "9434",
                "max_rating": "100%",
                "evidence_tips": [
                    "Mental health evaluation",
                    "Documentation of fatigue and mood symptoms",
                    "Research on sleep deprivation and mental health",
                ],
            },
        ],
    },
    # =========================================================================
    # HYPERTENSION
    # =========================================================================
    {
        "condition": "Hypertension",
        "category": "Cardiovascular",
        "diagnostic_codes": ["7101"],
        "description": "Long-term hypertension causes damage to multiple organ systems.",
        "secondary_conditions": [
            {
                "condition": "Heart Disease",
                "connection_type": "caused_by",
                "medical_rationale": "Chronic high blood pressure causes hypertensive heart disease, left ventricular hypertrophy, and coronary artery disease.",
                "strength": "established",
                "diagnostic_code": "7007",
                "max_rating": "100%",
                "evidence_tips": [
                    "Echocardiogram",
                    "Cardiac stress test",
                    "Documentation of blood pressure history",
                ],
            },
            {
                "condition": "Stroke",
                "connection_type": "caused_by",
                "medical_rationale": "Hypertension is the leading risk factor for stroke due to damage to blood vessels.",
                "strength": "established",
                "diagnostic_code": "8007-8009",
                "max_rating": "100%",
                "evidence_tips": [
                    "Medical records documenting stroke",
                    "Blood pressure history",
                    "Neurological evaluation",
                ],
            },
            {
                "condition": "Kidney Disease",
                "connection_type": "caused_by",
                "medical_rationale": "Hypertensive nephropathy damages kidney blood vessels, leading to chronic kidney disease.",
                "strength": "established",
                "diagnostic_code": "7541",
                "max_rating": "100%",
                "evidence_tips": [
                    "Kidney function tests",
                    "Blood pressure history",
                    "Nephrology evaluation",
                ],
            },
            {
                "condition": "Vision Problems",
                "connection_type": "caused_by",
                "medical_rationale": "Hypertensive retinopathy damages blood vessels in the eyes.",
                "strength": "established",
                "diagnostic_code": "6006",
                "max_rating": "100%",
                "evidence_tips": ["Ophthalmology evaluation", "Retinal imaging"],
            },
        ],
    },
    # =========================================================================
    # TINNITUS
    # =========================================================================
    {
        "condition": "Tinnitus",
        "category": "Ear/Auditory",
        "diagnostic_codes": ["6260"],
        "description": "Tinnitus can cause or contribute to secondary mental health conditions.",
        "secondary_conditions": [
            {
                "condition": "Depression/Anxiety",
                "connection_type": "caused_by",
                "medical_rationale": "Chronic tinnitus causes significant distress, sleep disruption, and concentration problems that lead to depression and anxiety.",
                "strength": "established",
                "diagnostic_code": "9434/9400",
                "max_rating": "100%",
                "evidence_tips": [
                    "Mental health evaluation",
                    "Documentation of tinnitus severity",
                    "Sleep disturbance records",
                ],
            },
            {
                "condition": "Sleep Disorder",
                "connection_type": "caused_by",
                "medical_rationale": "Persistent ringing makes it difficult to fall asleep and causes chronic sleep disturbance.",
                "strength": "established",
                "diagnostic_code": "6847",
                "max_rating": "100%",
                "evidence_tips": [
                    "Sleep study if available",
                    "Documentation of sleep problems",
                    "Medical records showing treatment attempts",
                ],
            },
            {
                "condition": "Migraines/Headaches",
                "connection_type": "aggravated_by",
                "medical_rationale": "Tinnitus can trigger and worsen migraines, particularly due to the constant sensory input and stress.",
                "strength": "moderate",
                "diagnostic_code": "8100",
                "max_rating": "50%",
                "evidence_tips": [
                    "Headache diary showing correlation",
                    "Neurology evaluation",
                    "Documentation of symptom pattern",
                ],
            },
        ],
    },
]


def get_all_primary_conditions() -> List[Dict[str, Any]]:
    """
    Get all primary conditions with their secondary conditions.
    Returns the full data structure for display.
    """
    return SECONDARY_CONDITIONS_DATA


def get_primary_condition(condition_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific primary condition by name.
    """
    condition_lower = condition_name.lower()
    for condition in SECONDARY_CONDITIONS_DATA:
        if condition_lower in condition["condition"].lower():
            return condition
    return None


def get_categories() -> List[str]:
    """
    Get all unique categories.
    """
    return list(set(c["category"] for c in SECONDARY_CONDITIONS_DATA))


def get_conditions_by_category(category: str) -> List[Dict[str, Any]]:
    """
    Get all conditions in a specific category.
    """
    return [c for c in SECONDARY_CONDITIONS_DATA if c["category"] == category]


def search_secondary_conditions(query: str) -> List[Dict[str, Any]]:
    """
    Search for conditions by name or description.
    Returns matching primary conditions with highlighted secondaries.
    """
    query_lower = query.lower()
    results = []

    for primary in SECONDARY_CONDITIONS_DATA:
        # Check if query matches primary condition
        primary_match = query_lower in primary["condition"].lower()

        # Check if query matches any secondary condition
        matching_secondaries = []
        for secondary in primary["secondary_conditions"]:
            if query_lower in secondary["condition"].lower():
                matching_secondaries.append(secondary)

        if primary_match or matching_secondaries:
            result = primary.copy()
            if matching_secondaries:
                result["matching_secondaries"] = matching_secondaries
            results.append(result)

    return results


def get_secondary_conditions_for(primary_condition: str) -> List[Dict[str, Any]]:
    """
    Get all secondary conditions for a specific primary condition.
    """
    condition = get_primary_condition(primary_condition)
    if condition:
        return condition["secondary_conditions"]
    return []


def get_conditions_count() -> Dict[str, int]:
    """
    Get count statistics for display.
    """
    total_primary = len(SECONDARY_CONDITIONS_DATA)
    total_secondary = sum(
        len(c["secondary_conditions"]) for c in SECONDARY_CONDITIONS_DATA
    )
    total_categories = len(get_categories())

    return {
        "primary_conditions": total_primary,
        "secondary_relationships": total_secondary,
        "categories": total_categories,
    }
