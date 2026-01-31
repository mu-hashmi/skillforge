"""Teacher model session with retry loop."""

import sys
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import Anthropic

from .config import get_anthropic_api_key
from .corpus import load_corpus_as_context, add_pages_to_corpus
from .discovery import search_for_gap
from .exceptions import TeacherSessionError, GapDetectionError, SearchError, AnalysisError


TEACHER_TOOLS = [
    {
        "name": "task_complete",
        "description": "Call this when you have successfully completed the task with a full, working solution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was accomplished",
                },
                "solution": {
                    "type": "string",
                    "description": "The complete solution (code, commands, etc)",
                },
            },
            "required": ["summary", "solution"],
        },
    },
    {
        "name": "request_documentation",
        "description": "Call this when the provided documentation is insufficient to complete the task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "Specific search query to find the missing information",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this information is needed",
                },
            },
            "required": ["search_query", "reason"],
        },
    },
]


TEACHER_SYSTEM_PROMPT = """You are an expert technical teacher completing a task using the documentation provided.

TASK: {task}

<documentation>
{corpus_context}
</documentation>

Complete the task using ONLY the documentation above. When finished, use one of the available tools:
- task_complete: When you have a full working solution
- request_documentation: When the docs are insufficient (be specific about what's missing)

You MUST call exactly one tool."""


ANALYSIS_PROMPT = """Analyze this attempted task completion.

TASK: {task}
ATTEMPT OUTPUT:
{output}

Does this output contain a complete, working solution? Look for:
- Missing configuration files
- Incomplete code (TODOs, placeholders, "..." )
- References to things not defined
- Explicit uncertainty ("I think", "might need", "not sure")

If incomplete, what specific topic should be searched to fill the gap?

Respond with EXACTLY one of:
COMPLETE: <summary>
INCOMPLETE: <specific search query for missing info>
AMBIGUOUS: <what's unclear>"""


@dataclass
class AttemptOutcome:
    success: bool
    output: str
    gap_query: str | None = None
    error_message: str | None = None
    analysis_summary: str | None = None
    analysis_raw: str | None = None


@dataclass
class TeacherResult:
    success: bool
    trace: list[dict] = field(default_factory=list)
    final_output: str = ""
    attempts: int = 0
    gaps_filled: list[str] = field(default_factory=list)


def _parse_analysis_output(analysis_text: str, attempt_output: str) -> AttemptOutcome:
    """Parse analyzer output into AttemptOutcome."""
    cleaned = analysis_text.strip()
    if cleaned.startswith("COMPLETE:"):
        summary = cleaned[len("COMPLETE:"):].strip()
        return AttemptOutcome(
            success=True,
            output=attempt_output,
            analysis_summary=summary,
            analysis_raw=analysis_text,
        )
    if cleaned.startswith("INCOMPLETE:"):
        query = cleaned[len("INCOMPLETE:"):].strip()
        if not query:
            return AttemptOutcome(
                success=False,
                output=attempt_output,
                error_message="Analyzer returned INCOMPLETE without a search query.",
                analysis_raw=analysis_text,
            )
        return AttemptOutcome(
            success=False,
            output=attempt_output,
            gap_query=query,
            analysis_raw=analysis_text,
        )
    if cleaned.startswith("AMBIGUOUS:"):
        detail = cleaned[len("AMBIGUOUS:"):].strip() or "Analyzer returned AMBIGUOUS."
        return AttemptOutcome(
            success=False,
            output=attempt_output,
            error_message=detail,
            analysis_raw=analysis_text,
        )
    return AttemptOutcome(
        success=False,
        output=attempt_output,
        error_message=f"Analyzer output did not match expected format: {analysis_text!r}",
        analysis_raw=analysis_text,
    )


def _join_text_blocks(content) -> str:
    """Concatenate all text blocks from a Claude response."""
    parts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def _extract_tool_use(response) -> tuple[str, dict, str]:
    """Extract exactly one tool call and any text output."""
    tool_uses = []
    text_parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_uses.append(block)
        elif getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    text_output = "".join(text_parts).strip()
    if len(tool_uses) != 1:
        raise GapDetectionError(
            f"Expected exactly one tool call, got {len(tool_uses)}. "
            f"Text output preview: {text_output[:500]}..."
        )
    tool_use = tool_uses[0]
    tool_name = tool_use.name
    tool_input = tool_use.input or {}
    return tool_name, tool_input, text_output


