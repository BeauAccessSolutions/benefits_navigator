"""
OCR Service - Extract text from documents using Tesseract
"""

import logging
from pathlib import Path
from typing import Dict

import pytesseract
from PIL import Image
import fitz  # PyMuPDF

from django.conf import settings

logger = logging.getLogger(__name__)


class OCRService:
    """
    Service for extracting text from documents using Tesseract OCR
    Supports PDFs and images
    """

    def __init__(self):
        # Configure Tesseract command path if specified in settings
        if hasattr(settings, "TESSERACT_CMD"):
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    def extract_text(self, file_path: str) -> Dict:
        """
        Extract text from document

        Args:
            file_path: Path to document file

        Returns:
            dict with keys:
                - text: Extracted text
                - confidence: Average confidence score (0-100)
                - page_count: Number of pages processed
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Determine file type and process accordingly
        file_ext = file_path.suffix.lower()

        if file_ext == ".pdf":
            return self._extract_from_pdf(file_path)
        elif file_ext in [".jpg", ".jpeg", ".png", ".tiff", ".tif"]:
            return self._extract_from_image(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

    def _extract_from_image(self, image_path: Path) -> Dict:
        """
        Extract text from a single image
        """
        try:
            image = Image.open(image_path)

            # Run Tesseract OCR
            # Using --psm 1 for automatic page segmentation with OSD
            custom_config = r"--psm 1"
            data = pytesseract.image_to_data(
                image, config=custom_config, output_type=pytesseract.Output.DICT
            )
            text = pytesseract.image_to_string(image, config=custom_config)

            # Calculate average confidence
            confidences = [int(conf) for conf in data["conf"] if conf != "-1"]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            logger.info(
                f"Extracted {len(text)} characters from image with {avg_confidence:.1f}% confidence"
            )

            return {
                "text": text.strip(),
                "confidence": round(avg_confidence, 2),
                "page_count": 1,
            }

        except Exception as e:
            logger.error(f"Error extracting text from image: {str(e)}")
            raise

    def _extract_from_pdf(self, pdf_path: Path) -> Dict:
        """
        Extract text from PDF
        First tries native PDF text extraction, falls back to OCR if needed
        """
        try:
            pdf_document = fitz.open(pdf_path)
            page_count = len(pdf_document)
            all_text = []
            confidences = []

            logger.info(f"Processing PDF with {page_count} pages")

            for page_num in range(page_count):
                page = pdf_document[page_num]

                # First, try native text extraction (for PDFs with embedded text)
                native_text = page.get_text().strip()

                if native_text and len(native_text) > 50:
                    # PDF has embedded text, use it
                    all_text.append(native_text)
                    confidences.append(100)  # Native text is 100% confident
                    logger.debug(f"Page {page_num + 1}: Using native text extraction")
                else:
                    # No embedded text, use OCR
                    logger.debug(f"Page {page_num + 1}: Using OCR")

                    # Render page to image
                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(2, 2)
                    )  # 2x zoom for better OCR
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    # Run OCR
                    custom_config = r"--psm 1"
                    data = pytesseract.image_to_data(
                        img, config=custom_config, output_type=pytesseract.Output.DICT
                    )
                    page_text = pytesseract.image_to_string(img, config=custom_config)

                    all_text.append(page_text.strip())

                    # Calculate page confidence
                    page_confidences = [
                        int(conf) for conf in data["conf"] if conf != "-1"
                    ]
                    page_avg_conf = (
                        sum(page_confidences) / len(page_confidences)
                        if page_confidences
                        else 0
                    )
                    confidences.append(page_avg_conf)

            pdf_document.close()

            # Combine all pages
            full_text = "\n\n".join([text for text in all_text if text])
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            logger.info(
                f"Extracted {len(full_text)} characters from {page_count}-page PDF with {avg_confidence:.1f}% confidence"
            )

            return {
                "text": full_text,
                "confidence": round(avg_confidence, 2),
                "page_count": page_count,
            }

        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            raise
