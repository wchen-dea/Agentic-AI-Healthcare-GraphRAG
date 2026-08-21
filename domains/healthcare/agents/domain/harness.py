"""Agent harness: everything surrounding the model that isn't the model itself.

Provides:
- LLM call retry with backoff and circuit breaking
- Pre-generation input guards (injection detection, input policy)
- Post-generation output validation (grounding check, safety scan)
- Prompt registry with version tracking
- Tool execution wrapper with timeout and error normalization
- Context budget accounting
- Structured error types that distinguish failures from valid outputs
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Structured error types ────────────────────────────────────────────────────

@dataclass(frozen=True)
class HarnessResult:
    """Wraps an LLM generation result with success/failure semantics."""
    output: str
    success: bool
    error_code: str | None = None
    retries_used: int = 0
    fallback_used: bool = False
    latency_ms: float = 0.0


@dataclass(frozen=True)
class GuardResult:
    """Result of a pre/post-generation guard check."""
    passed: bool
    reasons: tuple[str, ...] = ()


# ── Retry and circuit breaker ─────────────────────────────────────────────────

@dataclass
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 10.0
    retryable_prefixes: tuple[str, ...] = ("LLM error: Ollama request timed out",)


def call_with_retry(
    fn: Callable[[], str],
    policy: RetryPolicy | None = None,
) -> HarnessResult:
    """Call an LLM generation function with bounded retries and backoff."""
    policy = policy or RetryPolicy()
    last_output = ""
    started = time.perf_counter()

    for attempt in range(policy.max_retries + 1):
        output = fn()
        elapsed_ms = (time.perf_counter() - started) * 1000

        if not _is_retryable(output, policy):
            is_error = output.startswith("LLM error:")
            return HarnessResult(
                output=output,
                success=not is_error,
                error_code="llm_error" if is_error else None,
                retries_used=attempt,
                latency_ms=elapsed_ms,
            )

        last_output = output
        if attempt < policy.max_retries:
            delay = min(
                policy.base_delay_seconds * (2 ** attempt),
                policy.max_delay_seconds,
            )
            time.sleep(delay)

    elapsed_ms = (time.perf_counter() - started) * 1000
    return HarnessResult(
        output=last_output,
        success=False,
        error_code="retries_exhausted",
        retries_used=policy.max_retries,
        latency_ms=elapsed_ms,
    )


def _is_retryable(output: str, policy: RetryPolicy) -> bool:
    return any(output.startswith(p) for p in policy.retryable_prefixes)


# ── Pre-generation input guards ───────────────────────────────────────────────

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"\bDAN\b.*\bjailbreak\b", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are\s+(not\s+)?a", re.IGNORECASE),
]

_SENSITIVE_INPUT_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN pattern
    re.compile(r"\b\d{16}\b"),  # credit card number
]


def check_input_safety(question: str) -> GuardResult:
    """Detect prompt injection attempts and sensitive data in input."""
    reasons: list[str] = []

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(question):
            reasons.append("prompt_injection_detected")
            break

    for pattern in _SENSITIVE_INPUT_PATTERNS:
        if pattern.search(question):
            reasons.append("sensitive_data_in_input")
            break

    if len(question) > 5000:
        reasons.append("input_exceeds_safe_length")

    return GuardResult(passed=len(reasons) == 0, reasons=tuple(reasons))


# ── Post-generation output guards ─────────────────────────────────────────────

_UNSAFE_OUTPUT_PATTERNS = [
    re.compile(r"\b(social\s+security\s+number|ssn)\b", re.IGNORECASE),
    re.compile(r"\bcredit\s+card\s+number\b", re.IGNORECASE),
    re.compile(r"\bpassword\b.*\b(is|:)\s*\S+", re.IGNORECASE),
]

_SAFETY_CAVEAT_PHRASES = [
    "not medical advice",
    "consult",
    "clinical judgment",
    "demo data",
    "synthetic",
    "safety caveat",
    "not a substitute",
    "healthcare professional",
]


def check_output_safety(answer: str) -> GuardResult:
    """Validate that generated output doesn't contain unsafe content."""
    reasons: list[str] = []

    for pattern in _UNSAFE_OUTPUT_PATTERNS:
        if pattern.search(answer):
            reasons.append("sensitive_data_in_output")
            break

    return GuardResult(passed=len(reasons) == 0, reasons=tuple(reasons))