def _require_tool_field(tool_name: str, tool_input: dict, field: str) -> str:
    value = tool_input.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GapDetectionError(f"Tool '{tool_name}' missing required field '{field}'.")
    return value.strip()


def _run_analysis(
    client: Anthropic,
    task: str,
    attempt_output: str,
    model: str,
) -> AttemptOutcome:
    analysis_prompt = ANALYSIS_PROMPT.format(task=task, output=attempt_output)
    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": analysis_prompt}],
    )
    analysis_text = _join_text_blocks(response.content)
    return _parse_analysis_output(analysis_text, attempt_output)


def analyze_attempt(output: str) -> AttemptOutcome:
    """Parse analyzer output into AttemptOutcome."""
    return _parse_analysis_output(output, output)


def run_teacher_session(
    task: str,
    corpus_path: Path,
    model: str = "claude-sonnet-4-20250514",
    analysis_model: str | None = None,
    max_attempts: int = 5,
    verbose: bool = False,
    on_attempt: callable = None,
) -> TeacherResult:
    """
    Run teacher session with automatic gap filling.

    For each attempt:
    1. Load current corpus
    2. Ask model to complete task
    3. Analyze response for success/failure
    4. If failed with identifiable gap: search, enrich corpus, retry
    5. If failed without identifiable gap: raise AnalysisError immediately
    """
    client = Anthropic(api_key=get_anthropic_api_key())
    analysis_model = analysis_model or model

    trace: list[dict] = []
    gaps_filled: list[str] = []

    for attempt in range(1, max_attempts + 1):
        # Load current corpus
        corpus_context = load_corpus_as_context(corpus_path)

        # Build system prompt
        system = TEACHER_SYSTEM_PROMPT.format(task=task, corpus_context=corpus_context)

        # Ask model
        messages = [{"role": "user", "content": f"Please complete this task: {task}"}]

        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system,
            messages=messages,
            tools=TEACHER_TOOLS,
            tool_choice={"type": "any"},
        )

        tool_name, tool_input, text_output = _extract_tool_use(response)

        trace_entry = {
            "attempt": attempt,
            "input": messages,
            "text_output": text_output,
            "tool_call": tool_name,
            "tool_input": tool_input,
            "model": model,
        }

        # Analyze
        if tool_name == "task_complete":
            solution = _require_tool_field(tool_name, tool_input, "solution")
            summary = _require_tool_field(tool_name, tool_input, "summary")
            trace_entry["tool_summary"] = summary

            outcome = _run_analysis(client, task, solution, analysis_model)
            trace_entry["analysis_output"] = outcome.analysis_raw
            if outcome.analysis_summary:
                trace_entry["analysis_summary"] = outcome.analysis_summary
        elif tool_name == "request_documentation":
            gap_query = _require_tool_field(tool_name, tool_input, "search_query")
            trace_entry["gap_reason"] = _require_tool_field(tool_name, tool_input, "reason")
            outcome = AttemptOutcome(success=False, output=text_output, gap_query=gap_query)
        else:
            raise GapDetectionError(f"Unknown tool call '{tool_name}'.")

        if on_attempt:
            on_attempt(attempt, outcome)

        if outcome.success:
            trace.append(trace_entry)
            return TeacherResult(
                success=True,
                trace=trace,
                final_output=outcome.output,
                attempts=attempt,
                gaps_filled=gaps_filled,
            )

        if outcome.gap_query:
            trace_entry["gap_query"] = outcome.gap_query

            # Search for missing knowledge
            try:
                gap_sources = search_for_gap(outcome.gap_query)
                if gap_sources:
                    added = add_pages_to_corpus(corpus_path, gap_sources)
                    gaps_filled.append(outcome.gap_query)
                    trace_entry["gap_sources_added"] = added
            except SearchError as e:
                # Log warning instead of silent pass
                print(f"Warning: Gap search failed for '{outcome.gap_query}': {e}", file=sys.stderr)
                trace_entry["gap_search_failed"] = True
                trace_entry["gap_search_error"] = str(e)

            trace.append(trace_entry)
        else:
            # No gap identified - raise immediately per PRD
            trace.append(trace_entry)
            raise AnalysisError(
                f"Task failed on attempt {attempt} without identifiable knowledge gap. "
                f"Analyzer output: {outcome.analysis_raw or outcome.error_message}"
            )

    raise TeacherSessionError(f"Max attempts ({max_attempts}) reached without success")
