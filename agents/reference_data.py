"""
Reference Data Loader for AI Agents

Provides access to M21-1 Adjudication Procedures Manual and other reference materials.
Now supports both JSON files and database queries for M21 data.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Path to reference data
DATA_DIR = Path(__file__).parent / "data"
DBQ_DIR = DATA_DIR / "dbqs"
CFR_DIR = DATA_DIR / "cfr"


# ============================================================================
# Database-backed M21 Functions (uses scraped data)
# ============================================================================


def _get_m21_model():
    """Lazy import of M21ManualSection model to avoid circular imports"""
    try:
        from .models import M21ManualSection

        return M21ManualSection
    except ImportError:
        return None


def get_m21_section_from_db(reference: str) -> Optional[Dict]:
    """
    Get M21 section from database by reference.

    Args:
        reference: Section reference (e.g., 'V.ii.2.A' or 'M21-1.V.ii.2.A')

    Returns:
        Section data dict or None
    """
    M21ManualSection = _get_m21_model()
    if not M21ManualSection:
        return None

    # Normalize reference
    ref = reference.replace("M21-1.", "").strip()

    try:
        section = M21ManualSection.objects.filter(reference__icontains=ref).first()
        if section:
            return {
                "reference": section.reference,
                "full_reference": section.full_reference,
                "title": section.title,
                "overview": section.overview,
                "content": section.content,
                "part": section.part,
                "part_title": section.part_title,
                "subpart": section.subpart,
                "chapter": section.chapter,
                "section": section.section,
                "topics": section.topics or [],
                "references": section.references or [],
                "article_id": section.article_id,
                "knowva_url": section.knowva_url,
            }
    except Exception as e:
        logger.error(f"Error querying M21 section: {e}")

    return None


def search_m21_in_db(
    query: str, part_filter: Optional[str] = None, limit: int = 10
) -> List[Dict]:
    """
    Search M21 sections in database by keyword.

    Args:
        query: Search query
        part_filter: Optional part to filter by (e.g., 'V', 'IV')
        limit: Maximum results

    Returns:
        List of matching sections
    """
    M21ManualSection = _get_m21_model()
    if not M21ManualSection:
        return []

    try:
        from django.db.models import Q

        qs = M21ManualSection.objects.all()

        if part_filter:
            qs = qs.filter(part=part_filter)

        # Search in title, overview, and content
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(overview__icontains=query)
            | Q(search_text__icontains=query)
        )[:limit]

        return [
            {
                "reference": s.reference,
                "title": s.title,
                "part": s.part,
                "part_title": s.part_title,
                "overview": (s.overview or "")[:200],
            }
            for s in qs
        ]
    except Exception as e:
        logger.error(f"Error searching M21 sections: {e}")

    return []


def get_m21_sections_by_part(part: str, limit: int = 50) -> List[Dict]:
    """
    Get all M21 sections for a specific part.

    Args:
        part: Part identifier (e.g., 'V', 'VIII')
        limit: Maximum sections to return

    Returns:
        List of sections in that part
    """
    M21ManualSection = _get_m21_model()
    if not M21ManualSection:
        return []

    try:
        sections = M21ManualSection.objects.filter(part=part).order_by(
            "subpart", "chapter", "section"
        )[:limit]

        return [
            {
                "reference": s.reference,
                "title": s.title,
                "overview": (s.overview or "")[:200],
                "subpart": s.subpart,
                "chapter": s.chapter,
                "section": s.section,
            }
            for s in sections
        ]
    except Exception as e:
        logger.error(f"Error getting M21 sections by part: {e}")

    return []


def get_m21_stats() -> Dict:
    """Get statistics about M21 data in database."""
    M21ManualSection = _get_m21_model()
    if not M21ManualSection:
        return {"total": 0, "by_part": {}}

    try:
        from django.db.models import Count

        total = M21ManualSection.objects.count()
        by_part = dict(
            M21ManualSection.objects.values("part")
            .annotate(count=Count("id"))
            .values_list("part", "count")
        )

        return {
            "total": total,
            "by_part": by_part,
        }
    except Exception as e:
        logger.error(f"Error getting M21 stats: {e}")

    return {"total": 0, "by_part": {}}


@lru_cache(maxsize=1)
def load_m21_index() -> Dict:
    """Load the M21 section index"""
    with open(DATA_DIR / "m21_index.json", "r") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_m21_searchable() -> List[Dict]:
    """Load the flat searchable M21 index"""
    with open(DATA_DIR / "m21_searchable.json", "r") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_m21_agent_topics() -> Dict:
    """Load topic-organized M21 references for agents"""
    with open(DATA_DIR / "m21_agent_topics.json", "r") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_m21_complete() -> Dict:
    """Load the complete M21 manual (large file - use sparingly)"""
    with open(DATA_DIR / "m21_complete.json", "r") as f:
        return json.load(f)


@lru_cache(maxsize=10)
def load_m21_part(part_num: int) -> Optional[Dict]:
    """Load a specific part of the M21 manual"""
    try:
        with open(DATA_DIR / f"m21_part_{part_num}.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def load_appeal_guide(appeal_type: str) -> Optional[Dict]:
    """
    Load an appeal guide by type.

    Args:
        appeal_type: One of 'hlr', 'supplemental', 'board'
    """
    file_map = {
        "hlr": "higher_level_review_guide.json",
        "higher_level_review": "higher_level_review_guide.json",
        "supplemental": "supplemental_claim_guide.json",
        "supplemental_claim": "supplemental_claim_guide.json",
        "board": "board_appeal_guide.json",
        "board_appeal": "board_appeal_guide.json",
        "bva": "board_appeal_guide.json",
    }

    filename = file_map.get(appeal_type.lower())
    if not filename:
        return None

    try:
        with open(DATA_DIR / filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def search_m21_sections(
    query: str,
    topic_filter: Optional[str] = None,
    part_filter: Optional[str] = None,
    limit: int = 10,
) -> List[Dict]:
    """
    Search M21 sections by keyword.
    Tries database first, then falls back to JSON files.

    Args:
        query: Search query (searches titles and overviews)
        topic_filter: Optional topic to filter by (e.g., 'service_connection', 'evidence')
        part_filter: Optional part to filter by (e.g., 'V', 'IV')
        limit: Maximum results to return

    Returns:
        List of matching section summaries
    """
    # First try database
    db_results = search_m21_in_db(query, part_filter=part_filter, limit=limit)
    if db_results:
        return db_results

    # Fall back to JSON files
    query_lower = query.lower()
    try:
        searchable = load_m21_searchable()
    except FileNotFoundError:
        return []

    results = []
    for section in searchable:
        # Apply part filter
        if part_filter and section["part"] != part_filter:
            continue

        # Search in title, overview, and topics
        searchable_text = (
            section["title"].lower()
            + " "
            + section.get("overview", "").lower()
            + " "
            + " ".join(section.get("topics", []))
        ).lower()

        if query_lower in searchable_text:
            results.append(
                {
                    "reference": section["reference"],
                    "title": section["title"],
                    "part": section["part"],
                    "part_title": section["part_title"],
                    "overview": section.get("overview", "")[:200],
                    "topic_count": section.get("topic_count", 0),
                }
            )

            if len(results) >= limit:
                break

    return results


def get_m21_section(reference: str) -> Optional[Dict]:
    """
    Get a specific M21 section by reference.
    Tries JSON files first, then falls back to database.

    Args:
        reference: Section reference (e.g., 'M21-1.V.ii.2.A')

    Returns:
        Full section data or None if not found
    """
    # First try database (has scraped content)
    db_result = get_m21_section_from_db(reference)
    if db_result:
        return db_result

    # Fall back to JSON files
    # Parse reference: M21-1.PART.SUBPART.CHAPTER.SECTION
    parts = reference.replace("M21-1.", "").split(".")
    if len(parts) != 4:
        return None

    part, subpart, chapter, section = parts

    # Map roman numeral to int for file loading
    roman_to_int = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,
        "V": 5,
        "VI": 6,
        "VII": 7,
        "VIII": 8,
        "IX": 9,
        "X": 10,
        "XI": 11,
        "XII": 12,
        "XIII": 13,
        "XIV": 14,
    }

    part_num = roman_to_int.get(part)
    if not part_num:
        return None

    part_data = load_m21_part(part_num)
    if not part_data:
        return None

    try:
        return part_data["subparts"][subpart][chapter][section]
    except KeyError:
        return None


def get_sections_by_topic(topic: str, limit: int = 20) -> List[Dict]:
    """
    Get M21 sections relevant to a specific topic.

    Args:
        topic: Topic name (e.g., 'service_connection', 'evidence', 'examinations')

    Returns:
        List of relevant sections
    """
    topics = load_m21_agent_topics()
    topic_data = topics.get(topic.lower())

    if not topic_data:
        return []

    return topic_data.get("sections", [])[:limit]


def get_service_connection_guidance() -> Dict:
    """Get M21 guidance specifically about service connection."""
    return {
        "direct": get_m21_section("M21-1.V.ii.2.A"),
        "presumptive": get_m21_section("M21-1.V.ii.2.B"),
        "aggravation": get_m21_section("M21-1.V.ii.2.C"),
        "secondary": get_m21_section("M21-1.V.ii.2.D"),
        "congenital": get_m21_section("M21-1.V.ii.2.E"),
    }


def get_evidence_guidance() -> Dict:
    """Get M21 guidance about evidence review and weighing."""
    return {
        "reviewing_evidence": get_m21_section("M21-1.V.ii.1.A"),
        "lay_evidence": get_m21_section("M21-1.V.ii.1.B"),
    }


def get_rating_guidance() -> Dict:
    """Get M21 guidance about the rating process."""
    return {
        "determining_issues": get_m21_section("M21-1.V.ii.3.A"),
        "partial_ratings": get_m21_section("M21-1.V.ii.3.B"),
        "reviewing_diagnoses": get_m21_section("M21-1.V.ii.3.C"),
        "evaluating_disabilities": get_m21_section("M21-1.V.ii.3.D"),
    }


def get_effective_date_guidance() -> Dict:
    """Get M21 guidance about effective dates."""
    return {
        "effective_dates": get_m21_section("M21-1.V.ii.4.A"),
        "historical_guidance": get_m21_section("M21-1.V.ii.4.B"),
    }


def get_musculoskeletal_guidance() -> Dict:
    """Get M21 guidance about musculoskeletal conditions."""
    return {
        "painful_motion": get_m21_section("M21-1.V.iii.1.A"),
        "extremities_spine": get_m21_section("M21-1.V.iii.1.B"),
        "arthritis": get_m21_section("M21-1.V.iii.1.C"),
        "osteomyelitis": get_m21_section("M21-1.V.iii.1.D"),
        "muscle_injuries": get_m21_section("M21-1.V.iii.1.E"),
        "other_considerations": get_m21_section("M21-1.V.iii.1.F"),
    }


def get_examination_guidance() -> Dict:
    """Get M21 guidance about C&P examinations."""
    return {
        "failure_to_report": get_m21_section("M21-1.IV.i.2.F"),
        "sufficiency_criteria": get_m21_section("M21-1.IV.i.3.A"),
        "specific_disabilities": get_m21_section("M21-1.IV.i.3.B"),
        "insufficient_exams": get_m21_section("M21-1.IV.i.3.C"),
    }


def format_m21_reference_for_prompt(
    section: Optional[Dict], max_length: int = 2000
) -> str:
    """
    Format an M21 section for inclusion in an AI prompt.

    Args:
        section: Section data from get_m21_section()
        max_length: Maximum character length

    Returns:
        Formatted string for prompt inclusion
    """
    if not section:
        return ""

    output = []
    output.append(f"## {section.get('title', 'Unknown Section')}")
    output.append(
        f"Reference: {section.get('full_reference', section.get('reference', ''))}"
    )
    output.append("")

    if section.get("overview"):
        output.append("### Overview")
        output.append(section["overview"][:500])
        output.append("")

    # Add key topics
    topics = section.get("topics", [])
    if topics:
        output.append("### Key Points")
        for topic in topics[:5]:  # Limit to 5 topics
            if topic.get("title"):
                output.append(f"- **{topic['title']}**")
                if topic.get("content"):
                    # First 200 chars of content
                    content_preview = topic["content"][:200]
                    if len(topic["content"]) > 200:
                        content_preview += "..."
                    output.append(f"  {content_preview}")

    result = "\n".join(output)

    # Truncate if needed
    if len(result) > max_length:
        result = result[:max_length] + "\n...[truncated]"

    return result


# Available topics for reference
AVAILABLE_TOPICS = [
    "service_connection",
    "rating_process",
    "evidence",
    "examinations",
    "effective_dates",
    "appeals",
    "mental_health",
    "musculoskeletal",
    "special_monthly_compensation",
    "tdiu",
]


# Part titles for reference
PART_TITLES = {
    "I": "Claimants' Rights and Claims Processing Centers and Programs",
    "II": "Intake, Claims Establishment, Jurisdiction, and File Maintenance",
    "III": "The Development Process",
    "IV": "Examinations",
    "V": "The Rating Process",
    "VI": "The Authorization Process",
    "VII": "Dependency",
    "VIII": "Special Compensation Issues",
    "IX": "Pension, Survivors' Pension, and Parent's DIC",
    "X": "Benefits Administration and Oversight",
    "XI": "Notice of Death, Benefits Payable at Death, and Burial Benefits",
    "XII": "DIC and Other Survivor's Benefits",
    "XIII": "Eligibility Determinations and Information Sharing",
    "XIV": "Matching Programs",
}


# ============================================================================
# DBQ (Disability Benefits Questionnaire) Functions
# ============================================================================


@lru_cache(maxsize=50)
def load_dbq(condition: str) -> Optional[Dict]:
    """
    Load a DBQ by condition name.

    Args:
        condition: Condition name or key (e.g., 'ptsd', 'knee', 'back', 'mental_disorders')

    Returns:
        DBQ data dict or None if not found
    """
    # Normalize condition name
    condition_lower = condition.lower().replace(" ", "_").replace("-", "_")

    # Map common names to file names
    condition_map = {
        "ptsd": "dbq_ptsd",
        "post_traumatic_stress": "dbq_ptsd",
        "back": "dbq_back_thoracolumbar",
        "thoracolumbar": "dbq_back_thoracolumbar",
        "lumbar": "dbq_back_thoracolumbar",
        "spine": "dbq_back_thoracolumbar",
        "knee": "dbq_knee",
        "shoulder": "dbq_shoulder",
        "arm": "dbq_shoulder",
        "sleep_apnea": "dbq_sleep_apnea",
        "apnea": "dbq_sleep_apnea",
        "headaches": "dbq_headaches",
        "migraines": "dbq_headaches",
        "migraine": "dbq_headaches",
        "mental_disorders": "dbq_mental_disorders",
        "depression": "dbq_mental_disorders",
        "anxiety": "dbq_mental_disorders",
        "bipolar": "dbq_mental_disorders",
        "tinnitus": "dbq_tinnitus_hearing",
        "hearing": "dbq_tinnitus_hearing",
        "hearing_loss": "dbq_tinnitus_hearing",
        "ear": "dbq_tinnitus_hearing",
        "diabetes": "dbq_diabetes",
        "diabetic": "dbq_diabetes",
        "hypertension": "dbq_hypertension",
        "blood_pressure": "dbq_hypertension",
        "peripheral_nerves": "dbq_peripheral_nerves",
        "radiculopathy": "dbq_peripheral_nerves",
        "neuropathy": "dbq_peripheral_nerves",
        "neck": "dbq_neck_cervical",
        "cervical": "dbq_neck_cervical",
        "sinusitis": "dbq_sinusitis_rhinitis",
        "rhinitis": "dbq_sinusitis_rhinitis",
        "sinus": "dbq_sinusitis_rhinitis",
        "respiratory": "dbq_respiratory",
        "asthma": "dbq_respiratory",
        "copd": "dbq_respiratory",
        "lung": "dbq_respiratory",
        "heart": "dbq_heart",
        "cardiac": "dbq_heart",
        "coronary": "dbq_heart",
    }

    # Get filename
    filename = condition_map.get(condition_lower, f"dbq_{condition_lower}")

    try:
        with open(DBQ_DIR / f"{filename}.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def list_available_dbqs() -> List[Dict]:
    """
    List all available DBQs.

    Returns:
        List of dicts with DBQ name, condition, and category
    """
    dbqs = []
    if not DBQ_DIR.exists():
        return dbqs

    for file in DBQ_DIR.glob("*.json"):
        try:
            with open(file, "r") as f:
                data = json.load(f)
                dbqs.append(
                    {
                        "file": file.stem,
                        "name": data.get("dbq_name", file.stem),
                        "condition": data.get("condition", ""),
                        "category": data.get("category", ""),
                        "diagnostic_codes": data.get("diagnostic_codes", []),
                    }
                )
        except (json.JSONDecodeError, KeyError):
            continue

    return sorted(dbqs, key=lambda x: x["name"])


def get_dbq_rating_criteria(condition: str) -> Optional[Dict]:
    """
    Get just the rating criteria from a DBQ.

    Args:
        condition: Condition name

    Returns:
        Rating criteria dict or None
    """
    dbq = load_dbq(condition)
    if not dbq:
        return None
    return dbq.get("rating_criteria")


def get_dbq_tips(condition: str) -> Optional[List[str]]:
    """
    Get veteran tips from a DBQ.

    Args:
        condition: Condition name

    Returns:
        List of tips or None
    """
    dbq = load_dbq(condition)
    if not dbq:
        return None
    return dbq.get("tips_for_veterans", [])


def search_dbqs_by_diagnostic_code(code: str) -> List[Dict]:
    """
    Find DBQs by diagnostic code.

    Args:
        code: Diagnostic code (e.g., '8100', '5260')

    Returns:
        List of matching DBQs
    """
    matches = []
    for dbq_info in list_available_dbqs():
        if code in dbq_info.get("diagnostic_codes", []):
            matches.append(dbq_info)
    return matches


def search_dbqs_by_category(category: str) -> List[Dict]:
    """
    Find DBQs by category.

    Args:
        category: Category name (e.g., 'musculoskeletal', 'mental_health', 'respiratory')

    Returns:
        List of matching DBQs
    """
    category_lower = category.lower()
    return [
        dbq
        for dbq in list_available_dbqs()
        if dbq.get("category", "").lower() == category_lower
    ]


def format_dbq_for_prompt(condition: str, include_sections: List[str] = None) -> str:
    """
    Format DBQ data for inclusion in an AI prompt.

    Args:
        condition: Condition name
        include_sections: List of sections to include. Options:
            - 'rating_criteria'
            - 'tips'
            - 'common_mistakes'
            - 'secondary_conditions'
            - 'symptoms'

    Returns:
        Formatted string for prompt inclusion
    """
    dbq = load_dbq(condition)
    if not dbq:
        return f"No DBQ data found for condition: {condition}"

    if include_sections is None:
        include_sections = ["rating_criteria", "tips"]

    output = []
    output.append(f"## {dbq.get('dbq_name', condition)}")
    output.append(f"CFR Reference: {dbq.get('cfr_reference', 'N/A')}")
    output.append(f"Diagnostic Codes: {', '.join(dbq.get('diagnostic_codes', []))}")
    output.append("")

    if "rating_criteria" in include_sections:
        criteria = dbq.get("rating_criteria", {})
        if criteria:
            output.append("### Rating Criteria")
            output.append(criteria.get("description", ""))
            output.append("")

            levels = criteria.get("levels", [])
            for level in levels:
                output.append(
                    f"**{level.get('rating', 0)}%**: {level.get('criteria', '')}"
                )
            output.append("")

    if "tips" in include_sections:
        tips = dbq.get("tips_for_veterans", [])
        if tips:
            output.append("### Tips for Veterans")
            for tip in tips[:10]:  # Limit to first 10
                output.append(f"- {tip}")
            output.append("")

    if "common_mistakes" in include_sections:
        mistakes = dbq.get("common_mistakes", [])
        if mistakes:
            output.append("### Common Mistakes to Avoid")
            for mistake in mistakes:
                output.append(f"- {mistake}")
            output.append("")

    if "secondary_conditions" in include_sections:
        secondary = dbq.get("secondary_service_connection", {})
        if secondary:
            output.append("### Secondary Service Connection")
            primaries = secondary.get("common_primaries", [])
            for p in primaries:
                output.append(
                    f"- **{p.get('condition', '')}**: {p.get('connection', '')}"
                )
            output.append("")

    return "\n".join(output)


# Available DBQ categories
DBQ_CATEGORIES = [
    "mental_health",
    "musculoskeletal",
    "neurological",
    "respiratory",
    "cardiovascular",
    "endocrine",
    "special_senses",
]


# ============================================================================
# CFR (Code of Federal Regulations) Rating Schedule Functions
# ============================================================================


@lru_cache(maxsize=20)
def load_cfr_schedule(schedule_name: str) -> Optional[Dict]:
    """
    Load a CFR rating schedule by name.

    Args:
        schedule_name: Schedule name or key (e.g., 'mental_disorders', 'spine', 'knee')

    Returns:
        CFR schedule data dict or None if not found
    """
    # Normalize name
    name_lower = schedule_name.lower().replace(" ", "_").replace("-", "_")

    # Map common names to file names
    schedule_map = {
        "mental_disorders": "cfr_4_130_mental_disorders",
        "mental_health": "cfr_4_130_mental_disorders",
        "ptsd": "cfr_4_130_mental_disorders",
        "depression": "cfr_4_130_mental_disorders",
        "anxiety": "cfr_4_130_mental_disorders",
        "spine": "cfr_4_71a_spine",
        "back": "cfr_4_71a_spine",
        "neck": "cfr_4_71a_spine",
        "cervical": "cfr_4_71a_spine",
        "thoracolumbar": "cfr_4_71a_spine",
        "knee": "cfr_4_71a_knee",
        "leg": "cfr_4_71a_knee",
        "respiratory": "cfr_4_97_respiratory",
        "asthma": "cfr_4_97_respiratory",
        "copd": "cfr_4_97_respiratory",
        "sleep_apnea": "cfr_4_97_respiratory",
        "sinusitis": "cfr_4_97_respiratory",
        "cardiovascular": "cfr_4_104_cardiovascular",
        "heart": "cfr_4_104_cardiovascular",
        "cardiac": "cfr_4_104_cardiovascular",
        "hypertension": "cfr_4_104_cardiovascular",
        "neurological": "cfr_4_124a_neurological",
        "headaches": "cfr_4_124a_neurological",
        "migraines": "cfr_4_124a_neurological",
        "peripheral_nerves": "cfr_4_124a_neurological",
        "radiculopathy": "cfr_4_124a_neurological",
        "seizures": "cfr_4_124a_neurological",
        "endocrine": "cfr_4_119_endocrine",
        "diabetes": "cfr_4_119_endocrine",
        "thyroid": "cfr_4_119_endocrine",
        "special_provisions": "cfr_special_provisions",
        "combined_ratings": "cfr_special_provisions",
        "tdiu": "cfr_special_provisions",
        "presumptive": "cfr_special_provisions",
    }

    # Get filename
    filename = schedule_map.get(name_lower, f"cfr_{name_lower}")

    try:
        with open(CFR_DIR / f"{filename}.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def list_available_cfr_schedules() -> List[Dict]:
    """
    List all available CFR rating schedules.

    Returns:
        List of dicts with schedule info
    """
    schedules = []
    if not CFR_DIR.exists():
        return schedules

    for file in CFR_DIR.glob("*.json"):
        try:
            with open(file, "r") as f:
                data = json.load(f)
                schedules.append(
                    {
                        "file": file.stem,
                        "reference": data.get("cfr_reference", ""),
                        "title": data.get("title", file.stem),
                        "description": data.get("description", ""),
                    }
                )
        except (json.JSONDecodeError, KeyError):
            continue

    return sorted(schedules, key=lambda x: x["reference"])


def get_rating_criteria_by_code(diagnostic_code: str) -> Optional[Dict]:
    """
    Get rating criteria for a specific diagnostic code.

    Args:
        diagnostic_code: VA diagnostic code (e.g., '9411', '5260', '8100')

    Returns:
        Rating criteria dict or None
    """
    code = str(diagnostic_code)

    # Determine which schedule to check based on code range
    if code.startswith("9"):
        schedule = load_cfr_schedule("mental_disorders")
        if schedule:
            codes = schedule.get("diagnostic_codes", {})
            if code in codes:
                return {
                    "code": code,
                    "name": codes[code],
                    "rating_formula": schedule.get("general_rating_formula"),
                    "cfr_reference": schedule.get("cfr_reference"),
                }
    elif code.startswith("52") or code.startswith("50"):
        # Knee and musculoskeletal
        schedule = load_cfr_schedule("knee")
        if schedule:
            codes = schedule.get("diagnostic_codes", {})
            if code in codes:
                return {
                    "code": code,
                    "data": codes[code],
                    "cfr_reference": schedule.get("cfr_reference"),
                }
    elif code.startswith("81"):
        schedule = load_cfr_schedule("neurological")
        if schedule:
            return {
                "code": code,
                "cfr_reference": schedule.get("cfr_reference"),
                "headaches": schedule.get("headaches") if code == "8100" else None,
            }
    elif code.startswith("66") or code.startswith("68"):
        schedule = load_cfr_schedule("respiratory")
        if schedule:
            codes = schedule.get("diagnostic_codes", {})
            if code in codes:
                return {
                    "code": code,
                    "data": codes[code],
                    "cfr_reference": schedule.get("cfr_reference"),
                }
    elif code.startswith("70") or code.startswith("71"):
        schedule = load_cfr_schedule("cardiovascular")
        if schedule:
            codes = schedule.get("diagnostic_codes", {})
            if code in codes:
                return {
                    "code": code,
                    "data": codes[code],
                    "cfr_reference": schedule.get("cfr_reference"),
                }

    return None


def get_combined_rating(ratings: List[int]) -> int:
    """
    Calculate combined VA disability rating.

    Args:
        ratings: List of individual disability ratings (e.g., [30, 20, 10])

    Returns:
        Combined rating rounded to nearest 10
    """
    if not ratings:
        return 0

    # Sort ratings highest to lowest
    sorted_ratings = sorted(ratings, reverse=True)

    # Use combined ratings formula
    combined = 0
    for rating in sorted_ratings:
        # Combined = A + B(1-A)
        remaining = 100 - combined
        additional = (rating / 100) * remaining
        combined += additional

    # Round to nearest 10
    return round(combined / 10) * 10


def get_presumptive_conditions(exposure_type: str) -> List[str]:
    """
    Get list of presumptive conditions for a given exposure type.

    Args:
        exposure_type: Type of exposure ('agent_orange', 'pact_act', 'gulf_war')

    Returns:
        List of presumptive condition names
    """
    schedule = load_cfr_schedule("special_provisions")
    if not schedule:
        return []

    presumptive = schedule.get("presumptive_conditions", {})
    exposure_data = presumptive.get(exposure_type.lower(), {})

    conditions = exposure_data.get("conditions", [])
    if not conditions:
        # Check for nested condition lists
        conditions = exposure_data.get("respiratory_conditions", [])
        conditions.extend(exposure_data.get("other_conditions", []))

    return conditions


def format_cfr_for_prompt(schedule_name: str, max_length: int = 3000) -> str:
    """
    Format CFR schedule for inclusion in an AI prompt.

    Args:
        schedule_name: Schedule name
        max_length: Maximum character length

    Returns:
        Formatted string for prompt inclusion
    """
    schedule = load_cfr_schedule(schedule_name)
    if not schedule:
        return f"No CFR schedule found for: {schedule_name}"

    output = []
    output.append(f"## {schedule.get('title', schedule_name)}")
    output.append(f"Reference: {schedule.get('cfr_reference', 'N/A')}")
    output.append(f"Description: {schedule.get('description', '')}")
    output.append("")

    # Add rating levels if present
    if "general_rating_formula" in schedule:
        formula = schedule["general_rating_formula"]
        if isinstance(formula, dict):
            output.append("### Rating Formula")
            output.append(formula.get("name", ""))
            levels = formula.get("levels", [])
            for level in levels:
                output.append(
                    f"**{level.get('rating', 0)}%**: {level.get('summary', level.get('criteria', ''))}"
                )

    # Add important rules if present
    rules = schedule.get("important_rules", [])
    if rules:
        output.append("")
        output.append("### Important Rules")
        for rule in rules[:5]:
            output.append(f"- {rule}")

    result = "\n".join(output)

    if len(result) > max_length:
        result = result[:max_length] + "\n...[truncated]"

    return result


# Available CFR schedules for reference
CFR_SCHEDULES = [
    "mental_disorders",
    "spine",
    "knee",
    "respiratory",
    "cardiovascular",
    "neurological",
    "endocrine",
    "special_provisions",
]
