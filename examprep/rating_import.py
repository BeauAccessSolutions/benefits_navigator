"""
Rating Import Utility

Converts extracted ratings from RatingAnalysis model conditions
to DisabilityRating objects for use in the VA Rating Calculator.
"""

from typing import List
from .va_math import DisabilityRating

# Keywords that indicate bilateral conditions (paired extremities)
BILATERAL_KEYWORDS = [
    "knee",
    "ankle",
    "foot",
    "hip",
    "shoulder",
    "elbow",
    "wrist",
    "hand",
    "ear",
    "eye",
    "arm",
    "leg",
    "toes",
    "fingers",
    "hearing",
    "plantar fasciitis",
    "carpal tunnel",
]


def convert_extracted_to_ratings(conditions: list) -> List[DisabilityRating]:
    """
    Convert RatingAnalysis conditions JSONField to DisabilityRating objects.

    Args:
        conditions: List of condition dicts from RatingAnalysis.conditions
                   Expected format: [{"name": "...", "rating_percentage": 30, ...}]

    Returns:
        List of DisabilityRating objects ready for the calculator
    """
    ratings = []

    for condition in conditions:
        percentage = condition.get("rating_percentage", 0)

        # Handle string percentages
        if isinstance(percentage, str):
            try:
                percentage = int(percentage.replace("%", "").strip())
            except (ValueError, AttributeError):
                percentage = 0

        # Round to nearest 10 (VA ratings are in 10% increments)
        percentage = round(percentage / 10) * 10
        percentage = max(0, min(100, percentage))

        name = condition.get("name", "") or condition.get("condition", "")
        is_bilateral = _is_bilateral(name)

        if percentage > 0:
            ratings.append(
                DisabilityRating(
                    percentage=percentage, description=name, is_bilateral=is_bilateral
                )
            )

    return ratings


def _is_bilateral(name: str) -> bool:
    """
    Detect if a condition is bilateral based on its name.

    Bilateral conditions affect paired body parts (left/right) and
    receive a 10% bilateral factor bonus in VA Math calculations.

    Args:
        name: The condition name/description

    Returns:
        True if the condition appears to be bilateral
    """
    if not name:
        return False

    name_lower = name.lower()

    # Check for explicit bilateral keywords
    if "bilateral" in name_lower:
        return True

    # Check for paired body part keywords with left/right indicator
    for keyword in BILATERAL_KEYWORDS:
        if keyword in name_lower:
            # Check if it mentions left, right, or both
            if any(
                side in name_lower for side in ["left", "right", "both", "l/", "r/"]
            ):
                return True

    return False


def get_import_summary(conditions: list) -> dict:
    """
    Get a summary of conditions that will be imported.

    Useful for displaying a preview to the user before import.

    Args:
        conditions: List of condition dicts from RatingAnalysis.conditions

    Returns:
        Dict with import statistics
    """
    ratings = convert_extracted_to_ratings(conditions)

    bilateral_count = sum(1 for r in ratings if r.is_bilateral)
    total_percentage_sum = sum(r.percentage for r in ratings)

    return {
        "total_conditions": len(ratings),
        "bilateral_conditions": bilateral_count,
        "ratings": [
            {
                "percentage": r.percentage,
                "description": r.description,
                "is_bilateral": r.is_bilateral,
            }
            for r in ratings
        ],
        "raw_percentage_sum": total_percentage_sum,
    }