def check_output_grounding(
    answer: str,
    vector_context: list[dict[str, Any]],
    graph_context: list[dict[str, Any]],
) -> GuardResult:
    """Check that the answer references evidence from retrieval context."""
    reasons: list[str] = []

    if not answer.strip():
        reasons.append("empty_answer")
        return GuardResult(passed=False, reasons=tuple(reasons))

    has_safety = any(p in answer.lower() for p in _SAFETY_CAVEAT_PHRASES)
    if not has_safety:
        reasons.append("missing_safety_caveat")

    if not vector_context and not graph_context:
        reasons.append("no_evidence_available")

    return GuardResult(passed=len(reasons) == 0, reasons=tuple(reasons))


# ── Prompt registry ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: str
    template: str
    hash: str


_PROMPT_REGISTRY: dict[str, PromptVersion] = {}


def register_prompt(name: str, version: str, template: str) -> PromptVersion:
    """Register a prompt template with version tracking."""
    content_hash = hashlib.sha256(template.encode()).hexdigest()[:12]
    entry = PromptVersion(name=name, version=version, template=template, hash=content_hash)
    _PROMPT_REGISTRY[name] = entry
    return entry


def get_prompt(name: str) -> PromptVersion | None:
    return _PROMPT_REGISTRY.get(name)


def list_prompts() -> list[PromptVersion]:
    return list(_PROMPT_REGISTRY.values())


# ── Tool execution wrapper ────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolResult:
    """Normalized result from any tool execution."""
    success: bool
    data: Any = None
    error: str | None = None
    tool_name: str = ""
    latency_ms: float = 0.0


def execute_tool(
    tool_name: str,
    fn: Callable[[], Any],
    *,
    timeout_seconds: float = 30.0,
) -> ToolResult:
    """Execute a tool function with timeout handling and error normalization."""
    started = time.perf_counter()
    try:
        result = fn()
        elapsed = (time.perf_counter() - started) * 1000
        return ToolResult(success=True, data=result, tool_name=tool_name, latency_ms=elapsed)
    except TimeoutError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return ToolResult(success=False, error=f"timeout: {exc}", tool_name=tool_name, latency_ms=elapsed)
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return ToolResult(success=False, error=str(exc)[:500], tool_name=tool_name, latency_ms=elapsed)


# ── Context budget accounting ─────────────────────────────────────────────────

@dataclass
class ContextBudget:
    """Track token/character budget across prompt components."""
    max_chars: int = 8000
    system_chars: int = 0
    question_chars: int = 0
    vector_chars: int = 0
    graph_chars: int = 0

    @property
    def used(self) -> int:
        return self.system_chars + self.question_chars + self.vector_chars + self.graph_chars

    @property
    def remaining(self) -> int:
        return max(0, self.max_chars - self.used)

    @property
    def utilization(self) -> float:
        return self.used / self.max_chars if self.max_chars > 0 else 0.0

    def can_fit(self, chars: int) -> bool:
        return self.remaining >= chars


def compute_context_budget(
    question: str,
    vector_context: list[dict[str, Any]],
    graph_context: list[dict[str, Any]],
    *,
    max_chars: int = 8000,
    system_overhead: int = 300,
) -> ContextBudget:
    """Compute how much context budget is consumed by each component."""
    vector_text = " ".join(
        str(item.get("text", "")) for item in vector_context
    )
    graph_text = " ".join(str(item) for item in graph_context)

    return ContextBudget(
        max_chars=max_chars,
        system_chars=system_overhead,
        question_chars=len(question),
        vector_chars=len(vector_text),
        graph_chars=len(graph_text),
    )
