"""Tests for scripts/check_boundary.py — BOUNDARY pollution guard.

Asserts the live repository remains clean and the script catches obvious
violations injected via tmp_path fixtures.
"""


import subprocess
import sys
from pathlib import Path

from tests.script_module_helpers import load_script_module

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_boundary.py"


def test_script_exists_and_executable():
    assert SCRIPT_PATH.is_file(), "scripts/check_boundary.py must exist"


def test_live_repo_is_clean():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"BOUNDARY guard reports findings on live repo:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_detects_business_kb_prefix(tmp_path, monkeypatch):
    mod = load_script_module(SCRIPT_PATH, "check_boundary")
    fake_repo = tmp_path
    fake_global = fake_repo / "memory_core" / "memory" / "kb" / "global"
    fake_global.mkdir(parents=True)
    (fake_global / "workbot-truth-model.md").write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(mod, "KB_GLOBAL_DIR", fake_global)
    monkeypatch.setattr(mod, "KB_PROJECTS_DIR", fake_repo / "memory_core" / "memory" / "kb" / "projects")

    findings = mod.scan_business_kb_files()
    assert any(f["kind"] == "business-kb-prefix" for f in findings)
    assert any("workbot-" in f["matched"] for f in findings)


def test_detects_business_project_file(tmp_path, monkeypatch):
    mod = load_script_module(SCRIPT_PATH, "check_boundary")
    fake_repo = tmp_path
    fake_projects = fake_repo / "memory_core" / "memory" / "kb" / "projects"
    fake_projects.mkdir(parents=True)
    (fake_projects / "workbot.md").write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(mod, "KB_GLOBAL_DIR", fake_repo / "memory_core" / "memory" / "kb" / "global")
    monkeypatch.setattr(mod, "KB_PROJECTS_DIR", fake_projects)

    findings = mod.scan_business_kb_files()
    assert any(f["kind"] == "business-project-file" for f in findings)


def test_detects_runtime_ip_leak(tmp_path, monkeypatch):
    mod = load_script_module(SCRIPT_PATH, "check_boundary")
    fake_repo = tmp_path
    fake_root = fake_repo / "memory_core"
    fake_root.mkdir(parents=True)
    (fake_root / "leak.md").write_text(
        "Deploy target: 192.168.88.99 with axonhub-ci instance",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(mod, "LEAK_SCAN_ROOTS", (fake_root,))

    findings = mod.scan_runtime_leaks()
    matched = {f["matched"] for f in findings}
    assert "private-ip-192.168.88" in matched
    assert "axonhub-ci" in matched


def test_archive_is_exempt(tmp_path, monkeypatch):
    mod = load_script_module(SCRIPT_PATH, "check_boundary")
    fake_repo = tmp_path
    archive_dir = fake_repo / "memory_core" / "archive" / "legacy-workbot"
    archive_dir.mkdir(parents=True)
    (archive_dir / "doc.md").write_text("ce-01 reference allowed in archive/", encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(mod, "LEAK_SCAN_ROOTS", (fake_repo / "memory_core",))

    findings = mod.scan_runtime_leaks()
    assert findings == [], f"archive/ files must be exempt; got: {findings}"


def test_cli_returns_nonzero_on_findings(tmp_path):
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    fake_global = fake_repo / "memory" / "kb" / "global"
    fake_global.mkdir(parents=True)
    (fake_global / "workbot-truth-model.md").write_text("dummy", encoding="utf-8")

    fake_script = fake_repo / "check_boundary.py"
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    src = src.replace(
        'REPO_ROOT = Path(__file__).resolve().parents[1]',
        f'REPO_ROOT = Path({str(fake_repo)!r})',
    )
    fake_script.write_text(src, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(fake_script)],
        cwd=fake_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, f"expected exit 1 on findings, got {result.returncode}"
    assert "business-kb-prefix" in result.stdout


def test_cli_json_output(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    import json as _json
    payload = _json.loads(result.stdout)
    assert "findings" in payload and "count" in payload
    assert payload["count"] == 0


def _init_git_repo(path: Path) -> None:
    """Initialize a minimal git repo at *path* with one initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, capture_output=True, check=True)
    placeholder = path / ".gitkeep"
    placeholder.write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True)


def test_untracked_file_with_private_ip_not_scanned(tmp_path, monkeypatch):
    """boundary_guard 只扫 git-tracked 文件；含私网 IP 的 untracked 文件不触发 finding。"""
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    _init_git_repo(fake_repo)

    # Create a memory/ dir with an untracked file containing a private IP
    mem_dir = fake_repo / "memory" / "docs" / "plans"
    mem_dir.mkdir(parents=True)
    untracked_file = mem_dir / "disaster-recovery.md"
    untracked_file.write_text("Server at 192.168.88.42 for recovery", encoding="utf-8")
    # Explicitly NOT git-adding it → stays untracked

    mod = load_script_module(SCRIPT_PATH, "check_boundary_untracked")
    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(mod, "LEAK_SCAN_ROOTS", (fake_repo / "memory",))

    findings = mod.scan_runtime_leaks()
    assert findings == [], f"untracked file must not trigger finding; got: {findings}"


def test_tracked_file_with_private_ip_still_scanned(tmp_path, monkeypatch):
    """同内容 tracked 文件仍触发 finding——guard 语义不变。"""
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    _init_git_repo(fake_repo)

    mem_dir = fake_repo / "memory" / "docs"
    mem_dir.mkdir(parents=True)
    tracked_file = mem_dir / "tracked-leak.md"
    tracked_file.write_text("Deploy target: 192.168.88.99", encoding="utf-8")

    # git add + commit to make it tracked
    subprocess.run(["git", "add", str(tracked_file)], cwd=fake_repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add leak"], cwd=fake_repo, capture_output=True, check=True)

    mod = load_script_module(SCRIPT_PATH, "check_boundary_tracked")
    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(mod, "LEAK_SCAN_ROOTS", (fake_repo / "memory",))

    findings = mod.scan_runtime_leaks()
    matched = {f["matched"] for f in findings}
    assert "private-ip-192.168.88" in matched, f"tracked file must still trigger; got: {findings}"
