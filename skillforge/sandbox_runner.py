"""Lightweight sandbox runner for shadow validation."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .shadow_validation import SandboxResult


CODE_BLOCK_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]+)?\n(?P<code>.*?)```", re.DOTALL)


def _extract_code_blocks(output: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for match in CODE_BLOCK_RE.finditer(output):
        lang = (match.group("lang") or "").strip().lower()
        code = match.group("code") or ""
        blocks.append((lang, code))
    return blocks


def _run_command(command: list[str], cwd: Path) -> SandboxResult:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(success=False, exit_code=124, stderr="Sandbox validation timed out")
    return SandboxResult(
        success=result.returncode == 0,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def run_sandbox_validation(output: str, task: str) -> SandboxResult:
    """Run a minimal local validation for TASK_COMPLETE outputs."""
    blocks = _extract_code_blocks(output)
    if not blocks:
        return SandboxResult(
            success=False,
            exit_code=2,
            stderr=f"No runnable code blocks found for task: {task}",
        )

    with tempfile.TemporaryDirectory(prefix="skillforge_sandbox_") as tmpdir:
        tmp_path = Path(tmpdir)

        for idx, (lang, code) in enumerate(blocks, start=1):
            if lang in {"python", "py"}:
                script_path = tmp_path / f"script_{idx}.py"
                script_path.write_text(code)
                result = _run_command(["python", "-m", "py_compile", str(script_path)], tmp_path)
                if not result.success:
                    return SandboxResult(
                        success=False,
                        exit_code=result.exit_code,
                        stdout=result.stdout,
                        stderr=result.stderr or "Python compile check failed",
                    )
            elif lang in {"bash", "sh", "shell"}:
                script_path = tmp_path / f"script_{idx}.sh"
                script_path.write_text(code)
                result = _run_command(["bash", "-n", str(script_path)], tmp_path)
                if not result.success:
                    return SandboxResult(
                        success=False,
                        exit_code=result.exit_code,
                        stdout=result.stdout,
                        stderr=result.stderr or "Shell syntax check failed",
                    )

        return SandboxResult(success=True, exit_code=0)
