"""Regression tests for promote INDEX update on table-format INDEX.md.

Round-3 bug: promote_global_kb._update_index only handled marker-format INDEX
(```### [domain/](./domain/)```) and silently no-oped on table-format INDEX
(```| 标题 | 域 | 文件 |```) produced by sediment, while still printing
``✓ INDEX.md 已更新``. This caused CROSS-012 to report success while the INDEX
had zero new rows.

Fix: _update_index now detects table format and appends a ``| title | domain | file |``
row. On true no-op (neither format matches), it returns False so command_mode
prints a warning instead of ``✓ 已更新``.
"""

from pathlib import Path

import pytest


@pytest.fixture
def table_format_root(tmp_path: Path) -> Path:
    """Create a global KB root with sediment-style table-format INDEX.md."""
    root = tmp_path / "table-gk"
    (root / "pending").mkdir(parents=True)
    (root / "operations").mkdir()
    (root / "engineering").mkdir()
    (root / "collaboration").mkdir()
    (root / "INDEX.md").write_text(
        "# INDEX\n\n| 标题 | 域 | 文件 |\n|------|----|------|\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def marker_format_root(tmp_path: Path) -> Path:
    """Create a global KB root with global_kb_init-style marker-format INDEX.md."""
    root = tmp_path / "marker-gk"
    (root / "pending").mkdir(parents=True)
    (root / "operations").mkdir()
    (root / "engineering").mkdir()
    (root / "collaboration").mkdir()
    (root / "INDEX.md").write_text(
        "# Global KB\n\n"
        "### [operations/](./operations/)\n"
        "运维域\n\n"
        "### [engineering/](./engineering/)\n"
        "工程域\n\n"
        "### [collaboration/](./collaboration/)\n"
        "协作域\n\n"
        "### [pending/](./pending/)\n"
        "待确认\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def mismatch_format_root(tmp_path: Path) -> Path:
    """Create a global KB root with neither format (for no-op warning test)."""
    root = tmp_path / "mismatch-gk"
    (root / "pending").mkdir(parents=True)
    (root / "operations").mkdir()
    (root / "engineering").mkdir()
    (root / "collaboration").mkdir()
    (root / "INDEX.md").write_text(
        "# INDEX\n\nSome random content without markers or tables.\n",
        encoding="utf-8",
    )
    return root


class TestTableFormatPromote:
    """Table-format INDEX gets a new table row after promote."""

    def test_table_format_index_append_table_row(self, table_format_root: Path) -> None:
        """Promote to table-format INDEX appends ``| title | domain | file |`` row."""
        from memory_core.tools.promote_global_kb import main as promote_main

        # Create a pending candidate with frontmatter
        pending_file = table_format_root / "pending" / "restic-dryrun.md"
        pending_file.write_text(
            "---\n"
            'title: "教训：restic 备份前先 dry-run"\n'
            "domain: operations\n"
            "confidence: 0.9\n"
            "source: memory-evolve\n"
            "---\n\n"
            "restic 备份先 dry-run。\n",
            encoding="utf-8",
        )

        before = (table_format_root / "INDEX.md").read_text(encoding="utf-8")
        exit_code = promote_main(
            [
                str(pending_file),
                "--to",
                "operations",
                "--global-kb-root",
                str(table_format_root),
            ]
        )
        after = (table_format_root / "INDEX.md").read_text(encoding="utf-8")

        assert exit_code == 0
        assert after != before, "INDEX.md should have changed"
        # Table row present
        assert "| 教训：restic 备份前先 dry-run |" in after
        assert "| operations |" in after
        assert "operations/restic-dryrun.md" in after
        # File moved to formal domain
        assert not pending_file.exists()
        assert (table_format_root / "operations" / "restic-dryrun.md").exists()

    def test_pipe_character_escaped_in_title(self, table_format_root: Path) -> None:
        """Titles containing pipe characters are escaped to avoid breaking table format."""
        from memory_core.tools.promote_global_kb import main as promote_main

        # Create a pending candidate with pipe in title
        pending_file = table_format_root / "pending" / "pipe-test.md"
        pending_file.write_text(
            "---\n"
            'title: "配置项 A | 配置项 B 对比"\n'
            "domain: engineering\n"
            "confidence: 0.8\n"
            "source: memory-evolve\n"
            "---\n\n"
            "配置对比内容。\n",
            encoding="utf-8",
        )

        exit_code = promote_main(
            [
                str(pending_file),
                "--to",
                "engineering",
                "--global-kb-root",
                str(table_format_root),
            ]
        )
        after = (table_format_root / "INDEX.md").read_text(encoding="utf-8")

        assert exit_code == 0
        # Pipe should be escaped as \| in the table row
        assert "| 配置项 A \\| 配置项 B 对比 |" in after
        assert "engineering/pipe-test.md" in after
        # File moved to formal domain
        assert not pending_file.exists()
        assert (table_format_root / "engineering" / "pipe-test.md").exists()


class TestMarkerFormatPromote:
    """Marker-format INDEX keeps its existing behavior (no regression)."""

    def test_marker_format_index_no_regression(self, marker_format_root: Path) -> None:
        """Promote to marker-format INDEX still appends bullet."""
        from memory_core.tools.promote_global_kb import main as promote_main

        pending_file = marker_format_root / "pending" / "ci-cache.md"
        pending_file.write_text(
            '---\ntitle: "CI Cache 策略"\n---\n\nUse pyc cache.\n',
            encoding="utf-8",
        )

        before = (marker_format_root / "INDEX.md").read_text(encoding="utf-8")
        exit_code = promote_main(
            [
                str(pending_file),
                "--to",
                "engineering",
                "--global-kb-root",
                str(marker_format_root),
            ]
        )
        after = (marker_format_root / "INDEX.md").read_text(encoding="utf-8")

        assert exit_code == 0
        assert after != before, "INDEX.md should have changed"
        # Bullet present
        assert "- [ci-cache.md](./engineering/ci-cache.md)" in after
        # File moved
        assert (marker_format_root / "engineering" / "ci-cache.md").exists()


class TestNoOpWarning:
    """Neither format matches: no-op with warning, not false success."""

    def test_no_op_warning_when_format_mismatch(
        self, mismatch_format_root: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """INDEX exists but has neither table nor marker format: warning on stderr."""
        from memory_core.tools.promote_global_kb import main as promote_main

        pending_file = mismatch_format_root / "pending" / "orphan.md"
        pending_file.write_text("# Orphan\n\nContent.\n", encoding="utf-8")

        before = (mismatch_format_root / "INDEX.md").read_text(encoding="utf-8")
        exit_code = promote_main(
            [
                str(pending_file),
                "--to",
                "operations",
                "--global-kb-root",
                str(mismatch_format_root),
            ]
        )
        after = (mismatch_format_root / "INDEX.md").read_text(encoding="utf-8")

        # File still moved (non-fatal)
        assert exit_code == 0
        assert (mismatch_format_root / "operations" / "orphan.md").exists()
        # INDEX unchanged
        assert after == before
        # Warning printed on stderr (not false success on stdout)
        captured = capsys.readouterr()
        assert "警告" in captured.err or "未更新" in captured.err
        assert "✓ INDEX.md 已更新" not in captured.out


class TestDualFormatCoverage:
    """Both formats can be detected and handled distinctly."""

    def test_dual_format_coverage(self, table_format_root: Path, marker_format_root: Path) -> None:
        """Table and marker formats both produce INDEX updates (different formats)."""
        from memory_core.tools.promote_global_kb import _is_table_format_index

        table_content = (table_format_root / "INDEX.md").read_text(encoding="utf-8")
        marker_content = (marker_format_root / "INDEX.md").read_text(encoding="utf-8")

        assert _is_table_format_index(table_content) is True
        assert _is_table_format_index(marker_content) is False
