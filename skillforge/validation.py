"""Validation of teacher session output before skill generation."""

import re
from dataclasses import dataclass

from .teacher import TeacherResult
from .exceptions import ValidationError


@dataclass
class ValidationResult:
    passed: bool
    checks_run: int
    checks_passed: int
    warnings: list[str]
    errors: list[str]


def validate_teacher_output(result: TeacherResult) -> ValidationResult:
    """
    Validate teacher session output before generating skill.

    Checks:
    1. Output contains TASK_COMPLETE marker
    2. Output has substantial content (not just the marker)
    3. Output contains code blocks or commands (for technical tasks)
    4. No obvious error patterns in output
    """
    warnings = []
    errors = []
    checks_passed = 0
    checks_run = 0

    output = result.final_output

    # Check 1: TASK_COMPLETE marker present
    checks_run += 1
    if "TASK_COMPLETE:" in output:
        checks_passed += 1
    else:
        errors.append("Missing TASK_COMPLETE marker in final output")

    # Check 2: Substantial content (at least 500 chars before marker)
    checks_run += 1
    marker_idx = output.find("TASK_COMPLETE:")
    content_before = output[:marker_idx] if marker_idx > 0 else output
    if len(content_before.strip()) >= 500:
        checks_passed += 1
    elif len(content_before.strip()) >= 200:
        warnings.append(f"Output is relatively short ({len(content_before)} chars)")
        checks_passed += 1  # Pass with warning
    else:
        errors.append(f"Output too short ({len(content_before)} chars) - may be incomplete")

    # Check 3: Contains code blocks or commands (for technical tasks)
    checks_run += 1
    has_code_blocks = "```" in output
    has_inline_code = re.search(r'`[^`]+`', output) is not None
    has_commands = any(cmd in output.lower() for cmd in [
        "pip install", "npm install", "cargo", "make", "cmake",
        "python ", "node ", "go ", "rustc", "gcc", "clang",
        "import ", "from ", "require(", "use ",
    ])
    if has_code_blocks or has_inline_code or has_commands:
        checks_passed += 1
    else:
        warnings.append("No code blocks or commands detected - verify this is expected")
        checks_passed += 1  # Pass with warning for non-code tasks

    # Check 4: No obvious error patterns
    checks_run += 1
    error_patterns = [
        r"I (?:cannot|can't|am unable to)",
        r"(?:sorry|unfortunately).{0,50}(?:cannot|can't|unable)",
        r"I don't have (?:access|information|knowledge)",
        r"error:|Error:|ERROR:",
    ]
    has_error_pattern = any(re.search(pat, output, re.IGNORECASE) for pat in error_patterns)
    if not has_error_pattern:
        checks_passed += 1
    else:
        warnings.append("Output contains phrases that may indicate incomplete solution")
        # Still pass - might be documenting error handling
        checks_passed += 1

    passed = len(errors) == 0

    return ValidationResult(
        passed=passed,
        checks_run=checks_run,
        checks_passed=checks_passed,
        warnings=warnings,
        errors=errors,
    )


def validate_or_raise(result: TeacherResult) -> ValidationResult:
    """Validate and raise ValidationError if critical checks fail."""
    validation = validate_teacher_output(result)

    if not validation.passed:
        error_msg = "Validation failed:\n" + "\n".join(f"  - {e}" for e in validation.errors)
        if validation.warnings:
            error_msg += "\nWarnings:\n" + "\n".join(f"  - {w}" for w in validation.warnings)
        raise ValidationError(error_msg)

    return validation
