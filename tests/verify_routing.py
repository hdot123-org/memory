#!/usr/bin/env python3
"""Verification script for routing rule injection feature."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())

from memory_core.tools.init_project_memory import (
    MEMORY_HOOK_BEGIN_MARKER,
    MEMORY_HOOK_END_MARKER,
    init_project_memory,
    template_agents_md_block,
)

tmp = Path(tempfile.mkdtemp())
subprocess.run(["git", "init"], cwd=tmp, capture_output=True, check=True)

print("=== VAL-INJECT-001: Memory Hook block contains routing reference after create ===")
result = init_project_memory(tmp, mode="create")
assert result["success"] is True
content = (tmp / "AGENTS.md").read_text()
assert "memory/kb/global/memory-routing.md" in content
assert "project-map/INDEX.md" in content
begin = content.index(MEMORY_HOOK_BEGIN_MARKER)
end = content.index(MEMORY_HOOK_END_MARKER) + len(MEMORY_HOOK_END_MARKER)
block = content[begin:end]
assert "memory/kb/global/memory-routing.md" in block
assert "project-map/INDEX.md" in block
print("PASSED")

print("\n=== VAL-INJECT-002: Routing reference survives idempotent update ===")
assert "路由规则" in (tmp / "AGENTS.md").read_text()
result = init_project_memory(tmp, mode="update")
assert result["success"] is True
content = (tmp / "AGENTS.md").read_text()
assert "memory/kb/global/memory-routing.md" in content
assert "路由规则" in content
print("PASSED")

print("\n=== VAL-INJECT-003: Adopt mode preserves existing unmarked AGENTS.md ===")
tmp2 = Path(tempfile.mkdtemp())
subprocess.run(["git", "init"], cwd=tmp2, capture_output=True, check=True)
agents = tmp2 / "AGENTS.md"
agents.write_text("# Custom Agents\n\nMy custom content.")
result = init_project_memory(tmp2, mode="adopt")
assert result["success"] is True
assert agents.read_text() == "# Custom Agents\n\nMy custom content."
assert MEMORY_HOOK_BEGIN_MARKER not in agents.read_text()
print("PASSED")

print("\n=== VAL-INJECT-004: Repair mode updates marked blocks only ===")
result = init_project_memory(tmp, mode="repair")
assert result["success"] is True
content = (tmp / "AGENTS.md").read_text()
assert "memory/kb/global/memory-routing.md" in content
begin = content.index(MEMORY_HOOK_BEGIN_MARKER)
end = content.index(MEMORY_HOOK_END_MARKER)
block = content[begin:end]
assert "memory/kb/global/memory-routing.md" in block
print("PASSED")

print("\n=== VAL-PATH-001: Consumer paths are project-relative ===")
block = template_agents_md_block()
assert "memory/kb/global/memory-routing.md" in block
assert "`project-map/INDEX.md`" in block
assert "memory_core/" not in block
print("PASSED")

print("\n=== VAL-PATH-002: Referenced files exist after init ===")
assert (tmp / "memory" / "kb" / "global" / "memory-routing.md").exists()
assert (tmp / "project-map" / "INDEX.md").exists()
print("PASSED")

print("\n=== VAL-TEST-002: New test for routing reference in Memory Hook block ===")
block = template_agents_md_block()
assert "memory-routing.md" in block
assert "project-map/INDEX.md" in block
print("PASSED")

shutil.rmtree(tmp)
shutil.rmtree(tmp2)
print("\n=== ALL VALIDATION ASSERTIONS PASSED ===")
