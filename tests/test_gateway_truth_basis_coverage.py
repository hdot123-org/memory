"""Tests for truth-basis validation logic in memory_hook_gateway.py.

Covers:
- _classify_truth_ref (all return branches)
- _truth_basis_errors_for (all error checks)
- _authority_ref_allowed
- _lower_evidence_ref
"""
from __future__ import annotations

from pathlib import Path

import pytest  # noqa: E401

# ---------------------------------------------------------------------------
# Fixtures: mock module-level constants via monkeypatch
# ---------------------------------------------------------------------------


@pytest.fixture()
def gw(monkeypatch, tmp_path):
    """Import gateway module and patch path constants to tmp_path-based values."""
    import memory_core.tools.memory_hook_gateway as gw_mod

    repo_root = tmp_path / "repo"
    workspace_root = tmp_path / "workspace"
    project_map_root = workspace_root / "memory" / "project-map"

    # Create directory structure
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "agents").mkdir(parents=True)
    (repo_root / "gpt-web-to").mkdir(parents=True)
    (workspace_root / "memory" / "kb" / "global" / "projects").mkdir(parents=True)
    (workspace_root / "memory" / "kb" / "projects").mkdir(parents=True)
    (workspace_root / "memory" / "docs").mkdir(parents=True)
    (workspace_root / "projects").mkdir(parents=True)
    (workspace_root / "memory" / "artifacts").mkdir(parents=True)
    (workspace_root / "tools").mkdir(parents=True)
    (workspace_root / "memory" / "log").mkdir(parents=True)
    (workspace_root / "memory" / "system").mkdir(parents=True)

    # Patch constants
    monkeypatch.setattr(gw_mod, "REPO_ROOT", repo_root)
    monkeypatch.setattr(gw_mod, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(gw_mod, "PROJECT_MAP_ROOT", project_map_root)
    monkeypatch.setattr(gw_mod, "GLOBAL_CANONICAL", {
        workspace_root / "memory" / "global-canonical.md",
        workspace_root / "memory" / "kb" / "INDEX.md",
        repo_root / "memory" / "global-canonical.md",
        repo_root / "memory" / "kb" / "INDEX.md",
    })
    monkeypatch.setattr(gw_mod, "AUTHORITY_ALLOWED_PATHS", {
        workspace_root / "memory" / "kb" / "INDEX.md",
        workspace_root / "memory" / "AGENTS.md",
        repo_root / "memory" / "kb" / "INDEX.md",
        repo_root / "memory" / "AGENTS.md",
    })
    monkeypatch.setattr(gw_mod, "LOWER_EVIDENCE_ROOTS", [
        workspace_root / "memory" / "kb" / "lessons",
        workspace_root / "memory" / "log",
        repo_root / "memory" / "kb" / "lessons",
        repo_root / "memory" / "log",
    ])

    return gw_mod, repo_root, workspace_root, project_map_root


# ---------------------------------------------------------------------------
# _classify_truth_ref
# ---------------------------------------------------------------------------


class TestClassifyTruthRef:
    def test_legal_core(self, gw):
        gw_mod, _repo, _ws, pm_root = gw
        path = pm_root / "legal-core-map.md"
        assert gw_mod._classify_truth_ref(path) == "legal-core"

    def test_project_map_index(self, gw):
        gw_mod, _repo, _ws, pm_root = gw
        path = pm_root / "INDEX.md"
        assert gw_mod._classify_truth_ref(path) == "project-map-index"

    def test_global_canonical(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "global-canonical.md"
        assert gw_mod._classify_truth_ref(path) == "global-canonical"

    def test_compatibility_only(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "kb" / "global" / "projects" / "some-project.md"
        assert gw_mod._classify_truth_ref(path) == "compatibility-only"

    def test_project_canonical(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "kb" / "projects" / "my-project.md"
        assert gw_mod._classify_truth_ref(path) == "project-canonical"

    def test_docs(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "docs" / "design" / "foo.md"
        assert gw_mod._classify_truth_ref(path) == "docs"

    def test_project_runtime(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "projects" / "some-runtime" / "file.md"
        assert gw_mod._classify_truth_ref(path) == "project-runtime"

    def test_artifact(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "artifacts" / "some-artifact" / "data.json"
        assert gw_mod._classify_truth_ref(path) == "artifact"

    def test_tooling(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "tools" / "some-tool" / "main.py"
        assert gw_mod._classify_truth_ref(path) == "tooling"

    def test_log(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "log" / "2026-07-12.log"
        assert gw_mod._classify_truth_ref(path) == "log"

    def test_system(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "system" / "errors.log"
        assert gw_mod._classify_truth_ref(path) == "system"

    def test_app(self, gw):
        gw_mod, repo, _ws, _pm = gw
        path = repo / "app" / "main.py"
        assert gw_mod._classify_truth_ref(path) == "app"

    def test_agents(self, gw):
        gw_mod, repo, _ws, _pm = gw
        path = repo / "agents" / "worker.md"
        assert gw_mod._classify_truth_ref(path) == "agents"

    def test_gpt_web_to(self, gw):
        gw_mod, repo, _ws, _pm = gw
        path = repo / "gpt-web-to" / "config.yaml"
        assert gw_mod._classify_truth_ref(path) == "gpt-web-to"

    def test_repo_policy(self, gw):
        gw_mod, repo, _ws, _pm = gw
        path = repo / "AGENTS.md"
        assert gw_mod._classify_truth_ref(path) == "repo-policy"

    def test_workspace_entry(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "INDEX.md"
        assert gw_mod._classify_truth_ref(path) == "workspace-entry"

    def test_other(self, gw):
        gw_mod, _repo, _ws, _pm = gw
        path = Path("/tmp/completely-unrelated-path.md")
        assert gw_mod._classify_truth_ref(path) == "other"


# ---------------------------------------------------------------------------
# _authority_ref_allowed
# ---------------------------------------------------------------------------


class TestAuthorityRefAllowed:
    def test_in_authority_allowed_paths(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "kb" / "INDEX.md"
        assert gw_mod._authority_ref_allowed(path) is True

    def test_in_global_canonical(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "global-canonical.md"
        assert gw_mod._authority_ref_allowed(path) is True

    def test_not_allowed(self, gw):
        gw_mod, _repo, _ws, _pm = gw
        path = Path("/tmp/unknown-authority.md")
        assert gw_mod._authority_ref_allowed(path) is False


# ---------------------------------------------------------------------------
# _lower_evidence_ref
# ---------------------------------------------------------------------------


class TestLowerEvidenceRef:
    def test_in_lower_evidence_root(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "kb" / "lessons" / "some-lesson.md"
        assert gw_mod._lower_evidence_ref(path) is True

    def test_in_log_root(self, gw):
        gw_mod, _repo, ws, _pm = gw
        path = ws / "memory" / "log" / "2026-07-12.log"
        assert gw_mod._lower_evidence_ref(path) is True

    def test_not_lower_evidence(self, gw):
        gw_mod, _repo, _ws, _pm = gw
        path = Path("/tmp/not-lower-evidence.md")
        assert gw_mod._lower_evidence_ref(path) is False


# ---------------------------------------------------------------------------
# _truth_basis_errors_for
# ---------------------------------------------------------------------------


class TestTruthBasisErrorsFor:
    def test_missing_file(self, gw, tmp_path):
        gw_mod, _repo, _ws, _pm = gw
        path = tmp_path / "nonexistent.md"
        errors = gw_mod._truth_basis_errors_for(path, None)
        assert any("missing truth canonical" in e for e in errors)

    def test_missing_truth_basis_section(self, gw, tmp_path):
        gw_mod, _repo, _ws, _pm = gw
        path = tmp_path / "no-section.md"
        content = "# Some doc\nNo truth basis here.\n"
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("truth basis section missing" in e for e in errors)

    def test_all_refs_missing(self, gw, tmp_path):
        gw_mod, _repo, _ws, _pm = gw
        path = tmp_path / "empty-truth.md"
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n\n"
            "### Authority Refs\n\n"
            "### Evidence Refs\n\n"
            "### Conflict Status\n\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("source refs missing" in e for e in errors)
        assert any("authority refs missing" in e for e in errors)
        assert any("evidence refs missing" in e for e in errors)
        assert any("conflict status missing" in e for e in errors)

    def test_conflict_unresolved(self, gw, tmp_path):
        gw_mod, repo, ws, _pm = gw
        path = tmp_path / "unresolved.md"
        # Create a valid source ref file that exists
        source_file = repo / "memory" / "docs" / "design" / "source.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# source\n", encoding="utf-8")
        # Create a valid evidence ref file (lower evidence)
        evidence_file = ws / "memory" / "kb" / "lessons" / "evidence.md"
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text("# evidence\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/design/source.md\n\n"
            "### Authority Refs\n"
            "- memory/kb/INDEX.md\n\n"
            "### Evidence Refs\n"
            "- memory/kb/lessons/evidence.md\n\n"
            "### Conflict Status\n"
            "- pending\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("conflict status unresolved" in e for e in errors)

    def test_truth_ref_outside_repository(self, gw, tmp_path):
        gw_mod, _repo, _ws, _pm = gw
        path = tmp_path / "outside-repo.md"
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- /external/path/outside.md\n\n"
            "### Authority Refs\n\n"
            "### Evidence Refs\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("truth ref outside repository" in e for e in errors)

    def test_truth_ref_missing_on_disk(self, gw, tmp_path, monkeypatch):
        gw_mod, repo, _ws, _pm = gw
        path = tmp_path / "missing-disk.md"
        # Reference a path inside repo that doesn't exist on disk
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/nonexistent.md\n\n"
            "### Authority Refs\n\n"
            "### Evidence Refs\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("truth ref missing on disk" in e for e in errors)

    def test_source_and_evidence_identical(self, gw, tmp_path):
        gw_mod, repo, _ws, _pm = gw
        path = tmp_path / "identical.md"
        source_file = repo / "memory" / "docs" / "design" / "same.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# same\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/design/same.md\n\n"
            "### Authority Refs\n\n"
            "### Evidence Refs\n"
            "- memory/docs/design/same.md\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("source refs and evidence refs must not be identical" in e for e in errors)

    def test_source_overlap_authority(self, gw, tmp_path):
        gw_mod, repo, ws, _pm = gw
        path = tmp_path / "overlap.md"
        source_file = repo / "memory" / "docs" / "design" / "overlap.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# overlap\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/design/overlap.md\n\n"
            "### Authority Refs\n"
            "- memory/docs/design/overlap.md\n\n"
            "### Evidence Refs\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("source refs overlap authority refs" in e for e in errors)

    def test_authority_overlap_evidence(self, gw, tmp_path):
        gw_mod, repo, ws, _pm = gw
        path = tmp_path / "auth-evid.md"
        auth_file = ws / "memory" / "kb" / "lessons" / "shared.md"
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text("# shared\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/design/source.md\n\n"
            "### Authority Refs\n"
            "- memory/kb/lessons/shared.md\n\n"
            "### Evidence Refs\n"
            "- memory/kb/lessons/shared.md\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("authority refs overlap evidence refs" in e for e in errors)

    def test_authority_not_formal_canonical(self, gw, tmp_path):
        gw_mod, repo, ws, _pm = gw
        path = tmp_path / "bad-authority.md"
        # Create a valid source ref
        source_file = repo / "memory" / "docs" / "design" / "valid-source.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# valid\n", encoding="utf-8")
        # Create an authority ref that is NOT in AUTHORITY_ALLOWED_PATHS or GLOBAL_CANONICAL
        bad_auth = repo / "memory" / "docs" / "informal.md"
        bad_auth.write_text("# informal\n", encoding="utf-8")
        # Create a valid evidence ref (lower evidence)
        evidence_file = ws / "memory" / "kb" / "lessons" / "valid-evidence.md"
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text("# evidence\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/design/valid-source.md\n\n"
            "### Authority Refs\n"
            "- memory/docs/informal.md\n\n"
            "### Evidence Refs\n"
            "- memory/kb/lessons/valid-evidence.md\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("authority ref is not formal canonical" in e for e in errors)

    def test_source_refs_do_not_include_noncanonical(self, gw, tmp_path):
        gw_mod, repo, ws, _pm = gw
        path = tmp_path / "canon-only.md"
        # All source refs are global-canonical (no non-canonical origin)
        # Source ref resolves to REPO_ROOT / "memory/global-canonical.md"
        source_file = repo / "memory" / "global-canonical.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# global\n", encoding="utf-8")
        # Authority ref resolves to REPO_ROOT / "memory/kb/INDEX.md"
        auth_file = repo / "memory" / "kb" / "INDEX.md"
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text("# index\n", encoding="utf-8")
        # Evidence ref resolves to REPO_ROOT / "memory/kb/lessons/evidence.md"
        evidence_file = repo / "memory" / "kb" / "lessons" / "evidence.md"
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text("# evidence\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/global-canonical.md\n\n"
            "### Authority Refs\n"
            "- memory/kb/INDEX.md\n\n"
            "### Evidence Refs\n"
            "- memory/kb/lessons/evidence.md\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("source refs do not include a non-canonical origin" in e for e in errors)

    def test_evidence_no_lower_layer(self, gw, tmp_path):
        gw_mod, repo, ws, _pm = gw
        path = tmp_path / "no-lower.md"
        # Source ref: a non-canonical origin (docs)
        source_file = repo / "memory" / "docs" / "design" / "origin.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# origin\n", encoding="utf-8")
        # Evidence ref: NOT under LOWER_EVIDENCE_ROOTS (not lessons/log)
        evidence_file = repo / "memory" / "docs" / "design" / "evidence-not-lower.md"
        evidence_file.write_text("# evidence\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/design/origin.md\n\n"
            "### Authority Refs\n"
            "- memory/kb/INDEX.md\n\n"
            "### Evidence Refs\n"
            "- memory/docs/design/evidence-not-lower.md\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert any("evidence refs do not include lower-layer support" in e for e in errors)

    def test_conflict_resolved_no_errors(self, gw, tmp_path):
        """A well-formed truth-basis doc with resolved conflicts produces no errors."""
        gw_mod, repo, ws, _pm = gw
        path = tmp_path / "well-formed.md"
        # Create source ref file (non-canonical origin)
        source_file = repo / "memory" / "docs" / "design" / "origin.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# origin\n", encoding="utf-8")
        # Create authority ref file
        auth_file = repo / "memory" / "kb" / "INDEX.md"
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text("# index\n", encoding="utf-8")
        # Create evidence ref file
        evidence_file = repo / "memory" / "kb" / "lessons" / "evidence.md"
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text("# evidence\n", encoding="utf-8")
        content = (
            "### Truth Basis\n\n"
            "### Source Refs\n"
            "- memory/docs/design/origin.md\n\n"
            "### Authority Refs\n"
            "- memory/kb/INDEX.md\n\n"
            "### Evidence Refs\n"
            "- memory/kb/lessons/evidence.md\n\n"
            "### Conflict Status\n"
            "- resolved\n"
        )
        path.write_text(content, encoding="utf-8")
        errors = gw_mod._truth_basis_errors_for(path, content)
        assert errors == []
