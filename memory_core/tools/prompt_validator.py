"""
Pre-execution prompt validator.
Checks prompts before Task dispatch to prevent silent truncation.
"""

from dataclasses import dataclass
from typing import Optional

# Configuration — adjust based on actual Factory limits
MAX_PROMPT_CHARS = 50_000
MAX_PROMPT_TOKENS = 12_000  # approximate: ~4 chars per token
WARNING_THRESHOLD_CHARS = 40_000


@dataclass
class ValidationResult:
    is_safe: bool
    char_count: int
    estimated_tokens: int
    warning: Optional[str] = None
    recommendation: Optional[str] = None


def validate_prompt(prompt: str, *,
                    max_chars: int = MAX_PROMPT_CHARS,
                    warn_at: int = WARNING_THRESHOLD_CHARS) -> ValidationResult:
    """
    Validate a prompt before dispatching to a subagent.

    Returns a ValidationResult indicating whether the prompt is safe to use inline.
    """
    char_count = len(prompt)
    estimated_tokens = char_count // 4  # rough estimate

    if char_count > max_chars:
        return ValidationResult(
            is_safe=False,
            char_count=char_count,
            estimated_tokens=estimated_tokens,
            warning=f"Prompt exceeds maximum: {char_count} > {max_chars} chars",
            recommendation="Use file-based task dispatch or split into smaller tasks",
        )
    elif char_count > warn_at:
        return ValidationResult(
            is_safe=True,
            char_count=char_count,
            estimated_tokens=estimated_tokens,
            warning=f"Prompt near limit: {char_count}/{max_chars} chars "
                    f"(~{estimated_tokens} tokens)",
            recommendation="Consider file-based dispatch for safety",
        )

    return ValidationResult(
        is_safe=True,
        char_count=char_count,
        estimated_tokens=estimated_tokens,
    )


def check_prompt_or_raise(prompt: str, *, mode: str = "warn") -> ValidationResult:
    """
    Validate and optionally raise an error.

    mode: "warn" = print warning but allow
          "error" = raise PromptTooLongError
          "auto" = return validation result for caller to decide
    """
    result = validate_prompt(prompt)

    if not result.is_safe:
        if mode == "error":
            raise PromptTooLongError(
                f"Prompt too long: {result.char_count} chars "
                f"(max: {MAX_PROMPT_CHARS}). {result.recommendation}"
            )
        elif mode == "warn":
            print(f"[PROMPT WARNING] {result.warning}. {result.recommendation}")

    return result


class PromptTooLongError(ValueError):
    """Raised when a prompt exceeds the safe character limit."""
    pass
