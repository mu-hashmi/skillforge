"""Teacher model session with retry loop."""

import sys
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import Anthropic

from .config import get_anthropic_api_key
from .corpus import load_corpus_as_context, add_pages_to_corpus
from .discovery import search_for_gap
from .exceptions import TeacherSessionError, GapDetectionError, SearchError


TEACHER_SYSTEM_PROMPT = """You are an expert technical teacher. Your task is to demonstrate how to complete a specific task using the documentation provided.

TASK: {task}

You have access to the following documentation corpus:

<documentation>
{corpus_context}
</documentation>

---

INSTRUCTIONS:
1. Carefully study the documentation above
2. Provide a complete, working solution for the task
3. Include all necessary code, commands, and explanations
4. Be thorough and precise - reference specific sections of the documentation where relevant

If you encounter a knowledge gap where the documentation is insufficient to complete the task, clearly state:
KNOWLEDGE_GAP: <specific search query to find the missing information>

If you can complete the task successfully, end your response with:
TASK_COMPLETE: <brief summary of what was accomplished>

Remember: You MUST either identify a specific knowledge gap OR complete the task successfully. Do not provide partial solutions without indicating what's missing."""


RETRY_SYSTEM_PROMPT = """You are an expert technical teacher. Your previous response was missing the required markers.

TASK: {task}

<documentation>
{corpus_context}
</documentation>

---

CRITICAL: Your response MUST end with EXACTLY ONE of these two markers:

1. If you CAN complete the task with the documentation provided:
   TASK_COMPLETE: <brief summary>

2. If you CANNOT complete the task due to missing information:
   KNOWLEDGE_GAP: <specific search query>

There is NO other valid response format. You must choose one of these two options.

Previous attempt did not include either marker. Please try again."""


@dataclass
class AttemptOutcome:
    success: bool
    output: str
    gap_query: str | None = None
    error_message: str | None = None


@dataclass
class TeacherResult:
    success: bool
    trace: list[dict] = field(default_factory=list)
    final_output: str = ""
    attempts: int = 0
    gaps_filled: list[str] = field(default_factory=list)


def _extract_gap_query(output: str) -> str | None:
    """Extract knowledge gap query from model output."""
    marker = "KNOWLEDGE_GAP:"
    if marker in output:
        idx = output.find(marker)
        rest = output[idx + len(marker):].strip()
        # Take until newline or end
        end = rest.find("\n")
        query = rest[:end].strip() if end > 0 else rest.strip()
        if query:
            return query

    # Heuristic fallbacks for common gap indicators
    gap_phrases = [
        ("I don't have information about", "."),
        ("The documentation doesn't cover", "."),
        ("I need more details on", "."),
        ("Missing information about", "."),
        ("I couldn't find documentation for", "."),
        ("The docs don't mention", "."),
    ]
    output_lower = output.lower()
    for phrase, delimiter in gap_phrases:
        if phrase.lower() in output_lower:
            idx = output_lower.find(phrase.lower())
            rest = output[idx + len(phrase):].strip()
            end = rest.find(delimiter)
            if end > 0 and end < 100:
                return rest[:end].strip()

    return None


def _check_task_complete(output: str) -> bool:
    """Check if task was completed successfully."""
    return "TASK_COMPLETE:" in output


def analyze_attempt(output: str) -> AttemptOutcome:
    """Analyze model output to determine success/failure and any knowledge gaps."""
    if _check_task_complete(output):
        return AttemptOutcome(success=True, output=output)

    gap = _extract_gap_query(output)
    if gap:
        return AttemptOutcome(success=False, output=output, gap_query=gap)

    # No explicit gap but also not complete
    return AttemptOutcome(
        success=False,
        output=output,
        error_message="Task not completed and no specific knowledge gap identified",
    )


def run_teacher_session(
    task: str,
    corpus_path: Path,
    model: str = "claude-sonnet-4-20250514",
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
    5. If failed without identifiable gap: retry ONCE with stricter prompt, then raise GapDetectionError
    """
    client = Anthropic(api_key=get_anthropic_api_key())

    trace: list[dict] = []
    gaps_filled: list[str] = []
    used_retry_prompt = False  # Track if we've used the stricter retry prompt

    for attempt in range(1, max_attempts + 1):
        # Load current corpus
        corpus_context = load_corpus_as_context(corpus_path)

        # Build system prompt - use stricter version if retrying after missing marker
        if used_retry_prompt:
            system = RETRY_SYSTEM_PROMPT.format(task=task, corpus_context=corpus_context)
            used_retry_prompt = False  # Reset for next potential use
        else:
            system = TEACHER_SYSTEM_PROMPT.format(task=task, corpus_context=corpus_context)

        # Ask model
        messages = [{"role": "user", "content": f"Please complete this task: {task}"}]

        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system,
            messages=messages,
        )

        output = response.content[0].text

        trace_entry = {
            "attempt": attempt,
            "input": messages,
            "output": output,
            "model": model,
        }

        # Analyze
        outcome = analyze_attempt(output)

        if on_attempt:
            on_attempt(attempt, outcome)

        if outcome.success:
            trace.append(trace_entry)
            return TeacherResult(
                success=True,
                trace=trace,
                final_output=output,
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
            # No gap identified - retry once with stricter prompt before failing
            trace_entry["missing_marker"] = True
            trace.append(trace_entry)

            if attempt < max_attempts and not used_retry_prompt:
                # Mark that next attempt should use the retry prompt
                used_retry_prompt = True
                print(f"Warning: Attempt {attempt} missing markers, retrying with stricter prompt", file=sys.stderr)
                continue

            # Already retried or at max attempts - raise error
            raise GapDetectionError(
                f"Task failed on attempt {attempt} without identifiable knowledge gap. "
                f"Model output did not contain TASK_COMPLETE or KNOWLEDGE_GAP markers. "
                f"Output preview: {output[:500]}..."
            )

    raise TeacherSessionError(f"Max attempts ({max_attempts}) reached without success")
