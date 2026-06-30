#!/usr/bin/env python3
"""
Parse M21-1 Adjudication Procedures Manual into structured JSON
"""

import re
import json
from pathlib import Path


def parse_m21_manual(input_file: str, output_dir: str):
    """Parse M21 raw text into structured JSON files"""

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Build hierarchical structure
    manual = {"title": "M21-1 Adjudication Procedures Manual", "parts": {}}

    # More precise pattern - must match exactly: Part X, Subpart x, Chapter N, Section L - Title
    section_header_pattern = re.compile(
        r"^M21-1, Part ([IVX]+), Subpart ([ivx]+), Chapter (\d+), Section ([A-Z]) - (.+)$"
    )

    current_section = None
    section_content = []

    for line in lines:
        line = line.rstrip("\n")

        # Check if this is a section header (must be at start of line and have full format)
        header_match = section_header_pattern.match(line)

        if header_match:
            # Save previous section if exists
            if current_section:
                save_section(manual, current_section, "\n".join(section_content))

            # Start new section
            current_section = {
                "part": header_match.group(1),
                "subpart": header_match.group(2),
                "chapter": header_match.group(3),
                "section": header_match.group(4),
                "title": header_match.group(5).strip(),
            }
            section_content = []
        elif current_section:
            # This is content for current section
            section_content.append(line)

    # Save last section
    if current_section:
        save_section(manual, current_section, "\n".join(section_content))

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Save complete manual
    with open(output_path / "m21_complete.json", "w", encoding="utf-8") as f:
        json.dump(manual, f, indent=2, ensure_ascii=False)

    # Save individual parts for easier access
    for part_num, part_data in manual["parts"].items():
        part_file = (
            output_path
            / f'm21_part_{part_num.lower().replace("i", "1").replace("v", "5").replace("x", "10")}.json'
        )
        # Use simpler naming
        part_file = output_path / f"m21_part_{roman_to_int(part_num)}.json"
        with open(part_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "part": part_num,
                    "part_number": roman_to_int(part_num),
                    "title": get_part_title(part_num),
                    "subparts": part_data,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

    # Create a summary/index file
    create_index(manual, output_path)

    # Create topic-based extracts for agents
    create_agent_references(manual, output_path)

    # Create searchable flat file
    create_searchable_index(manual, output_path)

    print(
        f"Parsed {count_sections(manual)} sections across {len(manual['parts'])} parts"
    )
    return manual


def roman_to_int(roman):
    """Convert Roman numeral to integer"""
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    result = 0
    prev = 0
    for char in reversed(roman.upper()):
        curr = values.get(char, 0)
        if curr < prev:
            result -= curr
        else:
            result += curr
        prev = curr
    return result


def save_section(manual, section_info, content):
    """Save a section to the manual structure"""
    part = section_info["part"]
    subpart = section_info["subpart"]
    chapter = section_info["chapter"]
    section = section_info["section"]

    if part not in manual["parts"]:
        manual["parts"][part] = {}

    if subpart not in manual["parts"][part]:
        manual["parts"][part][subpart] = {}

    if chapter not in manual["parts"][part][subpart]:
        manual["parts"][part][subpart][chapter] = {}

    # Parse content into structured data
    parsed_content = parse_section_content(content, section_info)

    manual["parts"][part][subpart][chapter][section] = {
        "title": section_info["title"],
        "reference": f"M21-1.{part}.{subpart}.{chapter}.{section}",
        "full_reference": f"M21-1, Part {part}, Subpart {subpart}, Chapter {chapter}, Section {section}",
        **parsed_content,
    }


def parse_section_content(content, section_info):
    """Parse section content into structured data"""
    result = {"overview": "", "topics": [], "references": [], "key_points": []}

    lines = content.split("\n")

    # Extract article metadata
    for i, line in enumerate(lines):
        if line.startswith("Article ID:"):
            result["article_id"] = line.replace("Article ID:", "").strip()
        elif line.startswith("Updated"):
            result["last_updated"] = line.replace("Updated", "").strip()

    # Pattern for topic codes like "I.i.1.A.1.a."
    topic_code_pattern = re.compile(
        rf'^{re.escape(section_info["part"])}\.{re.escape(section_info["subpart"])}\.{re.escape(section_info["chapter"])}\.{re.escape(section_info["section"])}\.(\d+)\.([a-z])\.\s*(.+)?$'
    )

    # Also match numbered topics like "1.  Topic Title"
    numbered_topic_pattern = re.compile(r"^(\d+)\.\s{2,}(.+)$")

    current_topic = None
    topic_content = []
    in_overview = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_topic and topic_content:
                topic_content.append("")
            continue

        # Skip metadata lines
        if (
            stripped.startswith("Article ID:")
            or stripped.startswith("Updated")
            or stripped == "Next Section -->"
        ):
            continue

        # Check for topic code
        code_match = topic_code_pattern.match(stripped)
        numbered_match = numbered_topic_pattern.match(stripped)

        if code_match:
            in_overview = False
            # Save previous topic
            if current_topic:
                current_topic["content"] = clean_content("\n".join(topic_content))
                result["topics"].append(current_topic)

            title = code_match.group(3) if code_match.group(3) else ""
            current_topic = {
                "code": f"{section_info['part']}.{section_info['subpart']}.{section_info['chapter']}.{section_info['section']}.{code_match.group(1)}.{code_match.group(2)}",
                "topic_num": code_match.group(1),
                "subtopic": code_match.group(2),
                "title": title.strip(),
                "content": "",
            }
            topic_content = []

        elif numbered_match and in_overview:
            # This might be a topic list in overview
            if "topic_list" not in result:
                result["topic_list"] = []
            result["topic_list"].append(
                {
                    "num": numbered_match.group(1),
                    "name": numbered_match.group(2).strip(),
                }
            )

        elif current_topic:
            topic_content.append(stripped)

        elif in_overview and stripped not in [
            "Overview",
            "In This Section",
            "This section contains the following topics:",
        ]:
            if stripped.startswith("Topic") and "Topic Name" in stripped:
                continue  # Skip table headers
            result["overview"] += stripped + " "

    # Save last topic
    if current_topic:
        current_topic["content"] = clean_content("\n".join(topic_content))
        result["topics"].append(current_topic)

    result["overview"] = clean_content(result["overview"])

    # Extract references from content
    ref_pattern = re.compile(r"M21-1, Part [IVX]+, Subpart [ivx]+, [\d\.A-Za-z]+")
    cfr_pattern = re.compile(r"38 CFR [\d\.]+")

    full_content = content
    for match in ref_pattern.finditer(full_content):
        if match.group() not in result["references"]:
            result["references"].append(match.group())

    for match in cfr_pattern.finditer(full_content):
        cfr_ref = match.group()
        if cfr_ref not in result["references"]:
            result["references"].append(cfr_ref)

    return result


def clean_content(content):
    """Clean up content text"""
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = re.sub(r" {2,}", " ", content)
    content = re.sub(r"\n +", "\n", content)
    return content.strip()


def get_part_title(part_num):
    """Get the title for a part number"""
    titles = {
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
    return titles.get(part_num, f"Part {part_num}")


def count_sections(manual):
    """Count total sections in manual"""
    count = 0
    for part in manual["parts"].values():
        for subpart in part.values():
            for chapter in subpart.values():
                count += len(chapter)
    return count


def create_index(manual, output_path):
    """Create an index file for quick lookups"""
    index = {"parts": [], "total_sections": 0}

    for part_num in sorted(manual["parts"].keys(), key=roman_to_int):
        part_data = manual["parts"][part_num]
        part_info = {
            "part": part_num,
            "part_number": roman_to_int(part_num),
            "title": get_part_title(part_num),
            "subparts": [],
        }

        for subpart_num in sorted(part_data.keys()):
            subpart_data = part_data[subpart_num]
            subpart_info = {"subpart": subpart_num, "chapters": []}

            for chapter_num in sorted(subpart_data.keys(), key=int):
                chapter_data = subpart_data[chapter_num]
                chapter_info = {"chapter": chapter_num, "sections": []}

                for section_letter in sorted(chapter_data.keys()):
                    section_data = chapter_data[section_letter]
                    section_info = {
                        "section": section_letter,
                        "title": section_data["title"],
                        "reference": section_data["reference"],
                        "topic_count": len(section_data.get("topics", [])),
                    }
                    chapter_info["sections"].append(section_info)
                    index["total_sections"] += 1

                subpart_info["chapters"].append(chapter_info)

            part_info["subparts"].append(subpart_info)

        index["parts"].append(part_info)

    with open(output_path / "m21_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def create_agent_references(manual, output_path):
    """Create topic-specific reference files for AI agents"""

    # Key topics for agents
    agent_topics = {
        "service_connection": {
            "title": "Service Connection",
            "description": "How VA establishes service connection for disabilities",
            "keywords": [
                "service connection",
                "service-connection",
                "nexus",
                "in-service",
                "direct service",
                "secondary service",
                "presumptive",
                "aggravation",
            ],
            "sections": [],
        },
        "rating_process": {
            "title": "Rating Process",
            "description": "How VA rates disabilities and assigns percentages",
            "keywords": [
                "rating",
                "evaluation",
                "diagnostic code",
                "schedule for rating",
                "percentage",
                "combined rating",
            ],
            "sections": [],
        },
        "evidence": {
            "title": "Evidence Requirements",
            "description": "What evidence VA needs and how it weighs evidence",
            "keywords": [
                "evidence",
                "medical records",
                "lay evidence",
                "buddy statement",
                "nexus letter",
                "weighing evidence",
                "credibility",
            ],
            "sections": [],
        },
        "examinations": {
            "title": "C&P Examinations",
            "description": "Compensation & Pension exam procedures",
            "keywords": [
                "examination",
                "C&P",
                "DBQ",
                "medical opinion",
                "examiner",
                "exam request",
            ],
            "sections": [],
        },
        "effective_dates": {
            "title": "Effective Dates",
            "description": "How VA determines effective dates for benefits",
            "keywords": [
                "effective date",
                "date of claim",
                "date entitlement",
                "earlier effective date",
            ],
            "sections": [],
        },
        "appeals": {
            "title": "Appeals Process",
            "description": "Appeal lanes and procedures",
            "keywords": [
                "appeal",
                "higher-level review",
                "HLR",
                "supplemental claim",
                "board of veterans",
                "NOD",
                "notice of disagreement",
            ],
            "sections": [],
        },
        "mental_health": {
            "title": "Mental Health Conditions",
            "description": "Rating mental health disabilities including PTSD",
            "keywords": [
                "mental",
                "PTSD",
                "depression",
                "anxiety",
                "psychiatric",
                "mental disorder",
                "psychological",
            ],
            "sections": [],
        },
        "musculoskeletal": {
            "title": "Musculoskeletal Conditions",
            "description": "Rating physical disabilities of joints and spine",
            "keywords": [
                "musculoskeletal",
                "range of motion",
                "ROM",
                "joint",
                "spine",
                "back",
                "knee",
                "shoulder",
                "orthopedic",
            ],
            "sections": [],
        },
        "special_monthly_compensation": {
            "title": "Special Monthly Compensation (SMC)",
            "description": "Additional compensation for severe disabilities",
            "keywords": [
                "special monthly compensation",
                "SMC",
                "aid and attendance",
                "housebound",
            ],
            "sections": [],
        },
        "tdiu": {
            "title": "TDIU - Total Disability Individual Unemployability",
            "description": "Unemployability due to service-connected disabilities",
            "keywords": [
                "TDIU",
                "unemployability",
                "individual unemployability",
                "unable to work",
            ],
            "sections": [],
        },
    }

    # Search sections for keywords
    for part_num, part_data in manual["parts"].items():
        for subpart_num, subpart_data in part_data.items():
            for chapter_num, chapter_data in subpart_data.items():
                for section_letter, section_data in chapter_data.items():
                    # Build searchable text
                    section_text = section_data["title"].lower() + " "
                    section_text += section_data.get("overview", "").lower() + " "

                    for topic in section_data.get("topics", []):
                        section_text += topic.get("title", "").lower() + " "
                        section_text += topic.get("content", "").lower() + " "

                    # Check each agent topic
                    for topic_name, topic_info in agent_topics.items():
                        for keyword in topic_info["keywords"]:
                            if keyword.lower() in section_text:
                                topic_info["sections"].append(
                                    {
                                        "reference": section_data["reference"],
                                        "full_reference": section_data.get(
                                            "full_reference", ""
                                        ),
                                        "title": section_data["title"],
                                        "part": part_num,
                                        "part_title": get_part_title(part_num),
                                        "matched_keyword": keyword,
                                    }
                                )
                                break  # Only add once per section

    # Remove duplicates and sort
    for topic_name, topic_info in agent_topics.items():
        seen = set()
        unique_sections = []
        for section in topic_info["sections"]:
            if section["reference"] not in seen:
                seen.add(section["reference"])
                unique_sections.append(section)
        topic_info["sections"] = sorted(unique_sections, key=lambda x: x["reference"])
        topic_info["section_count"] = len(unique_sections)

    with open(output_path / "m21_agent_topics.json", "w", encoding="utf-8") as f:
        json.dump(agent_topics, f, indent=2, ensure_ascii=False)

    print("\nCreated agent topic references:")
    for topic_name, topic_info in agent_topics.items():
        print(f"  - {topic_info['title']}: {len(topic_info['sections'])} sections")


def create_searchable_index(manual, output_path):
    """Create a flat searchable index for quick lookups"""

    searchable = []

    for part_num, part_data in manual["parts"].items():
        for subpart_num, subpart_data in part_data.items():
            for chapter_num, chapter_data in subpart_data.items():
                for section_letter, section_data in chapter_data.items():
                    entry = {
                        "reference": section_data["reference"],
                        "full_reference": section_data.get("full_reference", ""),
                        "part": part_num,
                        "part_number": roman_to_int(part_num),
                        "part_title": get_part_title(part_num),
                        "subpart": subpart_num,
                        "chapter": chapter_num,
                        "section": section_letter,
                        "title": section_data["title"],
                        "overview": section_data.get("overview", "")[
                            :500
                        ],  # First 500 chars
                        "topic_count": len(section_data.get("topics", [])),
                        "topics": [
                            t.get("title", "")
                            for t in section_data.get("topics", [])
                            if t.get("title")
                        ],
                        "references": section_data.get("references", [])[
                            :10
                        ],  # First 10 refs
                        "last_updated": section_data.get("last_updated", ""),
                    }
                    searchable.append(entry)

    # Sort by part, subpart, chapter, section
    searchable.sort(
        key=lambda x: (x["part_number"], x["subpart"], int(x["chapter"]), x["section"])
    )

    with open(output_path / "m21_searchable.json", "w", encoding="utf-8") as f:
        json.dump(searchable, f, indent=2, ensure_ascii=False)

    print(f"\nCreated searchable index with {len(searchable)} entries")


if __name__ == "__main__":
    input_file = "/Users/zachbeaudoin/benefits-navigator/Research Docs/M21/m21_raw.txt"
    output_dir = "/Users/zachbeaudoin/benefits-navigator/Research Docs/M21/parsed"

    parse_m21_manual(input_file, output_dir)
