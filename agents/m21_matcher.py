"""
M21 Manual Section Matcher

Intelligent matching of VA denial reasons to relevant M21-1 manual sections.
Uses keyword matching, category mapping, and semantic relevance scoring.
"""

import logging
import re
from typing import List, Dict, Tuple
from django.db.models import Q

logger = logging.getLogger(__name__)


class M21Matcher:
    """
    Matches denial reasons and conditions to relevant M21-1 manual sections.

    Uses multiple strategies:
    1. Direct condition-to-section mapping (curated)
    2. Denial category to M21 part mapping
    3. Keyword-based search in M21 database
    4. Relevance scoring based on content overlap
    """

    # Map denial categories to relevant M21 parts
    # Part I: Claimants' Rights
    # Part II: Intake, Claims Establishment
    # Part III: Development Process
    # Part IV: Examinations
    # Part V: Rating Process
    # Part VI: Authorization Process
    CATEGORY_PART_MAP = {
        "service_connection": ["V"],  # Part V - Rating Process
        "nexus": ["V", "IV"],  # Part V Rating + Part IV Examinations
        "evidence": ["V", "III"],  # Part V + Part III Development
        "rating_level": ["V"],  # Part V - Rating criteria
        "current_diagnosis": ["V", "IV"],  # Part V + Part IV
        "in_service_event": ["V", "III"],  # Part V + Part III
        "procedural": ["I", "III"],  # Part I Rights + Part III Development
        "effective_date": ["V", "VI"],  # Part V + Part VI Authorization
        "aggravation": ["V"],  # Part V - Rating Process
        "presumptive": ["V"],  # Part V - Presumptive conditions
        "secondary": ["V"],  # Part V - Secondary SC
    }

    # Curated mapping of common conditions to M21 sections
    # Based on 365 scraped M21 sections
    CONDITION_SECTIONS = {
        # Mental Health
        "ptsd": ["V.ii.3", "V.ii.4", "IV.ii.1"],
        "depression": ["V.ii.3", "V.ii.4"],
        "anxiety": ["V.ii.3", "V.ii.4"],
        "bipolar": ["V.ii.3", "V.ii.4"],
        "mst": ["V.ii.3", "III.iv.4"],  # Military Sexual Trauma
        "tbi": ["V.ii.3", "IV.ii.1"],
        # Musculoskeletal
        "back": ["V.iii.1", "V.iii.2"],
        "neck": ["V.iii.1", "V.iii.2"],
        "knee": ["V.iii.1"],
        "shoulder": ["V.iii.1"],
        "hip": ["V.iii.1"],
        "ankle": ["V.iii.1"],
        "wrist": ["V.iii.1"],
        "elbow": ["V.iii.1"],
        # Respiratory
        "asthma": ["V.iii.4"],
        "sleep_apnea": ["V.iii.4"],
        "copd": ["V.iii.4"],
        # Cardiovascular
        "heart": ["V.iii.3"],
        "hypertension": ["V.iii.3"],
        "ischemic": ["V.iii.3"],
        # Hearing/Vision
        "hearing": ["V.iii.2"],
        "tinnitus": ["V.iii.2"],
        "vision": ["V.iii.2"],
        # Other
        "diabetes": ["V.iii.5"],
        "skin": ["V.iii.6"],
        "gerd": ["V.iii.5"],
        "migraines": ["V.ii.3"],
        "headaches": ["V.ii.3"],
    }

    # Keywords for each denial category (for search)
    CATEGORY_KEYWORDS = {
        "service_connection": [
            "service connection",
            "service-connection",
            "service connected",
            "direct service",
            "in-service incurrence",
            "incurred in service",
        ],
        "nexus": [
            "nexus",
            "medical nexus",
            "nexus opinion",
            "medical opinion",
            "at least as likely as not",
            "etiology",
            "causal relationship",
            "related to service",
            "link to service",
        ],
        "evidence": [
            "evidence",
            "lay evidence",
            "medical evidence",
            "competent evidence",
            "credible evidence",
            "probative value",
            "weight of evidence",
            "evidence requirements",
        ],
        "rating_level": [
            "rating",
            "evaluation",
            "diagnostic code",
            "rating criteria",
            "schedular",
            "percentage",
            "combined rating",
        ],
        "current_diagnosis": [
            "current diagnosis",
            "current disability",
            "diagnosed condition",
            "medical diagnosis",
            "competent diagnosis",
        ],
        "in_service_event": [
            "in-service event",
            "in service",
            "during service",
            "service records",
            "military records",
            "incident in service",
        ],
        "procedural": [
            "duty to assist",
            "notification",
            "due process",
            "vcaa",
            "notice",
            "procedural",
        ],
        "effective_date": [
            "effective date",
            "date of claim",
            "date of entitlement",
            "retroactive",
            "earlier effective date",
        ],
        "aggravation": [
            "aggravation",
            "aggravated",
            "worsened",
            "beyond natural progression",
            "pre-existing",
            "preexisting",
        ],
        "presumptive": [
            "presumptive",
            "presumption",
            "chronic disease",
            "tropical disease",
            "agent orange",
            "gulf war",
            "camp lejeune",
            "burn pit",
            "pact act",
        ],
        "secondary": [
            "secondary",
            "secondary service connection",
            "secondary condition",
            "caused by",
            "proximately due to",
            "aggravated by primary",
        ],
    }

    def __init__(self):
        """Initialize the M21 matcher."""
        self._model = None

    @property
    def M21ManualSection(self):
        """Lazy load M21ManualSection model to avoid circular imports."""
        if self._model is None:
            from agents.models import M21ManualSection

            self._model = M21ManualSection
        return self._model

    def find_relevant_sections(
        self,
        condition: str,
        denial_category: str,
        denial_reason: str = "",
        limit: int = 5,
    ) -> List[Dict]:
        """
        Find M21 sections relevant to this denial.

        Args:
            condition: The medical condition being claimed
            denial_category: Category of denial (nexus, evidence, etc.)
            denial_reason: Full text of denial reason
            limit: Maximum sections to return

        Returns:
            List of dicts with section info and relevance scores
        """
        sections = []
        seen_refs = set()

        # Strategy 1: Direct condition mapping
        condition_sections = self._get_condition_sections(condition)
        for section in condition_sections:
            if section.reference not in seen_refs:
                sections.append(self._section_to_dict(section, relevance=0.9))
                seen_refs.add(section.reference)

        # Strategy 2: Category-based part search
        category_sections = self._search_by_category(denial_category, condition)
        for section in category_sections:
            if section.reference not in seen_refs:
                sections.append(self._section_to_dict(section, relevance=0.7))
                seen_refs.add(section.reference)

        # Strategy 3: Keyword search in content
        keyword_sections = self._search_by_keywords(denial_category, denial_reason)
        for section in keyword_sections:
            if section.reference not in seen_refs:
                sections.append(self._section_to_dict(section, relevance=0.5))
                seen_refs.add(section.reference)

        # Sort by relevance and limit
        sections.sort(key=lambda x: x["relevance_score"], reverse=True)
        return sections[:limit]

    def _get_condition_sections(self, condition: str) -> List:
        """Get sections directly mapped to this condition."""
        condition_key = self._normalize_condition(condition)
        section_refs = self.CONDITION_SECTIONS.get(condition_key, [])

        sections = []
        for ref_prefix in section_refs:
            # Search for sections starting with this reference
            matches = self.M21ManualSection.objects.filter(
                reference__icontains=ref_prefix
            )[:3]
            sections.extend(matches)

        return sections

    def _search_by_category(self, category: str, condition: str) -> List:
        """Search M21 sections by denial category and condition."""
        parts = self.CATEGORY_PART_MAP.get(category, ["V"])

        # Build query for parts + condition keyword
        query = Q()
        for part in parts:
            query |= Q(part=part)

        # Add condition search if provided
        if condition:
            condition_normalized = self._normalize_condition(condition)
            query &= Q(search_text__icontains=condition_normalized) | Q(
                title__icontains=condition_normalized
            )

        return list(self.M21ManualSection.objects.filter(query)[:5])

    def _search_by_keywords(self, category: str, denial_reason: str) -> List:
        """Search M21 by category keywords and denial text."""
        keywords = self.CATEGORY_KEYWORDS.get(category, [])

        # Add words from denial reason
        if denial_reason:
            # Extract significant words (3+ chars, not common words)
            words = re.findall(r"\b[a-zA-Z]{3,}\b", denial_reason.lower())
            stop_words = {
                "the",
                "and",
                "for",
                "that",
                "with",
                "not",
                "has",
                "was",
                "are",
                "but",
            }
            keywords.extend([w for w in words if w not in stop_words])

        if not keywords:
            return []

        # Build OR query for keywords
        query = Q()
        for keyword in keywords[:10]:  # Limit to avoid overly complex queries
            query |= Q(search_text__icontains=keyword)

        return list(self.M21ManualSection.objects.filter(query)[:5])

    def _normalize_condition(self, condition: str) -> str:
        """Normalize condition name for matching."""
        condition = condition.lower().strip()

        # Common normalizations
        normalizations = {
            "post-traumatic stress disorder": "ptsd",
            "post traumatic stress disorder": "ptsd",
            "traumatic brain injury": "tbi",
            "sleep apnea": "sleep_apnea",
            "obstructive sleep apnea": "sleep_apnea",
            "lower back": "back",
            "lumbar spine": "back",
            "lumbosacral": "back",
            "cervical spine": "neck",
            "bilateral knee": "knee",
            "left knee": "knee",
            "right knee": "knee",
            "bilateral hearing loss": "hearing",
            "hearing loss": "hearing",
            "major depressive disorder": "depression",
            "generalized anxiety disorder": "anxiety",
            "ischemic heart disease": "heart",
            "coronary artery disease": "heart",
            "gastroesophageal reflux": "gerd",
            "acid reflux": "gerd",
            "migraine headaches": "migraines",
            "tension headaches": "headaches",
        }

        # Check direct normalizations
        for pattern, normalized in normalizations.items():
            if pattern in condition:
                return normalized

        # Return first significant word
        words = condition.split()
        for word in words:
            if len(word) > 3:
                return word

        return condition

    def _section_to_dict(self, section, relevance: float = 0.5) -> Dict:
        """Convert M21ManualSection to dict with relevance score."""
        # Extract a key excerpt (first 300 chars of overview or content)
        excerpt = section.overview[:300] if section.overview else section.content[:300]
        if len(excerpt) == 300:
            excerpt = excerpt.rsplit(" ", 1)[0] + "..."

        return {
            "reference": section.reference,
            "full_reference": section.full_reference,
            "title": section.title,
            "part": section.part,
            "part_title": section.part_title,
            "relevance_score": relevance,
            "key_excerpt": excerpt,
            "knowva_url": section.knowva_url,
        }

    def get_evidence_types_for_category(self, category: str) -> List[Dict]:
        """
        Get standard evidence types needed for a denial category.

        Returns list of evidence requirements with priority.
        """
        evidence_map = {
            "nexus": [
                {
                    "type": "nexus_letter",
                    "description": "Independent Medical Opinion (IMO) or nexus letter from a qualified medical professional",
                    "priority": "critical",
                    "tips": [
                        'Must include "at least as likely as not" language',
                        "Doctor should review service records and medical history",
                        "Include clear rationale explaining the connection",
                    ],
                },
                {
                    "type": "medical_records",
                    "description": "Complete medical treatment records showing continuity of symptoms",
                    "priority": "important",
                    "tips": [
                        "Include records from service to present",
                        "Highlight any statements linking to service",
                    ],
                },
            ],
            "evidence": [
                {
                    "type": "lay_statement",
                    "description": "Personal statement describing symptoms, impact, and history",
                    "priority": "important",
                    "tips": [
                        "Be specific about dates and events",
                        "Describe how symptoms affect daily life",
                        "Include worst day descriptions",
                    ],
                },
                {
                    "type": "buddy_statement",
                    "description": "Statements from family, friends, or fellow service members",
                    "priority": "helpful",
                    "tips": [
                        "Witnesses should describe what they personally observed",
                        "Include their relationship to you and time period",
                    ],
                },
                {
                    "type": "medical_records",
                    "description": "All relevant medical records",
                    "priority": "critical",
                    "tips": [
                        "Request complete records from all providers",
                        "Include VA and private treatment",
                    ],
                },
            ],
            "current_diagnosis": [
                {
                    "type": "diagnosis_letter",
                    "description": "Current diagnosis from a qualified medical professional",
                    "priority": "critical",
                    "tips": [
                        "Diagnosis should be based on current examination",
                        "Include diagnostic criteria met",
                        "Must use accepted diagnostic terminology",
                    ],
                },
                {
                    "type": "medical_records",
                    "description": "Recent treatment records showing the condition",
                    "priority": "important",
                    "tips": [
                        "Records should be within past 12 months",
                        "Include any diagnostic testing",
                    ],
                },
            ],
            "in_service_event": [
                {
                    "type": "service_records",
                    "description": "Military service records documenting the in-service event",
                    "priority": "critical",
                    "tips": [
                        "Request complete personnel and medical records",
                        "Include unit records if individual records unavailable",
                    ],
                },
                {
                    "type": "buddy_statement",
                    "description": "Statements from fellow service members who witnessed the event",
                    "priority": "important",
                    "tips": [
                        "Find veterans who served with you at the time",
                        "They should describe what they saw/heard",
                    ],
                },
                {
                    "type": "lay_statement",
                    "description": "Your detailed statement about the in-service event",
                    "priority": "important",
                    "tips": [
                        "Be as specific as possible about dates, locations, circumstances",
                        "Describe immediate aftermath and any treatment",
                    ],
                },
            ],
            "service_connection": [
                {
                    "type": "nexus_letter",
                    "description": "Medical opinion linking current condition to service",
                    "priority": "critical",
                    "tips": [
                        "Three elements: current diagnosis, in-service event, nexus"
                    ],
                },
                {
                    "type": "service_records",
                    "description": "Service records showing in-service event or symptoms",
                    "priority": "critical",
                    "tips": ["Any documentation from service period"],
                },
                {
                    "type": "medical_records",
                    "description": "Medical records showing current diagnosis",
                    "priority": "critical",
                    "tips": ["Must show you currently have the condition"],
                },
            ],
            "rating_level": [
                {
                    "type": "medical_records",
                    "description": "Medical records documenting symptom severity",
                    "priority": "critical",
                    "tips": [
                        "Records should show frequency and severity of symptoms",
                        "Document functional impairment",
                    ],
                },
                {
                    "type": "lay_statement",
                    "description": "Personal statement describing severity and impact",
                    "priority": "important",
                    "tips": [
                        "Describe your worst days",
                        "Explain how condition limits daily activities",
                        "Document impact on work and relationships",
                    ],
                },
                {
                    "type": "work_records",
                    "description": "Employment records showing impact on work",
                    "priority": "helpful",
                    "tips": ["Sick leave records, accommodations, performance issues"],
                },
            ],
            "secondary": [
                {
                    "type": "nexus_letter",
                    "description": "Medical opinion that primary condition caused or aggravated secondary condition",
                    "priority": "critical",
                    "tips": [
                        "Must link secondary to already service-connected condition",
                        "Can be causation OR aggravation theory",
                    ],
                },
                {
                    "type": "medical_records",
                    "description": "Records showing relationship between conditions",
                    "priority": "important",
                    "tips": [
                        "Timeline showing secondary developed after primary",
                        "Medical notes discussing relationship",
                    ],
                },
            ],
        }

        return evidence_map.get(category, evidence_map.get("evidence", []))

    def categorize_denial_reason(self, denial_reason: str) -> Tuple[str, float]:
        """
        Categorize a denial reason into a standard category.

        Returns:
            Tuple of (category, confidence)
        """
        reason_lower = denial_reason.lower()

        # Check for category indicators
        category_scores = {}

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in reason_lower:
                    score += 1
            if score > 0:
                category_scores[category] = score

        if not category_scores:
            return ("evidence", 0.3)  # Default to evidence category

        # Return highest scoring category
        best_category = max(category_scores, key=category_scores.get)
        confidence = min(category_scores[best_category] / 3, 1.0)

        return (best_category, confidence)
