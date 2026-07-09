"""
VA Special Monthly Compensation (SMC) and TDIU Eligibility Calculator

Implements eligibility checking for:
- SMC(k) through SMC(s) levels
- TDIU (Total Disability Individual Unemployability)

References:
- 38 CFR 3.350 - Special Monthly Compensation
- 38 CFR 4.16 - Total disability ratings for compensation based on unemployability
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class SMCLevel(Enum):
    """SMC compensation levels from lowest to highest"""

    K = "k"  # Loss of use, anatomical loss
    L = "l"  # Aid and attendance or housebound
    M = "m"  # Multiple 100% disabilities
    N = "n"  # Higher level multiple 100% disabilities
    O = "o"  # Anatomical loss of both arms/legs
    R1 = "r1"  # Higher level aid and attendance
    R2 = "r2"  # Highest level aid and attendance
    S = "s"  # Housebound (100% + 60%+)


@dataclass
class SMCCondition:
    """A condition that may qualify for SMC"""

    name: str
    rating: int
    loss_of_use: bool = False
    anatomical_loss: bool = False
    body_part: str = ""  # e.g., "hand", "foot", "eye", "creative_organ"
    requires_aid_attendance: bool = False
    is_housebound: bool = False


@dataclass
class SMCEligibilityResult:
    """Result of SMC eligibility check"""

    eligible: bool
    levels: List[SMCLevel] = field(default_factory=list)
    eligible_conditions: List[Dict[str, Any]] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    estimated_monthly_addition: float = 0.0
    recommendations: List[str] = field(default_factory=list)


@dataclass
class TDIUEligibilityResult:
    """Result of TDIU eligibility check"""

    schedular_eligible: bool
    extraschedular_possible: bool
    meets_single_disability: bool
    meets_combined_criteria: bool
    highest_single_rating: int
    combined_rating: int
    qualifying_ratings: List[Dict[str, Any]] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# 2024 SMC rates (monthly additions to base compensation)
SMC_RATES_2024 = {
    SMCLevel.K: 131.64,  # Per instance, can be combined
    SMCLevel.L: 4847.05,
    SMCLevel.M: 5339.31,
    SMCLevel.N: 5916.31,
    SMCLevel.O: 6494.12,
    SMCLevel.R1: 8203.91,
    SMCLevel.R2: 9414.26,
    SMCLevel.S: 4430.63,
}

# 2025 SMC rates (effective December 1, 2024 — 2.5% COLA)
SMC_RATES_2025 = {
    SMCLevel.K: 136.06,
    SMCLevel.L: 4767.34,
    SMCLevel.M: 5261.24,
    SMCLevel.N: 5985.06,
    SMCLevel.O: 6689.81,
    SMCLevel.R1: 9559.22,
    SMCLevel.R2: 10964.66,
    SMCLevel.S: 4288.45,
}

# 2026 SMC rates (effective December 1, 2025 — 2.8% COLA)
SMC_RATES_2026 = {
    SMCLevel.K: 139.87,
    SMCLevel.L: 4900.83,
    SMCLevel.M: 5408.55,
    SMCLevel.N: 6152.64,
    SMCLevel.O: 6877.12,
    SMCLevel.R1: 9826.88,
    SMCLevel.R2: 11271.67,
    SMCLevel.S: 4408.53,
}

# Master lookup for SMC rates by year
SMC_RATES_BY_YEAR = {
    2026: SMC_RATES_2026,
    2025: SMC_RATES_2025,
    2024: SMC_RATES_2024,
}

# Body parts that qualify for SMC(k)
SMC_K_BODY_PARTS = {
    "hand": "Loss or loss of use of one hand",
    "foot": "Loss or loss of use of one foot",
    "eye": "Blindness in one eye (having only light perception)",
    "creative_organ": "Loss or loss of use of a creative organ",
    "buttock": "Loss or loss of use of both buttocks",
}

# Paired body parts for bilateral consideration
PAIRED_BODY_PARTS = {
    "hands": ["left_hand", "right_hand"],
    "feet": ["left_foot", "right_foot"],
    "arms": ["left_arm", "right_arm"],
    "legs": ["left_leg", "right_leg"],
    "eyes": ["left_eye", "right_eye"],
    "ears": ["left_ear", "right_ear"],
    "kidneys": ["left_kidney", "right_kidney"],
}


def check_smc_eligibility(conditions: List[SMCCondition]) -> SMCEligibilityResult:
    """
    Check eligibility for Special Monthly Compensation (SMC) at various levels.

    SMC levels and criteria:
    - SMC(k): Loss of use of hand, foot, creative organ, or blindness in one eye
    - SMC(l): Need for regular aid and attendance OR housebound
    - SMC(m-n): Multiple disabilities at 100%
    - SMC(o): Anatomical loss of both arms, both legs, or combination
    - SMC(r): Higher level aid and attendance
    - SMC(s): Housebound - one 100% disability plus additional 60%+

    Args:
        conditions: List of SMCCondition objects describing the veteran's disabilities

    Returns:
        SMCEligibilityResult with eligibility details
    """
    result = SMCEligibilityResult(eligible=False)

    # Separate conditions by type
    conditions_100 = [c for c in conditions if c.rating == 100]
    conditions_with_loss = [c for c in conditions if c.loss_of_use or c.anatomical_loss]
    requires_aid = [c for c in conditions if c.requires_aid_attendance]
    is_housebound_any = any(c.is_housebound for c in conditions)

    # Calculate combined rating of non-100% conditions
    other_ratings = [c.rating for c in conditions if c.rating < 100]
    combined_other = calculate_combined_for_smc(other_ratings) if other_ratings else 0

    # Check SMC(k) - Loss of use or anatomical loss
    smc_k_conditions = check_smc_k(conditions_with_loss)
    if smc_k_conditions:
        result.eligible = True
        result.levels.append(SMCLevel.K)
        result.eligible_conditions.extend(smc_k_conditions)
        count = len(smc_k_conditions)
        result.estimated_monthly_addition += SMC_RATES_2026[SMCLevel.K] * count
        result.explanations.append(
            f"Eligible for SMC(k) based on {count} qualifying condition(s): "
            f"{', '.join([c['condition'] for c in smc_k_conditions])}"
        )

    # Check SMC(s) - Housebound (100% + 60%+ combined other)
    if len(conditions_100) >= 1 and combined_other >= 60:
        result.eligible = True
        result.levels.append(SMCLevel.S)
        result.estimated_monthly_addition = max(
            result.estimated_monthly_addition, SMC_RATES_2026[SMCLevel.S]
        )
        result.explanations.append(
            f"Eligible for SMC(s) - Housebound: You have one disability rated 100% "
            f"plus additional disabilities combining to {combined_other}% (meets 60% threshold)"
        )
        result.eligible_conditions.append(
            {
                "level": "SMC(s)",
                "reason": f"100% disability plus {combined_other}% additional disabilities",
                "conditions": [c.name for c in conditions_100],
            }
        )

    # Check SMC(l) - Aid and attendance or housebound
    if requires_aid or is_housebound_any:
        result.eligible = True
        result.levels.append(SMCLevel.L)
        if SMCLevel.S in result.levels:
            # SMC(l) rate is higher than SMC(s)
            result.estimated_monthly_addition = max(
                result.estimated_monthly_addition, SMC_RATES_2026[SMCLevel.L]
            )
        else:
            result.estimated_monthly_addition += SMC_RATES_2026[SMCLevel.L]

        reason = "aid and attendance" if requires_aid else "housebound status"
        result.explanations.append(f"Eligible for SMC(l) based on need for {reason}")

    # Check SMC(m) and higher - Multiple 100% disabilities
    if len(conditions_100) >= 2:
        result.eligible = True
        result.levels.append(SMCLevel.M)
        result.estimated_monthly_addition = max(
            result.estimated_monthly_addition, SMC_RATES_2026[SMCLevel.M]
        )
        result.explanations.append(
            f"Potentially eligible for SMC(m) or higher with {len(conditions_100)} "
            f"disabilities rated at 100%"
        )

    # Check SMC(o) - Anatomical loss of paired extremities
    paired_losses = check_paired_anatomical_loss(conditions_with_loss)
    if paired_losses:
        result.eligible = True
        result.levels.append(SMCLevel.O)
        result.estimated_monthly_addition = max(
            result.estimated_monthly_addition, SMC_RATES_2026[SMCLevel.O]
        )
        result.explanations.append(
            f"Potentially eligible for SMC(o) based on: {paired_losses}"
        )

    # Add recommendations
    if not result.eligible:
        result.recommendations.append(
            "You may not currently meet SMC criteria based on the information provided. "
            "Consider discussing with a Veterans Service Organization (VSO) or attorney "
            "if you believe you may qualify."
        )
    else:
        result.recommendations.append(
            "SMC can be complex with multiple levels. A VSO or accredited attorney "
            "can help ensure you receive the correct level of SMC."
        )

        # Check if they might qualify for higher level
        if SMCLevel.K in result.levels and SMCLevel.L not in result.levels:
            result.recommendations.append(
                "If your conditions require regular aid and attendance or make you "
                "substantially confined to your home, you may qualify for higher SMC levels."
            )

    return result


def check_smc_k(conditions: List[SMCCondition]) -> List[Dict[str, Any]]:
    """
    Check for SMC(k) eligibility based on loss of use or anatomical loss.

    SMC(k) is awarded for each of the following:
    - Loss or loss of use of one hand, foot, or creative organ
    - Blindness in one eye (light perception only)
    - Complete organic aphonia (loss of voice)
    - Loss or loss of use of both buttocks
    """
    qualifying = []

    for condition in conditions:
        if not (condition.loss_of_use or condition.anatomical_loss):
            continue

        body_part = condition.body_part.lower()

        # Check if body part qualifies
        if any(
            part in body_part for part in ["hand", "foot", "eye", "creative", "buttock"]
        ):
            qualifying.append(
                {
                    "condition": condition.name,
                    "body_part": condition.body_part,
                    "type": (
                        "anatomical_loss"
                        if condition.anatomical_loss
                        else "loss_of_use"
                    ),
                    "level": "SMC(k)",
                }
            )

    return qualifying


def check_paired_anatomical_loss(conditions: List[SMCCondition]) -> Optional[str]:
    """
    Check for anatomical loss of paired extremities (SMC(o) criteria).
    """
    parts_lost = set()

    for condition in conditions:
        if condition.anatomical_loss:
            body_part = condition.body_part.lower()
            parts_lost.add(body_part)

    # Check for paired losses
    if "left_arm" in parts_lost and "right_arm" in parts_lost:
        return "Both arms"
    if "left_leg" in parts_lost and "right_leg" in parts_lost:
        return "Both legs"
    if "left_hand" in parts_lost and "right_hand" in parts_lost:
        return "Both hands"
    if "left_foot" in parts_lost and "right_foot" in parts_lost:
        return "Both feet"

    # Check for combinations (arm + leg, etc.)
    arm_lost = any("arm" in p for p in parts_lost)
    leg_lost = any("leg" in p for p in parts_lost)
    if arm_lost and leg_lost:
        return "Combination of arm and leg"

    return None


def calculate_combined_for_smc(ratings: List[int]) -> int:
    """
    Calculate combined rating for SMC purposes using VA Math.
    Simplified version - uses the same formula as main calculator.
    """
    if not ratings:
        return 0

    if len(ratings) == 1:
        return ratings[0]

    # Sort highest to lowest
    sorted_ratings = sorted(ratings, reverse=True)

    # Apply VA Math: each rating is applied to remaining "healthy" percentage
    combined = sorted_ratings[0]
    for rating in sorted_ratings[1:]:
        remaining = 100 - combined
        combined = combined + (rating * remaining / 100)

    # Round to nearest 10 per VA rules
    return round(combined / 10) * 10


def check_tdiu_eligibility(
    ratings: List[Dict[str, Any]], combined_rating: int
) -> TDIUEligibilityResult:
    """
    Check eligibility for Total Disability Individual Unemployability (TDIU).

    TDIU allows a veteran to receive 100% compensation even if their combined
    rating is less than 100%, if they cannot maintain substantially gainful
    employment due to service-connected disabilities.

    Schedular criteria (38 CFR 4.16(a)):
    - One disability rated 60% or more, OR
    - Combined rating of 70%+ with at least one disability rated 40%+

    Extraschedular (38 CFR 4.16(b)):
    - May be granted on case-by-case basis even without meeting schedular criteria

    Args:
        ratings: List of dicts with 'percentage', 'description', and 'is_bilateral'
        combined_rating: The veteran's combined disability rating

    Returns:
        TDIUEligibilityResult with eligibility details
    """
    result = TDIUEligibilityResult(
        schedular_eligible=False,
        extraschedular_possible=False,
        meets_single_disability=False,
        meets_combined_criteria=False,
        highest_single_rating=0,
        combined_rating=combined_rating,
    )

    if not ratings:
        result.explanations.append("No disability ratings provided.")
        return result

    # Get individual ratings
    individual_ratings = [r.get("percentage", 0) for r in ratings]
    result.highest_single_rating = max(individual_ratings) if individual_ratings else 0

    # Check single disability criteria (60%+)
    high_ratings = [r for r in ratings if r.get("percentage", 0) >= 60]
    if high_ratings:
        result.meets_single_disability = True
        result.schedular_eligible = True
        result.qualifying_ratings = high_ratings
        result.explanations.append(
            f"Meets TDIU schedular criteria: One disability rated 60% or higher "
            f"({result.highest_single_rating}%)"
        )

    # Check combined criteria (70%+ combined with at least one 40%+)
    if combined_rating >= 70:
        ratings_40_plus = [r for r in ratings if r.get("percentage", 0) >= 40]
        if ratings_40_plus:
            result.meets_combined_criteria = True
            result.schedular_eligible = True
            if not result.meets_single_disability:
                result.qualifying_ratings = ratings_40_plus
            result.explanations.append(
                f"Meets TDIU schedular criteria: Combined rating of {combined_rating}% (70%+ required) "
                f"with at least one disability rated 40%+ ({ratings_40_plus[0].get('percentage')}%)"
            )

    # Check for extraschedular possibility
    if not result.schedular_eligible and combined_rating >= 40:
        result.extraschedular_possible = True
        result.explanations.append(
            "Does not meet schedular TDIU criteria, but extraschedular TDIU may be "
            "possible if your service-connected disabilities prevent you from working. "
            "This requires additional documentation and VA review."
        )

    # Add recommendations
    if result.schedular_eligible:
        result.recommendations = [
            "You appear to meet the schedular criteria for TDIU.",
            "To apply, you'll need to submit VA Form 21-8940 (Application for Increased "
            "Compensation Based on Unemployability).",
            "Gather evidence showing how your service-connected disabilities prevent "
            "you from maintaining substantially gainful employment.",
            "Consider obtaining a vocational assessment or employability evaluation.",
            "A Veterans Service Organization (VSO) can help you prepare a strong TDIU claim.",
        ]
    elif result.extraschedular_possible:
        result.recommendations = [
            "You don't meet the schedular criteria, but TDIU may still be possible.",
            "Extraschedular TDIU requires showing that your specific circumstances "
            "prevent employment even without meeting the rating thresholds.",
            "Strong medical evidence and potentially a vocational expert opinion "
            "will be critical.",
            "Consider consulting with a VA-accredited attorney or claims agent who "
            "has experience with extraschedular TDIU claims.",
        ]
    else:
        result.recommendations = [
            "Based on current ratings, you don't appear to meet TDIU criteria.",
            "If your conditions have worsened, consider filing for increased ratings.",
            "If you have unclaimed conditions, filing new claims could increase your combined rating.",
            "A VSO can help evaluate whether you have any basis for a TDIU claim.",
        ]

    return result


def get_smc_level_description(level: SMCLevel) -> Dict[str, str]:
    """
    Get detailed description of an SMC level.
    """
    descriptions = {
        SMCLevel.K: {
            "name": "SMC(k)",
            "title": "Loss of Use or Anatomical Loss",
            "description": (
                "Awarded for loss or loss of use of one hand, one foot, both buttocks, "
                "one or more creative organs, blindness in one eye (having only light perception), "
                "or complete organic aphonia (loss of voice). Can be awarded multiple times "
                "for different qualifying conditions."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.K]:.2f}/month (per instance)",
        },
        SMCLevel.L: {
            "name": "SMC(l)",
            "title": "Aid and Attendance or Housebound",
            "description": (
                "Awarded when the veteran is so helpless as to need regular aid and attendance "
                "of another person, OR is permanently housebound due to service-connected disability."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.L]:.2f}/month",
        },
        SMCLevel.M: {
            "name": "SMC(m)",
            "title": "Multiple 100% Disabilities",
            "description": (
                "Awarded when the veteran has multiple service-connected disabilities, each rated "
                "at 100%, that result in a need for aid and attendance or create a housebound status."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.M]:.2f}/month",
        },
        SMCLevel.N: {
            "name": "SMC(n)",
            "title": "Higher Level Multiple 100% Disabilities",
            "description": (
                "Awarded for more severe combinations of 100% rated disabilities beyond SMC(m) criteria."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.N]:.2f}/month",
        },
        SMCLevel.O: {
            "name": "SMC(o)",
            "title": "Anatomical Loss of Paired Extremities",
            "description": (
                "Awarded for anatomical loss or loss of use of both hands, both feet, "
                "both arms, both legs, or one hand and one foot."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.O]:.2f}/month",
        },
        SMCLevel.R1: {
            "name": "SMC(r1)",
            "title": "Higher Level Aid and Attendance",
            "description": (
                "Awarded for veterans requiring a higher level of care than SMC(l), "
                "including those with severe disabilities requiring more intensive care."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.R1]:.2f}/month",
        },
        SMCLevel.R2: {
            "name": "SMC(r2)",
            "title": "Highest Level Aid and Attendance",
            "description": (
                "The highest level of SMC, awarded for the most severe disabilities "
                "requiring the highest level of care and assistance."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.R2]:.2f}/month",
        },
        SMCLevel.S: {
            "name": "SMC(s)",
            "title": "Housebound (100% plus 60%+)",
            "description": (
                "Awarded when the veteran has a single disability rated at 100% AND "
                "additional service-connected disabilities independently ratable at 60% or more. "
                "The veteran must be substantially confined to their home."
            ),
            "rate": f"${SMC_RATES_2026[SMCLevel.S]:.2f}/month",
        },
    }
    return descriptions.get(level, {})


def get_all_smc_levels_info() -> List[Dict[str, str]]:
    """
    Get information about all SMC levels for educational display.
    """
    return [get_smc_level_description(level) for level in SMCLevel]
