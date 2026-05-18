"""Tests for hook_upgrade.py (M6 step 6.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_core.tools.hook_upgrade import (
    _inspect_settings,
    _inspect_wrapper,
    cmd_apply_upgrade,
    cmd_inspect,
    cmd_plan_upgrade,
    main,
)


@pytest.fixture
def factory_home(tmp_path: Path) -> Path:
    """Create a temporary factory home directory."""
    fh = tmp_path / ".factory"
    fh.mkdir()
    (fh / "bin").mkdir()
    return fh


@pytest.fixture
def factory_home_with_wrapper(factory_home: Path) -> Path:
    """Create factory home with a current-style wrapper."""
    wrapper = factory_home / "bin" / "memory-hook"
    wrapper.write_text(
        '#!/bin/sh\nset -eu\n# M3: Anti-pollution\nREADONLY=1\nMEMORY_HOOK_RECORD_PROJECT_LIFECYCLE\nexec "$@"\n',
        encoding="utf-8",
    )
    return factory_home


@pytest.fixture
def factory_home_with_old_wrapper(factory_home: Path) -> Path:
    """Create factory home with an old-style wrapper."""
    wrapper = factory_home / "bin" / "memory-hook"
    wrapper.write_text(
        '#!/bin/sh\nset -eu\nMEMORY_HOOK_FORCE=1\nsome_command || true\nprintf \'{}\'\n',
        encoding="utf-8",
    )
    return factory_home


@pytest.fixture
def factory_home_with_settings(factory_home: Path) -> Path:
    """Create factory home with settings.json including all hook events."""
    settings = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event session-start"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event prompt-submit"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event stop"}]}],
            "Notification": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event notification"}]}],
            "PreToolUse": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event pre-tool-use"}]}],
        }
    }
    sp = factory_home / "settings.json"
    sp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return factory_home


@pytest.fixture
def factory_home_missing_pretooluse(factory_home: Path) -> Path:
    """Create factory home with settings.json missing PreToolUse hook."""
    settings = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event session-start"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event prompt-submit"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event stop"}]}],
            "Notification": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event notification"}]}],
        }
    }
    sp = factory_home / "settings.json"
    sp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return factory_home


# ---------------------------------------------------------------------------
# Wrapper inspection tests
# ---------------------------------------------------------------------------

class TestInspectWrapper:
    def test_missing_wrapper(self, factory_home: Path) -> None:
        wrapper = factory_home / "bin" / "memory-hook"
        result = _inspect_wrapper(wrapper)
        assert not result["exists"]
        assert any(i["kind"] == "missing_wrapper" for i in result["issues"])

    def test_current_wrapper_no_issues(self, factory_home_with_wrapper: Path) -> None:
        wrapper = factory_home_with_wrapper / "bin" / "memory-hook"
        result = _inspect_wrapper(wrapper)
        assert result["exists"]
        # Should have current markers
        assert len(result["current_markers_found"]) > 0

    def test_old_wrapper_detected(self, factory_home_with_old_wrapper: Path) -> None:
        wrapper = factory_home_with_old_wrapper / "bin" / "memory-hook"
        result = _inspect_wrapper(wrapper)
        assert result["exists"]
        # Should detect old patterns
        issue_kinds = [i["kind"] for i in result["issues"]]
        assert "old_pattern" in issue_kinds

    def test_no_current_markers_flagged(self, factory_home: Path) -> None:
        wrapper = factory_home / "bin" / "memory-hook"
        wrapper.write_text("#!/bin/sh\necho hello\n", encoding="utf-8")
        result = _inspect_wrapper(wrapper)
        issue_kinds = [i["kind"] for i in result["issues"]]
        assert "old_wrapper" in issue_kinds


# ---------------------------------------------------------------------------
# Settings inspection tests
# ---------------------------------------------------------------------------

class TestInspectSettings:
    def test_missing_settings(self, factory_home: Path) -> None:
        sp = factory_home / "settings.json"
        result = _inspect_settings(sp)
        assert not result["exists"]
        assert any(i["kind"] == "missing_settings" for i in result["issues"])

    def test_all_events_registered(self, factory_home_with_settings: Path) -> None:
        sp = factory_home_with_settings / "settings.json"
        result = _inspect_settings(sp)
        assert "PreToolUse" in result["registered_events"]
        assert len(result["missing_events"]) == 0

    def test_missing_pretooluse(self, factory_home_missing_pretooluse: Path) -> None:
        sp = factory_home_missing_pretooluse / "settings.json"
        result = _inspect_settings(sp)
        assert "PreToolUse" in result["missing_events"]

    def test_empty_settings(self, factory_home: Path) -> None:
        sp = factory_home / "settings.json"
        sp.write_text("{}", encoding="utf-8")
        result = _inspect_settings(sp)
        assert len(result["missing_events"]) > 0


# ---------------------------------------------------------------------------
# inspect command tests
# ---------------------------------------------------------------------------

class TestCmdInspect:
    def test_inspect_clean(self, factory_home_with_wrapper: Path) -> None:
        result = cmd_inspect(factory_home=factory_home_with_wrapper)
        # May still have settings issues if no settings.json
        assert "wrapper" in result
        assert "settings" in result

    def test_inspect_json(
        self, factory_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_inspect(factory_home=factory_home, json_output=True)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "wrapper" in data
        assert "settings" in data

    def test_inspect_old_wrapper(self, factory_home_with_old_wrapper: Path) -> None:
        result = cmd_inspect(factory_home=factory_home_with_old_wrapper)
        assert result["needs_upgrade"] is True


# ---------------------------------------------------------------------------
# plan-upgrade command tests
# ---------------------------------------------------------------------------

class TestCmdPlanUpgrade:
    def test_plan_with_issues(self, factory_home: Path) -> None:
        result = cmd_plan_upgrade(factory_home=factory_home)
        # Missing wrapper and settings → should have actions
        assert len(result["actions"]) > 0

    def test_plan_json(
        self, factory_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_plan_upgrade(factory_home=factory_home, json_output=True)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "actions" in data

    def test_plan_missing_pretooluse(
        self, factory_home_missing_pretooluse: Path
    ) -> None:
        result = cmd_plan_upgrade(factory_home=factory_home_missing_pretooluse)
        action_kinds = [a["action"] for a in result["actions"]]
        assert "update_settings" in action_kinds


# ---------------------------------------------------------------------------
# apply-upgrade command tests
# ---------------------------------------------------------------------------

class TestCmdApplyUpgrade:
    def test_dry_run(self, factory_home: Path) -> None:
        result = cmd_apply_upgrade(
            factory_home=factory_home,
            dry_run=True,
        )
        assert result["dry_run"] is True
        assert "no changes applied" in result.get("message", "").lower() or result.get("planned_actions") is not None

    def test_apply_with_no_issues(
        self, factory_home_with_wrapper: Path, factory_home_with_settings: Path
    ) -> None:
        # Combine both into one factory home
        (factory_home_with_wrapper / "settings.json").write_text(
            (factory_home_with_settings / "settings.json").read_text(),
            encoding="utf-8",
        )
        result = cmd_apply_upgrade(
            factory_home=factory_home_with_wrapper,
            yes=True,
        )
        assert not result.get("errors")

    def test_apply_json(
        self, factory_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_apply_upgrade(
            factory_home=factory_home,
            yes=True,
            json_output=True,
            dry_run=True,
        )
        output = capsys.readouterr().out
        # There may be multiple JSON objects; find the apply-upgrade one
        # by looking for "dry_run" key
        data = None
        for obj_str in output.split("\n}\n{"):
            # Reconstruct braces if split between objects
            candidate = obj_str.strip()
            if not candidate.startswith("{"):
                candidate = "{" + candidate
            if not candidate.endswith("}"):
                candidate = candidate + "}"
            try:
                parsed = json.loads(candidate)
                if "dry_run" in parsed:
                    data = parsed
                    break
            except json.JSONDecodeError:
                continue
        if data is None:
            # Fallback: try entire output as json
            data = json.loads(output)
        assert "dry_run" in data


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_main_inspect(self, factory_home: Path) -> None:
        rc = main(["inspect", "--factory-home", str(factory_home)])
        assert rc == 0

    def test_main_plan_upgrade(self, factory_home: Path) -> None:
        rc = main(["plan-upgrade", "--factory-home", str(factory_home)])
        assert rc == 0

    def test_main_apply_upgrade_dry_run(self, factory_home: Path) -> None:
        rc = main(
            ["apply-upgrade", "--factory-home", str(factory_home), "--dry-run"]
        )
        assert rc == 0

    def test_main_no_command(self) -> None:
        with pytest.raises(SystemExit):
            main([])
