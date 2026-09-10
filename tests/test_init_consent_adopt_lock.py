"""Tests for M1-1: init consent marker, adopt hardening, exclusive_lock.

Validation assertions covered:
  VAL-INIT-001: --allow-non-git writes consent marker
  VAL-INIT-002: non-git without flag rejected by denylist
  VAL-INIT-003: --allow-non-git doesn't weaken other denylist rules
  VAL-INIT-004: adopt mode doesn't inject AGENTS.md block
  VAL-INIT-006: exclusive_lock concurrent init serialization
  VAL-INIT-007: adopt preserves business files (README + INDEX sha unchanged)
  VAL-INIT-008: --allow-non-git on git repo is harmless
  VAL-CROSS-003: consent marker readable by wrapper grep
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from memory_core.tools.init_project_memory import (
    MEMORY_HOOK_BEGIN_MARKER,
    init_project_memory,
    main,
)


def _call_main(argv: list[str]) -> int:
    old_argv = sys.argv
    try:
        sys.argv = ["memory-init", *argv]
        return main()
    finally:
        sys.argv = old_argv


# Anchored regex matching the spec-mandated consent grep pattern.
# 'allow_non_git = false # true' must NOT match (the false-positive this
# anchored pattern was designed to prevent).
CONSENT_RE = re.compile(r"^\s*allow_non_git\s*=\s*true\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# VAL-INIT-001: --allow-non-git writes consent marker
# ---------------------------------------------------------------------------


class TestConsentMarker:
    """VAL-INIT-001: --allow-non-git 建树并落 consent 标记."""

    def test_allow_non_git_writes_consent_to_ownership_toml(self, tmp_path: Path) -> None:
        """--allow-non-git on non-git dir → ownership.toml has allow_non_git = true."""
        result = init_project_memory(tmp_path, allow_non_git=True)
        assert result["success"] is True, f"init failed: {result['errors']}"

        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        assert ownership_path.exists(), "ownership.toml must exist after init"
        content = ownership_path.read_text(encoding="utf-8")
        assert CONSENT_RE.search(content), (
            f"ownership.toml must contain anchored 'allow_non_git = true'. Content:\n{content}"
        )

    def test_allow_non_git_consent_in_manifest_json(self, tmp_path: Path) -> None:
        """--allow-non-git may also write consent to manifest.json."""
        result = init_project_memory(tmp_path, allow_non_git=True)
        assert result["success"] is True

        manifest_path = tmp_path / "memory" / "system" / "manifest.json"
        # manifest.json may not exist if integrity signing is skipped in tests
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pytest.fail("manifest.json is not valid JSON")
            # If consent is in manifest, it must be true
            if "allow_non_git" in manifest:
                assert manifest["allow_non_git"] is True

    def test_consent_at_least_one_location(self, tmp_path: Path) -> None:
        """Consent must be grep-able in at least one of ownership.toml or manifest.json."""
        result = init_project_memory(tmp_path, allow_non_git=True)
        assert result["success"] is True

        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        manifest_path = tmp_path / "memory" / "system" / "manifest.json"

        found = False
        if ownership_path.exists():
            content = ownership_path.read_text(encoding="utf-8")
            if CONSENT_RE.search(content):
                found = True
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("allow_non_git") is True:
                    found = True
            except json.JSONDecodeError:
                pass
        assert found, "allow_non_git=true must appear in ownership.toml or manifest.json"

    def test_negative_control_git_repo_no_flag_no_consent(self, tmp_path: Path) -> None:
        """Git repo init without --allow-non-git → no allow_non_git in ownership.toml."""
        (tmp_path / ".git").mkdir()  # fake git repo
        result = init_project_memory(tmp_path)
        assert result["success"] is True

        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        assert ownership_path.exists()
        content = ownership_path.read_text(encoding="utf-8")
        assert not CONSENT_RE.search(content), "Git repo init without flag should NOT have allow_non_git=true"

    def test_consent_grep_anchored_rejects_false_positive(self) -> None:
        """Anchored regex must not match 'allow_non_git = false # true'."""
        bad_content = "allow_non_git = false # true\n"
        assert not CONSENT_RE.search(bad_content), "Anchored regex must reject 'allow_non_git = false # true'"


# ---------------------------------------------------------------------------
# VAL-INIT-002: non-git without flag rejected by denylist
# ---------------------------------------------------------------------------


class TestNonGitDenylist:
    """VAL-INIT-002: 无标记非 git 目标仍被 denylist 拒绝."""

    @pytest.fixture(autouse=True)
    def _disable_denylist_bypass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """conftest.py sets BYPASS_DENYLIST=1 globally; we need real denylist here."""
        monkeypatch.delenv("MEMORY_CORE_BYPASS_DENYLIST", raising=False)

    def test_non_git_rejected_exit_1(self, tmp_path: Path) -> None:
        """Non-git target without --allow-non-git → exit 1 (not 2)."""
        exit_code = _call_main(["--target", str(tmp_path)])
        assert exit_code == 1, f"Expected exit 1, got {exit_code}"

    def test_non_git_rejected_message_mentions_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rejection message should mention --allow-non-git as the override."""
        # Clear TMPDIR to avoid tmpdir check firing before non_git rule
        monkeypatch.delenv("TMPDIR", raising=False)
        _call_main(["--target", str(tmp_path)])
        captured = capsys.readouterr()
        # main() prints errors to stdout via print(f"  [ERROR]  {err}")
        # The denylist message contains "Use --allow-non-git to override this check"
        combined = captured.out + captured.err
        assert "allow-non-git" in combined or "allow_non_git" in combined, (
            f"Error message should mention --allow-non-git flag. stdout: {captured.out!r}, stderr: {captured.err!r}"
        )

    def test_non_git_no_tree_created(self, tmp_path: Path) -> None:
        """Rejected non-git target → no memory/ tree created."""
        _call_main(["--target", str(tmp_path)])
        assert not (tmp_path / "memory").exists(), "No memory tree should be created for rejected target"


