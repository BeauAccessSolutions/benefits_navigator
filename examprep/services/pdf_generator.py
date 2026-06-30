"""
PDF Generator for VA Rating Calculations

Generates professional PDF exports of rating calculations
with VA Math breakdown and compensation estimates.
"""

import io
from datetime import date
from typing import List, Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER


class RatingCalculationPDF:
    """
    Generate a PDF document for a VA disability rating calculation.
    """

    def __init__(
        self,
        ratings: List[Dict[str, Any]],
        combined_raw: float,
        combined_rounded: int,
        bilateral_factor: float,
        monthly_compensation: str,
        annual_compensation: str,
        step_by_step: List[Dict[str, Any]],
        has_spouse: bool = False,
        children_under_18: int = 0,
        dependent_parents: int = 0,
        calculation_name: Optional[str] = None,
    ):
        self.ratings = ratings
        self.combined_raw = combined_raw
        self.combined_rounded = combined_rounded
        self.bilateral_factor = bilateral_factor
        self.monthly_compensation = monthly_compensation
        self.annual_compensation = annual_compensation
        self.step_by_step = step_by_step
        self.has_spouse = has_spouse
        self.children_under_18 = children_under_18
        self.dependent_parents = dependent_parents
        self.calculation_name = calculation_name or "VA Rating Calculation"

        # Set up styles
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Create custom paragraph styles."""
        self.styles.add(
            ParagraphStyle(
                name="VATitle",
                parent=self.styles["Heading1"],
                fontSize=18,
                spaceAfter=12,
                textColor=colors.HexColor("#1e3a8a"),  # blue-900
                alignment=TA_CENTER,
            )
        )

        self.styles.add(
            ParagraphStyle(
                name="VASectionHeader",
                parent=self.styles["Heading2"],
                fontSize=14,
                spaceBefore=16,
                spaceAfter=8,
                textColor=colors.HexColor("#1e3a8a"),
            )
        )

        self.styles.add(
            ParagraphStyle(
                name="VASubHeader",
                parent=self.styles["Heading3"],
                fontSize=11,
                spaceBefore=8,
                spaceAfter=4,
                textColor=colors.HexColor("#374151"),  # gray-700
            )
        )

        self.styles.add(
            ParagraphStyle(
                name="VABodyText",
                parent=self.styles["Normal"],
                fontSize=10,
                spaceAfter=6,
            )
        )

        self.styles.add(
            ParagraphStyle(
                name="VADisclaimer",
                parent=self.styles["Normal"],
                fontSize=8,
                textColor=colors.HexColor("#6b7280"),  # gray-500
                spaceBefore=12,
            )
        )

        self.styles.add(
            ParagraphStyle(
                name="VAResultLarge",
                parent=self.styles["Normal"],
                fontSize=24,
                textColor=colors.HexColor("#059669"),  # green-600
                alignment=TA_CENTER,
                spaceBefore=8,
                spaceAfter=8,
            )
        )

    def generate(self) -> bytes:
        """Generate the PDF and return as bytes."""
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        # Build the document content
        story = []

        # Header
        story.append(Paragraph("VA Benefits Navigator", self.styles["VATitle"]))
        story.append(Paragraph(self.calculation_name, self.styles["VASectionHeader"]))
        story.append(
            Paragraph(
                f"Generated: {date.today().strftime('%B %d, %Y')}",
                self.styles["VABodyText"],
            )
        )
        story.append(Spacer(1, 12))

        # Horizontal line
        story.append(
            HRFlowable(
                width="100%",
                thickness=1,
                color=colors.HexColor("#d1d5db"),
                spaceBefore=6,
                spaceAfter=12,
            )
        )

        # Combined Rating Result
        story.append(
            Paragraph("Combined VA Disability Rating", self.styles["VASectionHeader"])
        )
        story.append(
            Paragraph(f"{self.combined_rounded}%", self.styles["VAResultLarge"])
        )

        if self.combined_raw != self.combined_rounded:
            story.append(
                Paragraph(
                    f"(Calculated: {self.combined_raw:.2f}%, rounded to {self.combined_rounded}%)",
                    ParagraphStyle(
                        "CenteredSmall",
                        parent=self.styles["Normal"],
                        fontSize=9,
                        alignment=TA_CENTER,
                        textColor=colors.HexColor("#6b7280"),
                    ),
                )
            )

        story.append(Spacer(1, 12))

        # Compensation Estimate
        story.append(
            Paragraph("Estimated Monthly Compensation", self.styles["VASubHeader"])
        )

        comp_data = [
            ["Monthly:", self.monthly_compensation],
            ["Annual:", self.annual_compensation],
        ]

        comp_table = Table(comp_data, colWidths=[2 * inch, 2 * inch])
        comp_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#059669")),
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (1, -1), "LEFT"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(comp_table)

        # Dependents info
        dependents = []
        if self.has_spouse:
            dependents.append("Spouse")
        if self.children_under_18 > 0:
            dependents.append(f"{self.children_under_18} child(ren) under 18")
        if self.dependent_parents > 0:
            dependents.append(f"{self.dependent_parents} dependent parent(s)")

        if dependents:
            story.append(
                Paragraph(
                    f"Includes: {', '.join(dependents)}", self.styles["VABodyText"]
                )
            )
        else:
            story.append(
                Paragraph("Veteran only (no dependents)", self.styles["VABodyText"])
            )

        story.append(Spacer(1, 12))

        # Individual Ratings Table
        story.append(
            Paragraph("Individual Disability Ratings", self.styles["VASectionHeader"])
        )

        if self.ratings:
            ratings_data = [["Condition", "Rating", "Bilateral"]]
            for r in self.ratings:
                bilateral = "Yes" if r.get("is_bilateral") else "No"
                ratings_data.append(
                    [
                        r.get("description", "Unnamed condition"),
                        f"{r.get('percentage', 0)}%",
                        bilateral,
                    ]
                )

            ratings_table = Table(
                ratings_data, colWidths=[3.5 * inch, 1.25 * inch, 1.25 * inch]
            )
            ratings_table.setStyle(
                TableStyle(
                    [
                        # Header row
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                        ("TOPPADDING", (0, 0), (-1, 0), 8),
                        # Data rows
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 10),
                        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                        ("TOPPADDING", (0, 1), (-1, -1), 6),
                        # Grid
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                        # Alternating row colors
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f3f4f6")],
                        ),
                    ]
                )
            )
            story.append(ratings_table)
        else:
            story.append(Paragraph("No ratings entered.", self.styles["VABodyText"]))

        story.append(Spacer(1, 12))

        # Bilateral Factor
        if self.bilateral_factor > 0:
            story.append(
                Paragraph("Bilateral Factor Applied", self.styles["VASubHeader"])
            )
            story.append(
                Paragraph(
                    f"A bilateral factor of {self.bilateral_factor:.2f}% was applied because you have "
                    "disabilities affecting both sides of your body.",
                    self.styles["VABodyText"],
                )
            )
            story.append(Spacer(1, 8))

        # VA Math Calculation Steps
        if self.step_by_step:
            story.append(
                Paragraph("VA Math Calculation Steps", self.styles["VASectionHeader"])
            )
            story.append(
                Paragraph(
                    "The VA uses a special formula to combine multiple disabilities. "
                    "Each rating is applied to your remaining 'whole person' value:",
                    self.styles["VABodyText"],
                )
            )

            steps_data = [["Step", "Description", "Result"]]
            for i, step in enumerate(self.step_by_step, 1):
                steps_data.append(
                    [str(i), step.get("description", ""), step.get("result", "")]
                )

            steps_table = Table(
                steps_data, colWidths=[0.5 * inch, 4.5 * inch, 1 * inch]
            )
            steps_table.setStyle(
                TableStyle(
                    [
                        # Header
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                        # Data
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("ALIGN", (0, 1), (0, -1), "CENTER"),
                        ("ALIGN", (2, 1), (2, -1), "CENTER"),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                        ("TOPPADDING", (0, 1), (-1, -1), 4),
                        # Grid
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f9fafb")],
                        ),
                    ]
                )
            )
            story.append(steps_table)

        story.append(Spacer(1, 16))

        # Legal Disclaimer
        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.HexColor("#d1d5db"),
                spaceBefore=12,
                spaceAfter=8,
            )
        )

        disclaimer_text = (
            "<b>Disclaimer:</b> This calculation is for informational purposes only and does not "
            "constitute legal or financial advice. Actual VA disability compensation may vary based "
            "on individual circumstances, effective dates, and current VA compensation rates. "
            "The calculation uses 2024 VA compensation rates. For official determinations, "
            "consult with a VA-accredited representative or the Department of Veterans Affairs. "
            "This document was generated by VA Benefits Navigator."
        )
        story.append(Paragraph(disclaimer_text, self.styles["VADisclaimer"]))

        # Reference
        story.append(
            Paragraph(
                "VA Math formula based on 38 CFR 4.25. Compensation rates from VA.gov.",
                self.styles["VADisclaimer"],
            )
        )

        # Build PDF
        doc.build(story)

        # Get the PDF bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes


def generate_rating_pdf(
    ratings: List[Dict[str, Any]],
    combined_raw: float,
    combined_rounded: int,
    bilateral_factor: float,
    monthly_compensation: str,
    annual_compensation: str,
    step_by_step: List[Dict[str, Any]],
    has_spouse: bool = False,
    children_under_18: int = 0,
    dependent_parents: int = 0,
    calculation_name: Optional[str] = None,
) -> bytes:
    """
    Generate a PDF for a rating calculation.

    Args:
        ratings: List of disability ratings
        combined_raw: Raw combined percentage before rounding
        combined_rounded: Final combined rating rounded to nearest 10
        bilateral_factor: Bilateral factor applied (if any)
        monthly_compensation: Formatted monthly compensation string
        annual_compensation: Formatted annual compensation string
        step_by_step: List of calculation steps
        has_spouse: Whether veteran has a spouse
        children_under_18: Number of children under 18
        dependent_parents: Number of dependent parents
        calculation_name: Optional name for the calculation

    Returns:
        PDF file as bytes
    """
    generator = RatingCalculationPDF(
        ratings=ratings,
        combined_raw=combined_raw,
        combined_rounded=combined_rounded,
        bilateral_factor=bilateral_factor,
        monthly_compensation=monthly_compensation,
        annual_compensation=annual_compensation,
        step_by_step=step_by_step,
        has_spouse=has_spouse,
        children_under_18=children_under_18,
        dependent_parents=dependent_parents,
        calculation_name=calculation_name,
    )

    return generator.generate()
