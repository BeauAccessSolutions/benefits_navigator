#!/usr/bin/env python3
"""
Security Invariants Checker

Static analysis script that verifies security invariants are maintained.
Run by CI on every PR and push to main.

Usage:
    python scripts/check_security_invariants.py
    python scripts/check_security_invariants.py --verbose

Exit codes:
    0 - All checks passed
    1 - One or more violations found
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

# =============================================================================
# Configuration
# =============================================================================

# Directory names to exclude (checked against Path.parts)
EXCLUDED_DIRS: Set[str] = {
    "venv",
    ".venv",
    "__pycache__",
    "migrations",
    "tests",
    ".git",
    "node_modules",
    "static",
    "media",
    "staticfiles",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "htmlcov",
    "dist",
    "build",
    "eggs",
    "*.egg-info",
}

# Files to always exclude
EXCLUDED_FILES: Set[str] = {
    "check_security_invariants.py",  # This script
}


@dataclass
class Violation:
    """A security invariant violation."""

    check: str
    file: str
    line: int
    message: str
    severity: str = "error"  # error, warning

    def __str__(self):
        return f"[{self.severity.upper()}] {self.file}:{self.line} - {self.check}: {self.message}"


class SecurityChecker:
    """Runs security invariant checks against the codebase."""

    def __init__(self, root_dir: Path, verbose: bool = False):
        self.root_dir = root_dir
        self.verbose = verbose
        self.violations: List[Violation] = []

    def log(self, message: str):
        """Print message if verbose mode enabled."""
        if self.verbose:
            print(f"  {message}")

    def add_violation(
        self, check: str, file: str, line: int, message: str, severity: str = "error"
    ):
        """Record a violation."""
        self.violations.append(Violation(check, file, line, message, severity))

    def should_exclude_path(self, path: Path) -> bool:
        """
        Check if a path should be excluded based on directory parts.

        Uses Path.parts to check directory components, not substring matching.
        This prevents false exclusions like files containing 'migration' in their name.
        """
        # Check if any part of the path is in excluded dirs
        for part in path.parts:
            if part in EXCLUDED_DIRS:
                return True
            # Handle glob patterns like *.egg-info
            for pattern in EXCLUDED_DIRS:
                if "*" in pattern and part.endswith(pattern.replace("*", "")):
                    return True

        # Check if filename is explicitly excluded
        if path.name in EXCLUDED_FILES:
            return True

        return False

    def get_python_files(self) -> List[Path]:
        """Get all Python files that should be checked."""
        python_files = []
        for py_file in self.root_dir.glob("**/*.py"):
            if not self.should_exclude_path(py_file.relative_to(self.root_dir)):
                python_files.append(py_file)
        return python_files

    def run_all_checks(self) -> bool:
        """Run all security checks. Returns True if all pass."""
        print("Running security invariant checks...")
        print()

        self.check_prohibited_phi_fields()
        self.check_sentry_pii_config()
        self.check_logging_pitfalls()
        self.check_phi_in_logging()

        print()
        errors = [v for v in self.violations if v.severity == "error"]
        warnings = [v for v in self.violations if v.severity == "warning"]

        if errors:
            print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
            print()
            for v in self.violations:
                print(f"  {v}")
            return False
        elif warnings:
            print(f"PASSED with {len(warnings)} warning(s)")
            print()
            for v in warnings:
                print(f"  {v}")
            return True
        else:
            print("PASSED: All security invariants verified")
            return True

    # =========================================================================
    # Check 1: Prohibited PHI Fields
    # =========================================================================

    def check_prohibited_phi_fields(self):
        """Ensure prohibited PHI fields don't exist in model definitions."""
        print("[1/4] Checking for prohibited PHI fields in models...")

        # Patterns that indicate Django field definitions
        prohibited_patterns = [
            # Django model field definitions with field name as attribute
            (r"^\s*ocr_text\s*=\s*models\.", "ocr_text field definition"),
            (r"^\s*raw_text\s*=\s*models\.", "raw_text field definition"),
            # Also check for db_column or related field names
            (r'db_column\s*=\s*["\']ocr_text["\']', "ocr_text db_column"),
            (r'db_column\s*=\s*["\']raw_text["\']', "raw_text db_column"),
        ]

        # Only check model files
        model_files = [
            self.root_dir / "claims" / "models.py",
            self.root_dir / "agents" / "models.py",
        ]

        for model_file in model_files:
            if not model_file.exists():
                continue

            self.log(f"Scanning {model_file.relative_to(self.root_dir)}")

            with open(model_file, "r") as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                for pattern, desc in prohibited_patterns:
                    if re.search(pattern, line):
                        self.add_violation(
                            "PHI_FIELD",
                            str(model_file.relative_to(self.root_dir)),
                            line_num,
                            f"Prohibited PHI field detected: {desc}. "
                            f"Raw OCR/document text must not be stored in DB.",
                        )

    # =========================================================================
    # Check 2: Sentry PII Configuration
    # =========================================================================

    def check_sentry_pii_config(self):
        """Ensure Sentry is not configured to send default PII."""
        print("[2/4] Checking Sentry PII configuration...")

        # Check all settings files
        settings_patterns = [
            self.root_dir / "benefits_navigator" / "settings.py",
            self.root_dir / "benefits_navigator" / "settings" / "*.py",
            self.root_dir / "settings.py",
            self.root_dir / "config" / "settings" / "*.py",
        ]

        settings_files = []
        for pattern in settings_patterns:
            if "*" in str(pattern):
                settings_files.extend(pattern.parent.glob(pattern.name))
            elif pattern.exists():
                settings_files.append(pattern)

        # Robust regex: whitespace-insensitive
        pii_pattern = re.compile(r"send_default_pii\s*=\s*True", re.IGNORECASE)

        for settings_file in settings_files:
            self.log(f"Scanning {settings_file.relative_to(self.root_dir)}")

            with open(settings_file, "r") as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                # Skip comments
                if stripped.startswith("#"):
                    continue

                if pii_pattern.search(line):
                    self.add_violation(
                        "SENTRY_PII",
                        str(settings_file.relative_to(self.root_dir)),
                        line_num,
                        "Sentry configured with send_default_pii=True. "
                        "This must be False to prevent PII leakage.",
                    )

    # =========================================================================
    # Check 3: Logging Pitfalls
    # =========================================================================

    def check_logging_pitfalls(self):
        """Check for common logging patterns that might leak sensitive data."""
        print("[3/4] Checking for logging pitfalls...")

        # Patterns that might log request bodies or sensitive data
        # Match: logger.info/debug/warning/error/critical(...request.body/POST/data...)
        # Match: logging.info/debug/warning/error/critical(...request.body/POST/data...)
        # Match: print(...request.body/POST/data...)
        pitfall_patterns = [
            (
                r"(?:logger|logging)\s*\.\s*(?:debug|info|warning|error|critical|exception)\s*\([^)]*request\.body",
                "Logging request.body may contain PII",
            ),
            (
                r"(?:logger|logging)\s*\.\s*(?:debug|info|warning|error|critical|exception)\s*\([^)]*request\.POST",
                "Logging request.POST may contain PII",
            ),
            (
                r"(?:logger|logging)\s*\.\s*(?:debug|info|warning|error|critical|exception)\s*\([^)]*request\.data",
                "Logging request.data may contain PII",
            ),
            (r"print\s*\([^)]*request\.body", "Printing request.body may contain PII"),
            (r"print\s*\([^)]*request\.POST", "Printing request.POST may contain PII"),
            (r"print\s*\([^)]*request\.data", "Printing request.data may contain PII"),
        ]

        python_files = self.get_python_files()

        for py_file in python_files:
            self.log(f"Scanning {py_file.relative_to(self.root_dir)}")

            try:
                with open(py_file, "r") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                for pattern, message in pitfall_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        self.add_violation(
                            "LOGGING_PITFALL",
                            str(py_file.relative_to(self.root_dir)),
                            line_num,
                            message,
                            severity="warning",
                        )

    # =========================================================================
    # Check 4: PHI in Logging Statements
    # =========================================================================

    def check_phi_in_logging(self):
        """Check for logging statements that might include PHI fields."""
        print("[4/4] Checking for PHI in logging statements...")

        # Higher-signal patterns: attribute access or dict key access of PHI fields
        # These patterns look for actual data access, not just the string mention
        phi_access_patterns = [
            # Attribute access: .ocr_text, .raw_text, .ssn, etc.
            r"\.ocr_text\b",
            r"\.raw_text\b",
            r"\.document_text\b",
            r"\.ssn\b",
            r"\.social_security\b",
            r"\.va_file_number\b",
            r"\.file_number\b",
            # Dict key access: ["ssn"], ['ssn'], .get("ssn"), .get('ssn')
            r'\[\s*["\'](?:ssn|social_security|va_file_number|file_number|ocr_text|raw_text)["\']',
            r'\.get\s*\(\s*["\'](?:ssn|social_security|va_file_number|file_number|ocr_text|raw_text)["\']',
        ]

        # Build combined pattern for PHI access
        phi_pattern = re.compile("|".join(phi_access_patterns), re.IGNORECASE)

        # Logging call pattern
        logging_call = re.compile(
            r"(?:logger|logging)\s*\.\s*(?:debug|info|warning|error|critical|exception)\s*\(",
            re.IGNORECASE,
        )

        python_files = self.get_python_files()

        for py_file in python_files:
            try:
                with open(py_file, "r") as f:
                    content = f.read()
                    lines = content.split("\n")
            except Exception:
                continue

            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                # Check if line contains both a logging call and PHI access
                if logging_call.search(line) and phi_pattern.search(line):
                    self.add_violation(
                        "PHI_LOGGING",
                        str(py_file.relative_to(self.root_dir)),
                        line_num,
                        "Logging statement may include PHI field access. "
                        "Remove sensitive data from log output.",
                    )


def main():
    parser = argparse.ArgumentParser(description="Check security invariants")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--root", type=str, default=".", help="Project root directory")
    args = parser.parse_args()

    root_dir = Path(args.root).resolve()

    # Verify we're in the right directory
    if not (root_dir / "manage.py").exists():
        print(f"Error: {root_dir} does not appear to be a Django project")
        sys.exit(1)

    checker = SecurityChecker(root_dir, verbose=args.verbose)
    success = checker.run_all_checks()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
