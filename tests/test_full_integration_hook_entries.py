"""Tests for scripts/test_full_integration.py — memory_entries 判定降级.

回归背景（2026-08-28，PR #1060 CI 实证）：自建 runner（actions-runner-03）
宿主残留 factory 平台自身的 ~/.factory/settings.json（config_exists PASS）
但未安装 memory-hook wrapper，且无任何 hook 事件条目。旧逻辑将
memory_entries 缺失一律判 FAIL，导致 CI runner（本就不安装 memory 系统）
被 exit 1 阻塞。修复后：wrapper 缺失（平台未安装）时条目缺失降级为 WARN。

覆盖：
- TFI-ENT-001: wrapper 未安装 + 条目缺失 → WARN（不 FAIL）
- TFI-ENT-002: wrapper 已安装 + 条目缺失 → FAIL（保留原语义）
- TFI-ENT-003: wrapper 已安装 + 条目齐全 → PASS
- TFI-ENT-004: wrapper 未安装 + 条目齐全 → PASS（安装了条目但 wrapper 丢失不报条目问题）
- TFI-ENT-005: factory dict 格式解析（hooks 以事件名为键）
- TFI-ENT-006: 配置文件损坏（非法 JSON）→ 仍 FAIL（解析失败与安装状态无关）
- TFI-ENT-007: _check_single_platform 集成路径——wrapper 缺失 + settings.json
  残留（CI runner 场景）→ wrapper_exists WARN + config_exists PASS +
  memory_entries WARN，无 FAIL
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tests.script_module_helpers import load_script_module

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "test_full_integration.py"

FACTORY_EVENTS = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "SessionEnd",
    "Notification",
    "PreCompact",
]


def _load_tester():
    mod = load_script_module(SCRIPT_PATH, "tfi_hook_entries_under_test")
    return mod


def _factory_config() -> dict[str, Any]:
    return dict(_load_tester().IntegrationTester.PLATFORM_CONFIGS["factory"])


def _write_factory_settings(home: Path, hooks: dict[str, Any] | None) -> Path:
    factory_dir = home / ".factory"
    factory_dir.mkdir(parents=True, exist_ok=True)
    settings = factory_dir / "settings.json"
    payload: dict = {}
    if hooks is not None:
        payload["hooks"] = hooks
    settings.write_text(json.dumps(payload), encoding="utf-8")
    return settings


def _full_hooks() -> dict[str, Any]:
    return {event: [{"command": "/bin/true"}] for event in FACTORY_EVENTS}


def _run_entries_check(settings: Path, wrapper_installed: bool):
    mod = _load_tester()
    tester = mod.IntegrationTester()
    config = tester.PLATFORM_CONFIGS["factory"]
    return tester._check_hook_entries("factory", settings, config, wrapper_installed=wrapper_installed)


# ============================================================================
# TFI-ENT-001: wrapper 未安装 + 条目缺失 → WARN
# ============================================================================
def test_missing_entries_without_wrapper_downgrades_to_warn(tmp_path, monkeypatch):
    """CI runner 场景：settings.json 残留但平台未安装 → WARN 而非 FAIL。"""
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory-home"))
    settings = _write_factory_settings(tmp_path, hooks={})
    result = _run_entries_check(settings, wrapper_installed=False)
    assert result.name == "factory:memory_entries"
    assert result.status == "WARN"
    assert "platform not installed" in result.message


# ============================================================================
# TFI-ENT-002: wrapper 已安装 + 条目缺失 → FAIL（原语义保留）
# ============================================================================
def test_missing_entries_with_wrapper_still_fails(tmp_path, monkeypatch):
    """真实安装场景：wrapper 在但条目缺失 → FAIL（安装不完整）。"""
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory-home"))
    settings = _write_factory_settings(tmp_path, hooks={})
    result = _run_entries_check(settings, wrapper_installed=True)
    assert result.name == "factory:memory_entries"
    assert result.status == "FAIL"


# ============================================================================
# TFI-ENT-003: wrapper 已安装 + 条目齐全 → PASS
# ============================================================================
def test_full_entries_with_wrapper_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory-home"))
    settings = _write_factory_settings(tmp_path, hooks=_full_hooks())
    result = _run_entries_check(settings, wrapper_installed=True)
    assert result.status == "PASS"


# ============================================================================
# TFI-ENT-004: wrapper 未安装 + 条目齐全 → PASS
# ============================================================================
def test_full_entries_without_wrapper_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory-home"))
    settings = _write_factory_settings(tmp_path, hooks=_full_hooks())
    result = _run_entries_check(settings, wrapper_installed=False)
    assert result.status == "PASS"


# ============================================================================
# TFI-ENT-005: factory dict 格式解析
# ============================================================================
def test_factory_dict_format_partial_entries(tmp_path, monkeypatch):
    """factory hooks 为事件名键的 dict；部分条目缺失计入 missing。"""
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory-home"))
    partial = {event: [{"command": "/bin/true"}] for event in FACTORY_EVENTS[:3]}
    settings = _write_factory_settings(tmp_path, hooks=partial)
    result = _run_entries_check(settings, wrapper_installed=True)
    assert result.status == "FAIL"
    assert result.details
    missing_line = result.details[0]
    assert "Missing:" in missing_line
    # 9 个预期事件，前 3 个已注册 → 缺 6 个
    assert str(len(FACTORY_EVENTS) - 3) in result.message


# ============================================================================
# TFI-ENT-006: 配置损坏 → FAIL（与安装状态无关）
# ============================================================================
def test_corrupt_config_fails_regardless_of_wrapper(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory-home"))
    factory_dir = tmp_path / ".factory"
    factory_dir.mkdir(parents=True, exist_ok=True)
    settings = factory_dir / "settings.json"
    settings.write_text("{not valid json", encoding="utf-8")
    for installed in (True, False):
        result = _run_entries_check(settings, wrapper_installed=installed)
        assert result.status == "FAIL", f"wrapper_installed={installed}"


# ============================================================================
# TFI-ENT-007: _check_single_platform 集成路径（CI runner 场景）
# ============================================================================
def test_single_platform_ci_runner_scenario_no_failure(tmp_path, monkeypatch):
    """wrapper 缺失 + settings.json 残留 → 整个平台检查无 FAIL。"""
    home = tmp_path / "home"
    home.mkdir()
    _write_factory_settings(home, hooks={})
    monkeypatch.setenv("FACTORY_HOME", str(home / ".factory"))
    # wrapper 不存在（未创建 bin/memory-hook）

    mod = _load_tester()
    tester = mod.IntegrationTester()
    results = tester._check_single_platform("factory")

    statuses = {r.name: r.status for r in results}
    assert statuses.get("factory:wrapper_exists") == "WARN"
    assert statuses.get("factory:config_exists") == "PASS"
    assert statuses.get("factory:memory_entries") == "WARN"
    # 关键回归断言：CI runner 场景不得产生任何 FAIL
    assert all(r.status != "FAIL" for r in results), [r.name for r in results if r.status == "FAIL"]


# ============================================================================
# 辅助：确认 FACTORY_HOME env 解析路径（防 PLATFORM_CONFIGS 漂移）
# ============================================================================
def test_platform_config_factory_shape():
    config = _factory_config()
    assert config["config_file"] == "settings.json"
    assert set(config["events"]) == set(FACTORY_EVENTS)
    assert "FACTORY_HOME" in os.environ or config["default_home"] == "~/.factory"


# ============================================================================
# zcode 漂移守护：PLATFORM_CONFIGS['zcode'] 形状断言
# ============================================================================
ZCODE_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"]


def _zcode_config() -> dict[str, Any]:
    return dict(_load_tester().IntegrationTester.PLATFORM_CONFIGS["zcode"])


def test_platform_config_zcode_shape():
    """zcode 条目：config_file='cli/config.json'、4 事件、ZCODE_HOME/~/.zcode。"""
    config = _zcode_config()
    assert config["config_file"] == "cli/config.json"
    assert set(config["events"]) == set(ZCODE_EVENTS)
    assert config["home_env"] == "ZCODE_HOME"
    assert config["default_home"] == "~/.zcode"


def _write_zcode_config(home: Path, hooks: dict[str, Any] | None) -> Path:
    """在 home 下构造 zcode 风格的嵌套 hooks 配置文件。"""
    zcode_dir = home / ".zcode"
    cli_dir = zcode_dir / "cli"
    cli_dir.mkdir(parents=True, exist_ok=True)
    config_file = cli_dir / "config.json"
    payload: dict = {}
    if hooks is not None:
        payload["hooks"] = hooks
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    return config_file


def _zcode_full_hooks() -> dict[str, Any]:
    """zcode 标准嵌套格式：hooks.events.<Event> = [{"matcher": ".*", ...}]"""
    return {
        "enabled": True,
        "timeoutMs": 10000,
        "events": {
            event: [{"matcher": ".*", "hooks": [{"type": "command", "command": "/bin/true"}]}]
            for event in ZCODE_EVENTS
        },
    }


def _run_zcode_entries_check(config_file: Path, wrapper_installed: bool):
    mod = _load_tester()
    tester = mod.IntegrationTester()
    config = tester.PLATFORM_CONFIGS["zcode"]
    return tester._check_hook_entries("zcode", config_file, config, wrapper_installed=wrapper_installed)


# ============================================================================
# zcode 嵌套格式解析：4 事件齐全 → PASS
# ============================================================================
def test_zcode_nested_hooks_all_events_pass(tmp_path, monkeypatch):
    """zcode hooks 为嵌套结构 hooks.events.<Event> → 4 事件全 found → PASS。"""
    monkeypatch.setenv("ZCODE_HOME", str(tmp_path / "zcode-home"))
    config_file = _write_zcode_config(tmp_path, hooks=_zcode_full_hooks())
    result = _run_zcode_entries_check(config_file, wrapper_installed=True)
    assert result.name == "zcode:memory_entries"
    assert result.status == "PASS"
    assert "4" in result.message


# ============================================================================
# zcode 嵌套格式解析：缺事件 + wrapper 在位 → FAIL
# ============================================================================
def test_zcode_nested_hooks_missing_events_fails(tmp_path, monkeypatch):
    """zcode hooks 只有 2 个事件 + wrapper 在位 → FAIL（非误入 claude list 分支）。"""
    monkeypatch.setenv("ZCODE_HOME", str(tmp_path / "zcode-home"))
    partial_hooks = {
        "enabled": True,
        "events": {
            "SessionStart": [{"matcher": ".*", "hooks": [{"type": "command", "command": "/bin/true"}]}],
            "UserPromptSubmit": [{"matcher": ".*", "hooks": [{"type": "command", "command": "/bin/true"}]}],
            # PreToolUse 和 PostToolUse 缺失
        },
    }
    config_file = _write_zcode_config(tmp_path, hooks=partial_hooks)
    result = _run_zcode_entries_check(config_file, wrapper_installed=True)
    assert result.name == "zcode:memory_entries"
    assert result.status == "FAIL"
    assert "Missing" in result.message


# ============================================================================
# zcode 嵌套格式解析：wrapper 未安装 + 缺事件 → WARN（降级）
# ============================================================================
def test_zcode_nested_hooks_missing_events_no_wrapper_warn(tmp_path, monkeypatch):
    """zcode hooks 缺事件但 wrapper 未安装 → WARN（CI runner 场景）。"""
    monkeypatch.setenv("ZCODE_HOME", str(tmp_path / "zcode-home"))
    config_file = _write_zcode_config(tmp_path, hooks={"enabled": True, "events": {}})
    result = _run_zcode_entries_check(config_file, wrapper_installed=False)
    assert result.name == "zcode:memory_entries"
    assert result.status == "WARN"


# ============================================================================
# zcode _check_single_platform 集成路径：wrapper 缺失 + config 残留 → 无 FAIL
# ============================================================================
def test_zcode_single_platform_ci_runner_scenario_no_failure(tmp_path, monkeypatch):
    """zcode CI runner 场景：wrapper 缺失 + config.json 残留 → 无 FAIL。"""
    home = tmp_path / "home"
    home.mkdir()
    _write_zcode_config(home, hooks={"enabled": True, "events": {}})
    monkeypatch.setenv("ZCODE_HOME", str(home / ".zcode"))

    mod = _load_tester()
    tester = mod.IntegrationTester()
    results = tester._check_single_platform("zcode")

    statuses = {r.name: r.status for r in results}
    assert statuses.get("zcode:wrapper_exists") == "WARN"
    assert statuses.get("zcode:config_exists") == "PASS"
    assert statuses.get("zcode:memory_entries") == "WARN"
    assert all(r.status != "FAIL" for r in results), [r.name for r in results if r.status == "FAIL"]
