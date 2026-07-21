"""Tests for prompt_validator — pre-execution prompt length validation."""

import pytest

from memory_core.tools.prompt_validator import (
    MAX_PROMPT_CHARS,
    PromptTooLongError,
    ValidationResult,
    check_prompt_or_raise,
    validate_prompt,
)


class TestValidatePrompt:
    def test_short_prompt_is_safe(self) -> None:
        result = validate_prompt("hello world")
        assert result.is_safe is True
        assert result.char_count == 11
        assert result.estimated_tokens == 2  # 11 // 4
        assert result.warning is None

    def test_empty_prompt_is_safe(self) -> None:
        result = validate_prompt("")
        assert result.is_safe is True
        assert result.char_count == 0

    def test_prompt_over_max_is_unsafe(self) -> None:
        prompt = "x" * (MAX_PROMPT_CHARS + 1)
        result = validate_prompt(prompt)
        assert result.is_safe is False
        assert "exceeds maximum" in result.warning

    def test_prompt_over_warning_threshold(self) -> None:
        prompt = "x" * 45_000  # between WARNING_THRESHOLD and MAX
        result = validate_prompt(prompt)
        assert result.is_safe is True
        assert result.warning is not None
        assert "near limit" in result.warning

    def test_custom_max_chars(self) -> None:
        result = validate_prompt("x" * 150, max_chars=100)
        assert result.is_safe is False
        assert result.char_count == 150

    def test_custom_warn_threshold(self) -> None:
        result = validate_prompt("x" * 60, max_chars=200, warn_at=50)
        assert result.is_safe is True
        assert result.warning is not None

    def test_token_estimation(self) -> None:
        result = validate_prompt("x" * 40)
        assert result.estimated_tokens == 10  # 40 // 4


class TestCheckPromptOrRaise:
    def test_warn_mode_allows_unsafe(self) -> None:
        prompt = "x" * (MAX_PROMPT_CHARS + 1)
        result = check_prompt_or_raise(prompt, mode="warn")
        assert result.is_safe is False

    def test_error_mode_raises(self) -> None:
        prompt = "x" * (MAX_PROMPT_CHARS + 1)
        with pytest.raises(PromptTooLongError):
            check_prompt_or_raise(prompt, mode="error")

    def test_auto_mode_returns_result(self) -> None:
        prompt = "x" * (MAX_PROMPT_CHARS + 1)
        result = check_prompt_or_raise(prompt, mode="auto")
        assert isinstance(result, ValidationResult)
        assert result.is_safe is False

    def test_safe_prompt_no_raise(self) -> None:
        result = check_prompt_or_raise("short", mode="error")
        assert result.is_safe is True


class TestValidationResult:
    def test_defaults(self) -> None:
        r = ValidationResult(is_safe=True, char_count=10, estimated_tokens=2)
        assert r.warning is None
        assert r.recommendation is None
