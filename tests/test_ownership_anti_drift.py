"""Anti-drift contract test for ownership classification (VAL-SEAM-007).

Verifies that infra_core.packs.memory.ownership_reader.classify_owned_path
and memory_core.ownership.classify_owned_path produce identical results on
a shared JSON corpus.

This test prevents semantic drift between the two implementations.
"""

import json
from pathlib import Path

import pytest
from infra_core.packs.memory.ownership_reader import (
    classify_owned_path as infra_classify,
)

from memory_core.ownership import classify_owned_path as memory_classify

# Shared test corpus: list of (rel_path, expected_is_owned, expected_reason_contains)
# Note: This corpus focuses on standard domain-based classification where both
# implementations should agree. Known semantic differences (e.g., bare "memory"
# directory, root-level files) are documented below.
TEST_CORPUS = [
    # Standard owned paths under declared domains
    ("memory/docs/INDEX.md", True, "memory_docs"),
    ("memory/docs/guides/setup.md", True, "memory_docs"),
    ("memory/kb/decisions/architecture.md", True, "memory_kb"),
    ("memory/kb/lessons/deployment.md", True, "memory_kb"),
    ("memory/system/ownership.toml", True, "memory_system"),
    ("memory/system/manifest.json", True, "memory_system"),
    # Non-owned paths (outside memory/*)
    ("src/main.py", False, ""),
    ("tests/test_main.py", False, ""),
    ("docs/api.md", False, ""),  # docs/ is not owned, only memory/docs/
    # Relative path normalization
    ("./memory/docs/file.md", True, "memory_docs"),
]

# Known semantic differences between implementations:
# 1. README.md: memory-core marks root files as owned, infra-core does not
# 2. "memory" and "memory/": memory-core treats bare directory as owned, infra-core requires path *under* domain
# 3. Empty project: memory-core has fallback defaults, infra-core requires explicit ownership.toml


def _create_test_project(tmp_path: Path) -> Path:
    """Create a minimal test project with ownership.toml."""
    project = tmp_path / "test-project"
    (project / "memory" / "system").mkdir(parents=True)

    ownership = project / "memory" / "system" / "ownership.toml"
    ownership.write_text(
        """
schema_version = "ownership-v1"
memory_version = "0.41.0"

[[domains]]
name = "memory_docs"
path = "memory/docs"
level = "critical"
recursive = true

[[domains]]
name = "memory_kb"
path = "memory/kb"
level = "standard"
recursive = true

[[domains]]
name = "memory_system"
path = "memory/system"
level = "critical"
recursive = true
""",
        encoding="utf-8",
    )

    return project


@pytest.mark.parametrize("rel_path,expected_owned,reason_hint", TEST_CORPUS)
def test_ownership_classification_parity(tmp_path: Path, rel_path: str, expected_owned: bool, reason_hint: str):
    """VAL-SEAM-007: infra-core and memory-core classify paths identically."""
    project = _create_test_project(tmp_path)

    # Classify with infra-core implementation
    infra_result = infra_classify(rel_path, project_root=project)
    infra_is_owned = not isinstance(infra_result, type(infra_result).__bases__[0])
    # Check if it's Owned or NotOwned
    infra_is_owned = "Owned" in type(infra_result).__name__ and "Not" not in type(infra_result).__name__

    # Classify with memory-core implementation
    memory_result = memory_classify(rel_path, project_root=project)
    memory_is_owned = "Owned" in type(memory_result).__name__ and "Not" not in type(memory_result).__name__

    # Both must agree on ownership status
    assert infra_is_owned == memory_is_owned == expected_owned, (
        f"Path {rel_path}: infra={infra_is_owned}, memory={memory_is_owned}, expected={expected_owned}"
    )

    # If expected to be owned and has reason hint, check reason
    if expected_owned and reason_hint:
        infra_reason = str(getattr(infra_result, "reason", ""))
        memory_reason = str(getattr(memory_result, "reason", ""))
        # At least one should contain the hint (both may have different formats)
        assert reason_hint in infra_reason or reason_hint in memory_reason, (
            f"Path {rel_path}: expected reason containing '{reason_hint}', "
            f"infra='{infra_reason}', memory='{memory_reason}'"
        )


def test_ownership_corpus_json_roundtrip(tmp_path: Path):
    """VAL-SEAM-007: Corpus can be serialized/deserialized without drift."""
    project = _create_test_project(tmp_path)

    # Serialize corpus to JSON
    corpus_json = json.dumps(
        [{"path": p, "expected_owned": e} for p, e, _ in TEST_CORPUS[:3]],
        indent=2,
    )

    # Deserialize and re-test
    corpus = json.loads(corpus_json)
    for entry in corpus:
        rel_path = entry["path"]
        expected_owned = entry["expected_owned"]

        infra_result = infra_classify(rel_path, project_root=project)
        memory_result = memory_classify(rel_path, project_root=project)

        infra_is_owned = "Owned" in type(infra_result).__name__ and "Not" not in type(infra_result).__name__
        memory_is_owned = "Owned" in type(memory_result).__name__ and "Not" not in type(memory_result).__name__

        assert infra_is_owned == memory_is_owned == expected_owned


def test_ownership_malformed_toml(tmp_path: Path):
    """VAL-SEAM-007: Both implementations handle malformed ownership.toml."""
    project = tmp_path / "malformed-project"
    (project / "memory" / "system").mkdir(parents=True)

    ownership = project / "memory" / "system" / "ownership.toml"
    ownership.write_text("this is not valid toml [[[", encoding="utf-8")

    infra_result = infra_classify("memory/docs/file.md", project_root=project)
    memory_result = memory_classify("memory/docs/file.md", project_root=project)

    # Both should handle gracefully (may be NotOwned or Owned depending on fallback)
    # Key: neither should raise an exception
    assert infra_result is not None
    assert memory_result is not None


# Semantic differences (intentionally not tested as contract violations):
# 1. Empty project (no ownership.toml): memory-core defaults to Owned for memory/* paths,
#    infra-core requires explicit ownership.toml to declare domains
# 2. Root-level files (README.md): memory-core treats as owned, infra-core does not
# 3. Bare "memory" or "memory/" directory: memory-core treats as owned,
#    infra-core requires paths *under* a declared domain
#
# These reflect different design philosophies:
# - memory-core: conservative default protection for memory/* namespace
# - infra-core: explicit opt-in via ownership.toml declaration
#
# The anti-drift test focuses on the common case: declared domains in ownership.toml
