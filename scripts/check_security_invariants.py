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
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Set

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
    # Local git worktrees hold full checkouts of other branches. They are
    # untracked, so CI never sees them, but a developer running this locally
    # would get a wall of violations from branches they aren't working on.
    ".worktrees",
    ".claude",  # agent scratch, incl. .claude/worktrees/ — same reason
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
        self.check_sentry_frame_locals()
        self.check_sentry_sdk_pin()
        self.check_logging_pitfalls()
        self.check_phi_in_logging()
        self.check_streaming_prompt_logging()

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
        print("[1/5] Checking for prohibited PHI fields in models...")

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
        print("[2/5] Checking Sentry PII configuration...")

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
    # Check 2b: Sentry frame-locals capture
    # =========================================================================

    def _settings_files(self) -> List[Path]:
        """
        Every settings module in the project.

        Globs `settings*.py` rather than naming files, so `settings_production.py`
        and `settings_staging.py` are covered too. Check 2 above uses a narrower
        hand-written list; that is fine for it (the only `send_default_pii` lives
        in the base module) but would be a hole here, where the whole point is to
        catch an omission in *any* module that calls `sentry_sdk.init`.
        """
        files = []
        for path in self.root_dir.glob("**/settings*.py"):
            if not self.should_exclude_path(path.relative_to(self.root_dir)):
                files.append(path)
        return sorted(files)

    @staticmethod
    def _iter_sentry_init_calls(tree: ast.AST) -> Iterator[ast.Call]:
        """
        Yield every call node that initialises the Sentry SDK.

        Handles both import styles, resolving aliases first so a bare `init(...)`
        is only matched when this module actually imported it from sentry_sdk —
        matching every bare `init()` would fire on unrelated code.
        """
        module_aliases = {"sentry_sdk"}  # `import sentry_sdk` / `as sentry`
        init_aliases = set()  # `from sentry_sdk import init [as x]`

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "sentry_sdk":
                        module_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module == "sentry_sdk":
                for alias in node.names:
                    if alias.name == "init":
                        init_aliases.add(alias.asname or alias.name)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "init":
                base = func.value
                if isinstance(base, ast.Name) and base.id in module_aliases:
                    yield node
            elif isinstance(func, ast.Name) and func.id in init_aliases:
                yield node

    def check_sentry_frame_locals(self):
        """
        Ensure every sentry_sdk.init() sets include_local_variables=False.

        WHY THIS CHECK IS AST-BASED AND NOT A REGEX
        -------------------------------------------
        Check 2 (SENTRY_PII) greps for `send_default_pii=True` — a *wrong value*.
        This defect is a different shape: an *omission*. `include_local_variables`
        is simply absent, the SDK default (True) applies, and no regex for a wrong
        value can ever match a line that isn't there. Detecting an omission means
        parsing the call and inspecting which keywords are present.

        WHY IT MATTERS
        --------------
        `send_default_pii=False` reads as "no user data goes to Sentry" and does
        not mean that. It governs request bodies, cookies and user identifiers. It
        does not touch stack-frame locals, which are captured by default and
        attached to every event. In this codebase the Celery task frames hold OCR'd
        document text and AI analysis — a veteran's medical narrative.

        Found in three separate Beau Access Solutions apps, by two independent
        audits, 2026-07-26. Every one of them had set send_default_pii=False and
        left include_local_variables unset. This is a default that everyone reads
        as protective and isn't, which is exactly the kind of thing a build gate
        exists to hold.
        """
        for settings_file in self._settings_files():
            rel = str(settings_file.relative_to(self.root_dir))
            self.log(f"Scanning {rel} for sentry_sdk.init()")

            try:
                tree = ast.parse(settings_file.read_text(), filename=str(settings_file))
            except SyntaxError as exc:
                self.add_violation(
                    "SENTRY_FRAME_LOCALS",
                    rel,
                    exc.lineno or 0,
                    f"Could not parse settings module: {exc.msg}. "
                    "This check cannot verify Sentry configuration here.",
                )
                continue

            for call in self._iter_sentry_init_calls(tree):
                keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}

                if "include_local_variables" not in keywords:
                    self.add_violation(
                        "SENTRY_FRAME_LOCALS",
                        rel,
                        call.lineno,
                        "sentry_sdk.init() does not set include_local_variables. "
                        "The SDK default captures stack-frame locals and attaches "
                        "them to every event; send_default_pii=False does NOT "
                        "prevent this. Celery frames hold OCR text and AI analysis. "
                        "Add include_local_variables=False.",
                    )
                    continue

                value = keywords["include_local_variables"]
                if not (isinstance(value, ast.Constant) and value.value is False):
                    self.add_violation(
                        "SENTRY_FRAME_LOCALS",
                        rel,
                        call.lineno,
                        "sentry_sdk.init() sets include_local_variables to "
                        "something other than the literal False. Frame locals "
                        "carry OCR text and AI analysis; this must be False.",
                    )

    def check_sentry_sdk_pin(self):
        """
        Warn when sentry-sdk is not pinned to an exact version.

        Defence in depth, not the primary control: the explicit
        include_local_variables=False above protects regardless of version. The
        residual risk a floor pin (`>=`) leaves is a future major release
        renaming or removing the keyword — `init()` accepts arbitrary keywords,
        so it would silently become a no-op and frame capture would resume with
        no error and no failing test. Warning, not error, so this never blocks a
        deploy on its own.
        """
        requirements = self.root_dir / "requirements.txt"
        if not requirements.exists():
            return

        for line_num, line in enumerate(requirements.read_text().splitlines(), 1):
            stripped = line.strip()
            if not stripped.lower().startswith("sentry-sdk"):
                continue
            if "==" in stripped:
                continue
            self.add_violation(
                "SENTRY_SDK_PIN",
                "requirements.txt",
                line_num,
                f"sentry-sdk is not pinned exactly ({stripped!r}). init() accepts "
                "unknown keywords silently, so a major release that renames or "
                "drops include_local_variables would turn the frame-locals "
                "protection into a no-op with no error. Pin with '=='.",
                severity="warning",
            )

    # =========================================================================
    # Check 3: Logging Pitfalls
    # =========================================================================

    def check_logging_pitfalls(self):
        """Check for common logging patterns that might leak sensitive data."""
        print("[3/5] Checking for logging pitfalls...")

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
        print("[4/5] Checking for PHI in logging statements...")

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

    # =========================================================================
    # Check 5: Streaming assistant — no prompt/delta content in logs
    # =========================================================================

    def check_streaming_prompt_logging(self):
        """Flag logging of the streaming assistant's prompt/delta CONTENT.

        The streaming assistant treats the whole transcript as PHI
        (docs/ux/assistant-interactions.md §5, docs/security-invariants.md §3):
        the SSE view and gateway ``stream()`` may log turn metadata (turn/user id,
        length, public_code) but never the prompt text or a token delta.

        Metadata derived from those variables is explicitly allowed, so a bare
        reference to a sensitive variable inside a logging call is a violation
        while wrapping it in ``len(...)`` is not. Only the two streaming files
        are scanned, since that is where these variable names carry PHI.
        """
        print("[5/5] Checking for prompt/delta logging in streaming assistant...")

        # Files where these variable names hold PHI (prompt text / token deltas).
        target_files = [
            self.root_dir / "agents" / "views.py",
            self.root_dir / "agents" / "ai_gateway.py",
        ]

        # Variables that carry prompt text or streamed answer deltas.
        sensitive_vars = ["prompt", "user_prompt", "delta", "deltas", "answer"]

        logging_call = re.compile(
            r"(?:logger|logging)\s*\.\s*"
            r"(?:debug|info|warning|error|critical|exception)\s*\(",
            re.IGNORECASE,
        )
        # Metadata-only accessors that are SAFE even though they name the variable
        # (e.g. len(prompt), len(user_prompt) — a length, not the content).
        safe_wrapped = re.compile(
            r"len\s*\(\s*(?:" + "|".join(sensitive_vars) + r")\s*\)"
        )
        bare_var = re.compile(r"\b(?:" + "|".join(sensitive_vars) + r")\b")

        for target in target_files:
            if not target.exists():
                continue

            self.log(f"Scanning {target.relative_to(self.root_dir)}")

            with open(target, "r") as f:
                lines = f.readlines()

            in_call = False
            call_start_line = 0
            depth = 0
            buffer = ""

            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if not in_call:
                    if stripped.startswith("#"):
                        continue
                    match = logging_call.search(line)
                    if not match:
                        continue
                    in_call = True
                    call_start_line = line_num
                    buffer = ""
                    fragment = line[match.end() - 1 :]  # from the opening "("
                else:
                    fragment = line

                # Accumulate until the logging call's parentheses balance, so
                # multi-line logger.*(...) statements are inspected as a whole.
                buffer += fragment
                depth += fragment.count("(") - fragment.count(")")
                if depth > 0:
                    continue

                # Full logging statement captured in `buffer`; evaluate it.
                without_len = safe_wrapped.sub("", buffer)
                if bare_var.search(without_len):
                    self.add_violation(
                        "STREAMING_PHI_LOGGING",
                        str(target.relative_to(self.root_dir)),
                        call_start_line,
                        "Logging statement references streaming prompt/delta "
                        "content (PHI). Log only metadata (turn/user id, length, "
                        "public_code) — never the prompt text or a token delta.",
                    )

                in_call = False
                depth = 0
                buffer = ""


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