# ---------------------------------------------------------------------------
# VAL-INIT-003: --allow-non-git doesn't weaken other denylist rules
# ---------------------------------------------------------------------------


class TestAllowNonGitDoesNotWeakenOtherRules:
    """VAL-INIT-003: --allow-non-git 不削弱其他 denylist 规则."""

    @pytest.fixture(autouse=True)
    def _disable_denylist_bypass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """conftest.py sets BYPASS_DENYLIST=1 globally; we need real denylist here."""
        monkeypatch.delenv("MEMORY_CORE_BYPASS_DENYLIST", raising=False)

    def test_junk_pattern_still_rejected_with_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """demo-* directory with --allow-non-git → still rejected by junk_pattern."""
        # Clear TMPDIR to avoid tmpdir check firing before junk_pattern
        monkeypatch.delenv("TMPDIR", raising=False)
        junk_dir = tmp_path / "demo-something"
        junk_dir.mkdir()
        result = init_project_memory(junk_dir, allow_non_git=True)
        assert result["success"] is False, "demo-* should be rejected even with --allow-non-git"
        assert any("junk_pattern" in e for e in result.get("errors", [])), (
            f"Rejection should be for junk_pattern, got: {result['errors']}"
        )

    def test_home_root_still_rejected_with_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """$HOME with --allow-non-git → still rejected."""
        # Clear TMPDIR and use a non-tmp path for HOME
        monkeypatch.delenv("TMPDIR", raising=False)
        # Create a fake home directory outside of tmp
        fake_home = tmp_path.parent / "fake_home"
        fake_home.mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(fake_home))
        result = init_project_memory(fake_home, allow_non_git=True)
        assert result["success"] is False
        assert any("home_root" in e for e in result.get("errors", []))


# ---------------------------------------------------------------------------
# VAL-INIT-004: adopt mode doesn't inject AGENTS.md block
# ---------------------------------------------------------------------------


class TestAdoptNoAgentsInjection:
    """VAL-INIT-004: adopt 模式不追加 AGENTS.md 注入块."""

    def test_adopt_preserves_existing_agents_md_sha(self, tmp_path: Path) -> None:
        """Business AGENTS.md sha256 unchanged after adopt."""
        import hashlib

        agents_content = "# Business Agents\n\nCustom agent configuration."
        agents_path = tmp_path / "AGENTS.md"
        agents_path.write_text(agents_content)
        sha_before = hashlib.sha256(agents_path.read_bytes()).hexdigest()

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        sha_after = hashlib.sha256(agents_path.read_bytes()).hexdigest()
        assert sha_before == sha_after, "AGENTS.md sha256 must not change in adopt mode"
        assert MEMORY_HOOK_BEGIN_MARKER not in agents_path.read_text()

    def test_adopt_no_agents_md_stays_missing(self, tmp_path: Path) -> None:
        """If no AGENTS.md exists, adopt doesn't create one."""
        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True
        assert not (tmp_path / "AGENTS.md").exists(), "adopt should not create AGENTS.md when absent"

    def test_adopt_still_builds_missing_skeleton(self, tmp_path: Path) -> None:
        """adopt builds missing skeleton files (manifest.json etc.)."""
        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True
        assert (tmp_path / "memory" / "system").is_dir(), "skeleton must be built in adopt mode"


