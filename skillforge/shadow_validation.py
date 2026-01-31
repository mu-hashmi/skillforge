"""Shadow validation to intercept false TASK_COMPLETE signals."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from collections.abc import Callable


CODE_BLOCK_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]+)?\n(?P<code>.*?)```", re.DOTALL)
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([^\s#]+)", re.MULTILINE)
PIP_INSTALL_RE = re.compile(r"\bpip\s+install\s+([^\s]+)")
JS_IMPORT_RE = re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]")
JS_REQUIRE_RE = re.compile(r"\brequire\(['\"]([^'\"]+)['\"]\)")

PLACEHOLDER_PATTERNS = [
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bplaceholder\b",
    r"\byour_?api_?key\b",
    r"\byour_?token\b",
    r"\byour_?project\b",
    r"\bexample_?module\b",
    r"\bmy_?library\b",
]


@dataclass
class StaticAnalysisResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SandboxResult:
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class ShadowValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_summary: str | None = None
    search_query: str | None = None


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for match in CODE_BLOCK_RE.finditer(text):
        lang = (match.group("lang") or "").strip().lower()
        code = match.group("code") or ""
        blocks.append((lang, code))
    return blocks


def _check_python_syntax(code: str) -> str | None:
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return f"Python syntax error: {exc.msg} (line {exc.lineno})"
    return None


def _check_import_names(code: str) -> list[str]:
    issues: list[str] = []
    for match in IMPORT_RE.finditer(code):
        module_name = match.group(1)
        if "-" in module_name or module_name.startswith("/"):
            issues.append(f"Invalid Python import name: {module_name}")
        if "/" in module_name:
            issues.append(f"Suspicious Python import path: {module_name}")
    return issues


def _check_pip_installs(text: str) -> list[str]:
    issues: list[str] = []
    for match in PIP_INSTALL_RE.finditer(text):
        package = match.group(1)
        if any(ch in package for ch in ["<", ">", "...", "{", "}"]):
            issues.append(f"Invalid pip package specifier: {package}")
    return issues


def _check_js_imports(code: str) -> list[str]:
    issues: list[str] = []
    for match in JS_IMPORT_RE.finditer(code):
        module = match.group(1)
        if " " in module:
            issues.append(f"Invalid JS import path: {module}")
    for match in JS_REQUIRE_RE.finditer(code):
        module = match.group(1)
        if " " in module:
            issues.append(f"Invalid JS require path: {module}")
    return issues


def fast_static_analysis(output: str) -> StaticAnalysisResult:
    """Run a fast static analysis pass for common hallucination patterns."""
    result = StaticAnalysisResult()
    blocks = _extract_code_blocks(output)

    if not blocks:
        result.warnings.append("No code blocks detected for static analysis")

    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, output, re.IGNORECASE):
            result.warnings.append(f"Found placeholder text matching '{pattern}'")

    result.errors.extend(_check_pip_installs(output))

    for lang, code in blocks:
        if lang in {"python", "py"}:
            syntax_error = _check_python_syntax(code)
            if syntax_error:
                result.errors.append(syntax_error)
            result.errors.extend(_check_import_names(code))
        if lang in {"javascript", "js", "typescript", "ts"}:
            result.errors.extend(_check_js_imports(code))

    return result


def _build_search_query(task: str, error_summary: str) -> str:
    return f"{task} {error_summary}".strip()


def shadow_validate_output(
    output: str,
    task: str,
    sandbox_runner: Callable[[str, str], SandboxResult] | None = None,
) -> ShadowValidationResult:
    """Validate TASK_COMPLETE output before accepting success."""
    static_result = fast_static_analysis(output)
    errors = list(static_result.errors)
    warnings = list(static_result.warnings)

    if errors:
        summary = "; ".join(errors)
        return ShadowValidationResult(
            passed=False,
            errors=errors,
            warnings=warnings,
            error_summary=summary,
            search_query=_build_search_query(task, summary),
        )

    if sandbox_runner:
        sandbox_result = sandbox_runner(output, task)
        if not sandbox_result.success:
            summary = sandbox_result.stderr.strip() or "Sandbox validation failed"
            return ShadowValidationResult(
                passed=False,
                errors=[summary],
                warnings=warnings,
                error_summary=summary,
                search_query=_build_search_query(task, summary),
            )

    return ShadowValidationResult(passed=True, warnings=warnings)
