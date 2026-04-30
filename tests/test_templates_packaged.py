"""Verify that template resources are accessible after install (i.e. packaged in wheel)."""
from __future__ import annotations

import importlib.resources as resources


class TestTemplatesPackaged:
    """Ensure workspace.templates data files are present at runtime."""

    def test_templates_dir_exists(self):
        """workspace.templates must be importable as a subpackage."""
        import workspace.templates  # noqa: F401

    def test_code_review_template_accessible(self):
        """code-review-template.md should be readable via importlib.resources."""
        ref = resources.files("workspace.templates") / "code-review-template.md"
        content = ref.read_text(encoding="utf-8")
        assert len(content) > 0
        assert "Review" in content or "review" in content

    def test_analyze_for_review_accessible(self):
        """analyze-for-review.py should be readable via importlib.resources."""
        ref = resources.files("workspace.templates") / "analyze-for-review.py"
        content = ref.read_text(encoding="utf-8")
        assert "def main" in content or "import" in content

    def test_memory_lock_accessible(self):
        """templates/.memory/memory.lock should be readable."""
        ref = resources.files("workspace.templates") / ".memory" / "memory.lock"
        content = ref.read_text(encoding="utf-8")
        assert len(content) >= 0

    def test_adapter_toml_accessible(self):
        """templates/.memory/adapter.toml should be readable."""
        ref = resources.files("workspace.templates") / ".memory" / "adapter.toml"
        content = ref.read_text(encoding="utf-8")
        assert len(content) >= 0