# ---------------------------------------------------------------------------
# VAL-INIT-006: exclusive_lock concurrent init serialization
# ---------------------------------------------------------------------------


class TestConcurrentInit:
    """VAL-INIT-006: exclusive_lock 并发 init 串行化."""

    def test_8_concurrent_init_all_succeed(self, tmp_path: Path) -> None:
        """8 concurrent inits on same target → all exit 0."""
        results = []

        def _run_init(idx: int) -> dict:
            r = init_project_memory(tmp_path, mode="create")
            return r

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_run_init, i) for i in range(8)]
            for f in futures:
                results.append(f.result())

        for i, r in enumerate(results):
            assert r["success"] is True, f"Init {i} failed: {r.get('errors', [])}"

    def test_concurrent_init_manifest_valid_json(self, tmp_path: Path) -> None:
        """After 8 concurrent inits, manifest.json is valid JSON."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(init_project_memory, tmp_path) for _ in range(8)]
            for f in futures:
                f.result()

        manifest_path = tmp_path / "memory" / "system" / "manifest.json"
        if manifest_path.exists():
            try:
                json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pytest.fail("manifest.json is not valid JSON after concurrent init")

    def test_concurrent_init_no_zero_byte_files(self, tmp_path: Path) -> None:
        """After 8 concurrent inits, no 0-byte files exist (except intentional .keep sentinels)."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(init_project_memory, tmp_path) for _ in range(8)]
            for f in futures:
                f.result()

        for f in (tmp_path / "memory").rglob("*"):
            if f.is_file() and f.name != ".keep":  # .keep files are intentionally empty
                assert f.stat().st_size > 0, f"Zero-byte file found: {f}"

    def test_concurrent_init_exactly_one_agents_block(self, tmp_path: Path) -> None:
        """After 8 concurrent inits, AGENTS.md has exactly one BEGIN/END pair."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(init_project_memory, tmp_path) for _ in range(8)]
            for f in futures:
                f.result()

        agents_path = tmp_path / "AGENTS.md"
        if agents_path.exists():
            content = agents_path.read_text()
            begin_count = content.count(MEMORY_HOOK_BEGIN_MARKER)
            from memory_core.tools._init_config import MEMORY_HOOK_END_MARKER

            end_count = content.count(MEMORY_HOOK_END_MARKER)
            assert begin_count == 1, f"Expected 1 BEGIN marker, got {begin_count}"
            assert end_count == 1, f"Expected 1 END marker, got {end_count}"


# ---------------------------------------------------------------------------
# VAL-INIT-007: adopt preserves business files
# ---------------------------------------------------------------------------


class TestAdoptPreservesBusinessFiles:
    """VAL-INIT-007: adopt 模式保留业务文件."""

    def test_adopt_preserves_readme_sha(self, tmp_path: Path) -> None:
        """Business README.md sha256 unchanged after adopt."""
        import hashlib

        readme_content = "# My Business Project\n\nThis is the real README."
        readme_path = tmp_path / "README.md"
        readme_path.write_text(readme_content)
        sha_before = hashlib.sha256(readme_path.read_bytes()).hexdigest()

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        sha_after = hashlib.sha256(readme_path.read_bytes()).hexdigest()
        assert sha_before == sha_after, "README.md sha256 must not change in adopt mode"

    def test_adopt_preserves_business_index_sha(self, tmp_path: Path) -> None:
        """Business INDEX.md (non-memory) sha256 unchanged after adopt."""
        import hashlib

        # Business INDEX.md = doesn't contain "project-map" (the discriminator)
        index_content = "# Business Index\n\nMy project documentation index."
        index_path = tmp_path / "INDEX.md"
        index_path.write_text(index_content)
        sha_before = hashlib.sha256(index_path.read_bytes()).hexdigest()

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        sha_after = hashlib.sha256(index_path.read_bytes()).hexdigest()
        assert sha_before == sha_after, "Business INDEX.md sha256 must not change in adopt mode"


# ---------------------------------------------------------------------------
# VAL-INIT-008: --allow-non-git on git repo is harmless
# ---------------------------------------------------------------------------


class TestAllowNonGitOnGitRepo:
    """VAL-INIT-008: --allow-non-git 用于 git 仓库无害."""

    def test_allow_non_git_on_git_repo_succeeds(self, tmp_path: Path) -> None:
        """--allow-non-git on git repo → exit 0, tree normal."""
        (tmp_path / ".git").mkdir()
        result = init_project_memory(tmp_path, allow_non_git=True)
        assert result["success"] is True
        assert (tmp_path / "memory" / "system").is_dir()
