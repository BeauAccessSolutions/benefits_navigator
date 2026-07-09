"""
Performance Baseline Tests

Measures baseline performance for critical operations.
Results are stored as artifacts for regression detection.

These tests:
- Use mocked external services (OpenAI, Celery)
- Measure view-level request handling time
- Are deterministic and repeatable

Run with:
    pytest tests/benchmarks/ -v
"""

import time
from statistics import mean

import pytest
from django.urls import reverse

from .conftest import record_benchmark

# =============================================================================
# Configuration
# =============================================================================

# Number of iterations for timing
ITERATIONS = 5

# Warm-up iterations (not counted)
WARMUP = 1


def benchmark(func, iterations=ITERATIONS, warmup=WARMUP):
    """
    Run a function multiple times and return timing statistics.

    Returns dict with mean, min, max times in seconds.
    """
    times = []

    # Warm-up runs
    for _ in range(warmup):
        func()

    # Timed runs
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append(end - start)

    return {
        "mean": mean(times),
        "min": min(times),
        "max": max(times),
        "iterations": iterations,
    }


# =============================================================================
# Document Upload View Benchmarks
# =============================================================================


@pytest.mark.django_db
class TestDocumentUploadPerformance:
    """Benchmark document upload request handling (view-level only, no OCR)."""

    def test_upload_page_load_time(self, authenticated_client, mock_celery):
        """Measure time to load the document upload page."""

        def load_page():
            response = authenticated_client.get(reverse("claims:document_upload"))
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("document_upload_page_load", results["mean"])

        print(f"\nDocument upload page load: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.5, f"Upload page load too slow: {results['mean']}s"

    def test_upload_form_submission_time(
        self, authenticated_client, mock_celery, sample_pdf_file
    ):
        """Measure time to submit document upload form (excluding processing)."""

        def submit_upload():
            # Need fresh file for each upload
            from django.core.files.uploadedfile import SimpleUploadedFile

            pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
0000000101 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
170
%%EOF"""
            test_file = SimpleUploadedFile(
                name="benchmark_test.pdf",
                content=pdf_content,
                content_type="application/pdf",
            )

            response = authenticated_client.post(
                reverse("claims:document_upload"),
                {
                    "file": test_file,
                    "document_type": "medical_records",
                },
                format="multipart",
            )
            # Should redirect after successful upload
            assert response.status_code in [200, 302]

        results = benchmark(submit_upload, iterations=3)  # Fewer iterations for writes
        record_benchmark("document_upload_form_submit", results["mean"])

        print(f"\nDocument upload form submit: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 1.0, f"Upload form submit too slow: {results['mean']}s"

    def test_document_list_load_time(self, authenticated_client):
        """Measure time to load document list page."""

        def load_list():
            response = authenticated_client.get(reverse("claims:document_list"))
            assert response.status_code == 200

        results = benchmark(load_list)
        record_benchmark("document_list_page_load", results["mean"])

        print(f"\nDocument list page load: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.5, f"Document list load too slow: {results['mean']}s"


# =============================================================================
# Agent View Benchmarks
# =============================================================================


@pytest.mark.django_db
class TestAgentViewPerformance:
    """Benchmark agent view request handling (no OpenAI calls)."""

    def test_decision_analyzer_page_load(self, authenticated_client, mock_openai):
        """Measure time to load decision analyzer page."""

        def load_page():
            response = authenticated_client.get(reverse("agents:decision_analyzer"))
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("decision_analyzer_page_load", results["mean"])

        print(f"\nDecision analyzer page load: {results['mean']*1000:.2f}ms (mean)")
        assert (
            results["mean"] < 0.5
        ), f"Decision analyzer load too slow: {results['mean']}s"

    def test_evidence_gap_page_load(self, authenticated_client, mock_openai):
        """Measure time to load evidence gap analyzer page."""

        def load_page():
            response = authenticated_client.get(reverse("agents:evidence_gap"))
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("evidence_gap_page_load", results["mean"])

        print(f"\nEvidence gap analyzer page load: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.5, f"Evidence gap load too slow: {results['mean']}s"

    def test_statement_generator_page_load(self, authenticated_client, mock_openai):
        """Measure time to load statement generator page."""

        def load_page():
            response = authenticated_client.get(reverse("agents:statement_generator"))
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("statement_generator_page_load", results["mean"])

        print(f"\nStatement generator page load: {results['mean']*1000:.2f}ms (mean)")
        assert (
            results["mean"] < 0.5
        ), f"Statement generator load too slow: {results['mean']}s"

    def test_agent_history_page_load(self, authenticated_client):
        """Measure time to load agent history page."""

        def load_page():
            response = authenticated_client.get(reverse("agents:history"))
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("agent_history_page_load", results["mean"])

        print(f"\nAgent history page load: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.5, f"Agent history load too slow: {results['mean']}s"


# =============================================================================
# Core View Benchmarks
# =============================================================================


@pytest.mark.django_db
class TestCoreViewPerformance:
    """Benchmark core application views."""

    def test_home_page_load(self, client):
        """Measure time to load home page (unauthenticated)."""
        from django.test import Client

        client = Client()

        def load_page():
            response = client.get("/", follow=True)
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("home_page_load", results["mean"])

        print(f"\nHome page load: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.3, f"Home page load too slow: {results['mean']}s"

    def test_dashboard_page_load(self, authenticated_client):
        """Measure time to load dashboard page."""

        def load_page():
            response = authenticated_client.get(reverse("dashboard"))
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("dashboard_page_load", results["mean"])

        print(f"\nDashboard page load: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.5, f"Dashboard load too slow: {results['mean']}s"

    def test_health_check_response_time(self, client):
        """Measure health check response time."""
        from django.test import Client

        client = Client()

        def check_health():
            response = client.get("/health/", follow=True)
            assert response.status_code == 200

        results = benchmark(check_health, iterations=10)
        record_benchmark("health_check_response", results["mean"])

        print(f"\nHealth check response: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.1, f"Health check too slow: {results['mean']}s"


# =============================================================================
# Exam Prep View Benchmarks
# =============================================================================


@pytest.mark.django_db
class TestExamPrepPerformance:
    """Benchmark exam prep views (public, high-traffic)."""

    def test_rating_calculator_load(self, client):
        """Measure time to load rating calculator."""
        from django.test import Client

        client = Client()

        def load_page():
            response = client.get("/exam-prep/rating-calculator/")
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("rating_calculator_page_load", results["mean"])

        print(f"\nRating calculator page load: {results['mean']*1000:.2f}ms (mean)")
        assert (
            results["mean"] < 0.5
        ), f"Rating calculator load too slow: {results['mean']}s"

    def test_glossary_list_load(self, client):
        """Measure time to load glossary list."""
        from django.test import Client

        client = Client()

        def load_page():
            response = client.get("/exam-prep/glossary/")
            assert response.status_code == 200

        results = benchmark(load_page)
        record_benchmark("glossary_list_page_load", results["mean"])

        print(f"\nGlossary list page load: {results['mean']*1000:.2f}ms (mean)")
        assert results["mean"] < 0.5, f"Glossary list load too slow: {results['mean']}s"
