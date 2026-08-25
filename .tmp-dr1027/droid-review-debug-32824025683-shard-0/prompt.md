# Droid Auto Review — Shard Review Prompt

You are reviewing a subset of changes in this pull request. Focus on the provided diff and file list.

## Review Guidelines

1. **Correctness**: Logic errors, off-by-one, null dereferences, race conditions
2. **Security**: Injection, auth bypass, secrets exposure, unsafe deserialization
3. **Performance**: N+1 queries, unbounded loops, memory leaks, missing indexes
4. **Maintainability**: Complex logic, missing error handling, unclear naming

## Output Format

You MUST respond with a valid JSON object. No markdown, no prose, no explanation outside the JSON.

```json
{
  "shard_id": <int>,
  "findings": [
    {
      "severity": "<P0|P1|P2|P3>",
      "file": "<relative path>",
      "line": <int>,
      "message": "<concise description>"
    }
  ]
}
```

### Severity Levels

- **P0**: Critical — security vulnerability, data loss, crash in production
- **P1**: High — correctness bug, logic error, missing error handling
- **P2**: Medium — performance issue, maintainability concern
- **P3**: Low — style, minor improvement, suggestion

## Self-Validation Rules

Before responding, verify:

1. Every `file` in findings exists in the provided file list
2. Every `line` references a line that appears in the diff (added/modified context)
3. `shard_id` matches the provided shard ID
4. `findings` is an array (may be empty if no issues found)
5. All required fields present in each finding: severity, file, line, message

If any self-validation fails, you MUST correct the output before responding.

## Budget Instructions

You are operating under a fixed review budget. Adhere to the following constraints:

1. **Output budget**: Return at most 20 findings per shard. Prioritize by severity (P0 > P1 > P2 > P3).
2. **Time budget**: This shard has a 30-minute execution timeout. Focus on the most critical findings first — if you are running low, wrap up with what you have.
3. **Scope budget**: Review ONLY the diff and files provided in this shard. Do not chase references outside the provided context.
4. **Convergence**: Prefer fewer, high-quality findings over many speculative ones. Each finding must be actionable.

If the diff is large, scan for P0/P1 issues first, then P2/P3 only if budget remains.

## Important

- Review ONLY the provided diff and files. Do not infer context outside this shard.
- If the diff is empty or no files are provided, return `{"shard_id": <id>, "findings": []}`.
- Do not fabricate findings for code not shown in the diff.
- Be precise with line numbers — they must match the diff context.

## Shard 0 Diff

```diff
diff --git a/memory_core/tools/_guard_classify.py b/memory_core/tools/_guard_classify.py
index 81e6255..ea18186 100644
--- a/memory_core/tools/_guard_classify.py
+++ b/memory_core/tools/_guard_classify.py
@@ -38,6 +38,7 @@ from ._guard_patterns import (
     RE_REDIRECT,
     RE_RM,
     RE_RSYNC,
+    RE_SORT_OUTPUT,
     RE_TEE,
     RE_TOUCH,
     UNCERTAIN_PATH_PATTERNS,
@@ -226,10 +227,77 @@ def _extract_ln_path(match: re.Match[str]) -> list[str]:
     return [args[-1]] if len(args) >= 2 else []
 
 
+def _extract_sort_output_path(match: re.Match[str], include_redirects: bool = True) -> list[str]:
+    """Extract output target path from sort -o/--output command.
+
+    INFRA-551: parse sort output flags with a single semantic parser shared
+    with ``_segment_has_write_intent`` (architecture fact #10: regex fork is
+    the root cause factory for guard regressions).
+
+    Handles:
+    - Exact ``-o FILE`` and combined short flags ending with 'o' (``-ro FILE``)
+    - GNU attached-value forms ``-oFILE`` / ``-roFILE``
+    - ``--output=FILE`` long form
+    - ``--output FILE`` space-separated GNU form
+
+    Args:
+        match: RE_SORT_OUTPUT match (group 1 = argument list).
+        include_redirects: when True (default, for the extraction pipeline),
+            also union redirect targets found in the segment — ``sort -o A > B``
+            writes BOTH A and B. When False (for write-intent detection),
+            only the output-flag target counts; plain redirects are handled
+            separately by ``_check_redirect_targets``.
+    """
+    args = _split_shell_args(match.group(1))
+    targets: list[str] = []
+    for idx, arg in enumerate(args):
+        if arg == "-o":
+            if idx + 1 < len(args):
+                targets.append(args[idx + 1])
+            break
+        # GNU attached value: -oFILE (flag char 'o' immediately followed by value)
+        if arg.startswith("-o") and len(arg) > 2 and not arg.startswith("--"):
+            targets.append(arg[2:])
+            break
+        # GNU attached value after combined flags: -roFILE / -nruoFILE
+        # (leading flags pure alphabetic, SHORTEST flag run ending at the first
+        # 'o' flag char — lazy quantifier so -roout.txt splits as r|o|out.txt,
+        # not roo|ut.txt)
+        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 2:
+            m = re.match(r"^-([a-zA-Z]*?o)([a-zA-Z0-9_./-]+)$", arg)
+            if m and m.group(1) and m.group(2):
+                targets.append(m.group(2))
+                break
+        if arg.startswith("--output="):
+            targets.append(arg.split("=", 1)[1])
+            break
+        if arg == "--output":
+            if idx + 1 < len(args):
+                targets.append(args[idx + 1])
+            break
+        # Combined short flags ending with 'o' (mirror R4-3 rules: pure
+        # alphabetic tokens only, excluding value-carrying forms like
+        # -T/tmp/work, -S1Go, -k1,1)
+        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
+            flag_part = arg[1:]
+            if not any(c in flag_part for c in "/=%0123456789") and flag_part.endswith("o"):
+                # Bare combined flag (-ro): value is the next arg
+                if idx + 1 < len(args):
+                    targets.append(args[idx + 1])
+                break
+    # Union with redirect targets in the same segment (sort -o A > B writes BOTH).
+    # NB: use a strict findall (not _extract_redirect_path) — its fallback
+    # `return [match.group(1)]` would fabricate targets when no redirect exists.
+    if include_redirects:
+        redirect_pattern = re.compile(r"(?<![&>])[12]?>[>]?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
+        targets.extend(redirect_pattern.findall(match.string))
+    return targets
+
+
 def _extract_path_from_execute(command: str) -> list[str]:
     """Extract target paths from Execute command.
 
-    Dispatch table: 14 command patterns → path extraction handlers.
+    Dispatch table: 15 command patterns → path extraction handlers.
     """
     command = command.strip()
     if not command:
@@ -246,6 +314,9 @@ def _extract_path_from_execute(command: str) -> list[str]:
         (RE_TOUCH, _extract_touch_path, False),
         (RE_PYTHON_C, _extract_python_path, False),
         (RE_NODE_E, _extract_node_path, False),
+        # RE_SORT_OUTPUT before RE_REDIRECT: its handler unions sort output
+        # targets WITH redirect targets (sort -o A > B must extract both)
+        (RE_SORT_OUTPUT, _extract_sort_output_path, False),
         (RE_REDIRECT, _extract_redirect_path, True),  # uses search()
         (RE_TEE, _extract_tee_path, False),
         (RE_HEREDOC, _extract_heredoc_path, False),
@@ -723,6 +794,34 @@ def _check_redirect_targets(segment: str) -> bool:
     return False
 
 
+# Known safe read-only commands (architecture §2.2 safe set + common tools)
+# INFRA-551: module-level so the coarse gate can recognize readonly
+# vocabulary segments (owned strings there are usually INPUT references)
+READONLY_COMMANDS = {
+    "cat",
+    "ls",
+    "grep",
+    "rg",  # B3: rg is read-only (architecture §2.2 lists grep/rg)
+    "head",
+    "tail",
+    "echo",
+    "printf",
+    "stat",
+    "wc",
+    "diff",
+    "awk",
+    "sort",  # B3: sort is read-only
+    "pytest",
+    "ruff",
+    "mypy",
+}
+
+# INFRA-551: readonly vocabulary for the coarse gate skip decision —
+# readonly commands plus commands with readonly subcommand handling
+# (ruff check / sed -n / git log etc. handled in _segment_has_write_intent)
+_READONLY_VOCAB = READONLY_COMMANDS | {"sed", "git"}
+
+
 def _segment_has_write_intent(segment: str) -> bool:  # noqa: C901
     """Determine if a command segment has write intent.
 
@@ -744,25 +843,7 @@ def _segment_has_write_intent(segment: str) -> bool:  # noqa: C901
     # Get first command word
     first_word = segment.split()[0] if segment.split() else ""
 
-    # Known safe read-only commands (architecture §2.2 safe set + common tools)
-    readonly_commands = {
-        "cat",
-        "ls",
-        "grep",
-        "rg",  # B3: rg is read-only (architecture §2.2 lists grep/rg)
-        "head",
-        "tail",
-        "echo",
-        "printf",
-        "stat",
-        "wc",
-        "diff",
-        "awk",
-        "sort",  # B3: sort is read-only
-        "pytest",
-        "ruff",
-        "mypy",
-    }
+    readonly_commands = READONLY_COMMANDS
     # R3-6: ruff format / ruff check --fix are write operations
     if first_word == "ruff":
         words = segment.split()
@@ -780,29 +861,17 @@ def _segment_has_write_intent(segment: str) -> bool:  # noqa: C901
         return _check_redirect_targets(segment)
 
     if first_word in readonly_commands:
-        # R3-4 + R4-2 + R4-3: sort with -o/--output is write operation
+        # R3-4 + R4-2 + R4-3 + INFRA-551: sort with -o/--output is write operation
         # Handles: -o, combined flags like -ro/-nro/-uo, --output=, --output (space form)
         # R4-3 fix: exclude value-carrying forms like -T/tmp/work, -S1Go, -k1,1
+        # INFRA-551: extraction shares one semantic parser with the legacy
+        # path extractor (single source of truth for sort output flags)
         if first_word == "sort":
-            words = segment.split()
-            for idx, w in enumerate(words[1:], 1):
-                # Exact -o flag
-                if w == "-o":
-                    return True
-                # Combined short flags ending with 'o' (e.g. -ro, -nro, -uo)
-                # R4-3: must be pure alphabetic flags, no value indicators
-                if w.startswith("-") and not w.startswith("--") and len(w) > 1:
-                    flag_part = w[1:]
-                    # Skip value-carrying forms: -T/tmp/work, -S1Go, -k1,1, etc.
-                    # Pure alphabetic flags ending with 'o'
-                    if not any(c in flag_part for c in "/=%0123456789") and flag_part.endswith("o"):
-                        return True
-                # --output=VALUE form
-                if w.startswith("--output="):
-                    return True
-                # --output VALUE (space-separated GNU form)
-                if w == "--output" and idx + 1 < len(words):
-                    return True
+            sort_match = RE_SORT_OUTPUT.match(segment)
+            if sort_match is not None and _extract_sort_output_path(sort_match, include_redirects=False):
+                # Write form: -o FILE / -ro FILE / -oFILE / --output[= ]FILE
+                return True
+            # Fall through: readonly sort still checks redirect targets below
 
         # Readonly commands only have write intent if redirecting to owned paths
         # R4-0: Use unified _check_redirect_targets helper
@@ -979,12 +1048,29 @@ def _classify_execute(payload: dict[str, Any], project_root: Path, ownership: An
     # Fix-2: Split into segments
     segments = _split_command_segments(command)
 
-    # Check segments and track write intent
-    segment_result, any_write_intent = _check_command_segments(segments)
+    # INFRA-551: precise extraction is authoritative over the coarse string
+    # heuristic. When a segment has extractable write targets (redirect
+    # targets, sort output flag targets), classify those targets precisely
+    # BEFORE the coarse gate runs, so that:
+    # - audit/ / review/ owned-domain escapes are caught (heuristic blind)
+    # - owned INPUT files with safe OUTPUT targets are not false-blocked
+    #   (e.g. sort -o /tmp/out memory/kb/data.csv)
+    for segment in segments:
+        if _extract_path_from_execute(segment):
+            legacy_result = _legacy_path_extraction(segment, ownership, project_root, full_command_context=command)
+            if legacy_result.matched:
+                return legacy_result
+
+    # Check segments and track write intent.
+    # INFRA-551: the coarse gate is a fallback — when a segment's write
+    # targets were precisely extracted and classified as safe (allow), the
+    # coarse string heuristic must not re-block it (fixes owned-INPUT +
+    # safe-OUTPUT false positives, e.g. sort -o /tmp/out memory/kb/data.csv).
+    segment_result = _check_command_segments(segments, ownership, project_root)
     if segment_result is not None:
         return segment_result
 
-    # B1 fix: Run legacy extraction per segment with write intent
+    # B1 fix: run legacy extraction per segment with write intent
     # This catches file-type blacklists, uncertain paths, and owned paths
     # that segment-level write intent gate doesn't detect
     for segment in segments:
@@ -1003,14 +1089,24 @@ def _classify_execute(payload: dict[str, Any], project_root: Path, ownership: An
     )
 
 
-def _check_command_segments(segments: list[str]) -> tuple[RuleResult | None, bool]:
+def _check_command_segments(
+    segments: list[str],
+    ownership: Any,
+    project_root: Path,
+) -> RuleResult | None:  # noqa: ARG001
     """Check command segments for owned resource references.
 
-    Returns:
-        tuple: (RuleResult if a segment triggers block decision, else None),
-               (bool indicating if any segment had write intent)
+    Returns RuleResult if a segment triggers block decision, else None.
+
+    INFRA-551: when a segment's write targets are precisely extractable and
+    already classified (by the authoritative pre-pass in _classify_execute),
+    the coarse string gate skips that segment — precision wins over the
+    heuristic to avoid false positives.
+
+    ownership/project_root are accepted for signature symmetry with the
+    authoritative classification pass; the coarse gate itself needs no
+    ownership context.
     """
-    any_write_intent = False
     for i, segment in enumerate(segments):
         parts = segment.split()
         if not parts:
@@ -1022,30 +1118,35 @@ def _check_command_segments(segments: list[str]) -> tuple[RuleResult | None, boo
         if first_word == "cd" and len(parts) >= 2:
             cd_result = _handle_cd_segment(segment, parts, i, segments)
             if cd_result is not None:
-                return cd_result, any_write_intent
+                return cd_result
+            continue
+
+        # INFRA-551: segments whose first word is in the readonly vocabulary
+        # (cat/grep/sort/ruff/sed/git/...) were already classified precisely
+        # by the authoritative pre-pass — owned strings in such segments are
+        # usually INPUTS (e.g. sort -o /tmp/out memory/kb/data.csv), so the
+        # coarse string gate must skip them to avoid false positives.
+        # Write commands (mv/rm/install/rsync/...) keep the coarse gate
+        # (defense-in-depth for extractor gaps like install -t).
+        if first_word in _READONLY_VOCAB and _extract_path_from_execute(segment):
             continue
 
         # Check for write intent
         has_write_intent = _segment_has_write_intent(segment)
-        if has_write_intent:
-            any_write_intent = True
 
         # Check if segment has owned references
         has_owned_refs = _check_owned_in_segment(segment)
 
         # If this segment has write intent and owned refs, block
         if has_write_intent and has_owned_refs:
-            return (
-                RuleResult(
-                    matched=True,
-                    severity="error",
-                    message=f"Command segment has write intent targeting owned resources: {segment[:50]}...",
-                    detail={"decision": "block"},
-                ),
-                any_write_intent,
+            return RuleResult(
+                matched=True,
+                severity="error",
+                message=f"Command segment has write intent targeting owned resources: {segment[:50]}...",
+                detail={"decision": "block"},
             )
 
-    return None, any_write_intent
+    return None
 
 
 def _handle_cd_segment(segment: str, parts: list[str], i: int, segments: list[str]) -> RuleResult | None:
diff --git a/memory_core/tools/_guard_patterns.py b/memory_core/tools/_guard_patterns.py
index 0763c48..fab467d 100644
--- a/memory_core/tools/_guard_patterns.py
+++ b/memory_core/tools/_guard_patterns.py
@@ -59,6 +59,11 @@ RE_NODE_E = re.compile(
     re.IGNORECASE | re.DOTALL,
 )
 
+# sort command args (INFRA-551: output flag target extraction).
+# Captures the argument list only; -o/--output semantics live in
+# _extract_sort_output_path (single semantic parser, no regex fork).
+RE_SORT_OUTPUT = re.compile(r"^sort\s+(.+)$", re.IGNORECASE)
+
 # shell redirect (> >>) — used with findall() for multi-redirect coverage
 RE_REDIRECT = re.compile(r"[12]?>[>]?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
 
diff --git a/tests/test_guard_infra551.py b/tests/test_guard_infra551.py
new file mode 100644
index 0000000..f127e1c
--- /dev/null
+++ b/tests/test_guard_infra551.py
@@ -0,0 +1,256 @@
+"""INFRA-551 guard tests: sort output-flag target classification + redirect precision.
+
+Findings fixed in this round (on top of PR #1026 / R4-1..R4-3):
+
+False decisions (scrutiny r3/r4 residual):
+- F-1: ``sort -o backups/y.sql data.csv`` allowed — sort output-flag targets
+  were never extracted, so file-type blacklist never ran (only the coarse
+  string heuristic on ``memory/``/``agents.md`` applied).
+- F-2: ``ruff check . > audit/report.md`` / ``> review/x.md`` allowed — the
+  unified redirect helper only knows string indicators, not the ownership
+  classifier's audit/ and review/ domains.
+- F-3: ``sort -o /tmp/out memory/kb/data.csv`` blocked — coarse string gate
+  fires on the owned INPUT file even though the OUTPUT target is safe.
+
+Design (architecture fact #10 anti-regression):
+- One semantic parser ``_extract_sort_output_path`` shared by write-intent
+  detection and legacy path extraction (no regex fork).
+- Authoritative pre-pass: segments with precisely-extractable write targets
+  are classified against the ownership policy BEFORE the coarse string gate;
+  the coarse gate then skips readonly-vocabulary segments (owned strings
+  there are usually inputs) but still guards write commands
+  (defense-in-depth for extractor gaps like ``install -t``).
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from memory_core.tools._guard_classify import (
+    _extract_path_from_execute,
+    _extract_sort_output_path,
+    _segment_has_write_intent,
+)
+from memory_core.tools._guard_patterns import RE_SORT_OUTPUT
+from tests.guard_helpers import run_guard
+
+PROTECTED_TARGET = "memory/kb/out.txt"
+BACKUPS_TARGET = "backups/y.sql"
+SAFE_TARGET = "/tmp/out.txt"
+
+
+@pytest.fixture
+def fake_project(tmp_path):
+    """Create a fake project with memory/ tree for guard subprocess."""
+    (tmp_path / "memory" / "system").mkdir(parents=True)
+    (tmp_path / "memory" / "kb").mkdir(parents=True)
+    (tmp_path / "src").mkdir(parents=True)
+    (tmp_path / "src" / "app.py").write_text("# app\n")
+    return tmp_path
+
+
+# ---------------------------------------------------------------------------
+# F-1: sort output-flag targets must reach blacklist + ownership classifiers
+# ---------------------------------------------------------------------------
+
+SORT_FLAG_BLACKLIST_BLOCK = [
+    f"sort -o {BACKUPS_TARGET} data.csv",
+    f"sort --output={BACKUPS_TARGET} data.csv",
+    f"sort --output {BACKUPS_TARGET} data.csv",
+    f"sort -ro {BACKUPS_TARGET} data.csv",
+    "sort -o dump.sql data.csv",
+    "sort --output=data.bak data.csv",
+]
+
+
+@pytest.mark.parametrize("cmd", SORT_FLAG_BLACKLIST_BLOCK)
+def test_sort_flag_blacklist_block(fake_project, cmd: str) -> None:
+    """F-1: sort output flags targeting blacklisted types must block."""
+    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
+    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
+    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"
+
+
+SORT_FLAG_OWNED_DOMAIN_BLOCK = [
+    f"sort -o {PROTECTED_TARGET} data.csv",
+    f"sort --output={PROTECTED_TARGET} data.csv",
+    f"sort --output {PROTECTED_TARGET} data.csv",
+    f"sort -ro {PROTECTED_TARGET} data.csv",
+    "sort -o audit/report.md data.csv",
+    "sort -o review/findings.md data.csv",
+    "sort --output=memory/docs/note.md data.csv",
+]
+
+
+@pytest.mark.parametrize("cmd", SORT_FLAG_OWNED_DOMAIN_BLOCK)
+def test_sort_flag_owned_domain_block(fake_project, cmd: str) -> None:
+    """F-1: sort output flags targeting owned domains (incl. audit/review) must block."""
+    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
+    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
+    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"
+
+
+# ---------------------------------------------------------------------------
+# F-2: redirect targets in classifier-owned domains (audit/, review/)
+# ---------------------------------------------------------------------------
+
+REDIRECT_OWNED_DOMAIN_BLOCK = [
+    "ruff check . > audit/report.md",
+    "ruff check . > review/x.md",
+    "cat src/a.py >> audit/evidence.txt",
+    "git log > review/history.txt",
+    "echo x 2> audit/err.log",
+    "grep pat src/ &> review/scan.txt",
+]
+
+
+@pytest.mark.parametrize("cmd", REDIRECT_OWNED_DOMAIN_BLOCK)
+def test_redirect_classifier_owned_domain_block(fake_project, cmd: str) -> None:
+    """F-2: redirects into classifier-owned domains (audit/review) must block."""
+    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
+    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
+    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"
+
+
+# ---------------------------------------------------------------------------
+# F-3: owned INPUT files with safe OUTPUT targets must allow
+# ---------------------------------------------------------------------------
+
+OWNED_INPUT_SAFE_OUTPUT_ALLOW = [
+    f"sort -o {SAFE_TARGET} memory/kb/data.csv",
+    f"sort --output {SAFE_TARGET} memory/kb/data.csv",
+    f"sort --output={SAFE_TARGET} memory/kb/data.csv",
+    "cat memory/kb/README.md > /tmp/out.txt",
+    "grep pattern memory/kb/x.md > /tmp/matches.txt",
+    "git log memory/kb/ > /tmp/history.txt",
+]
+
+
+@pytest.mark.parametrize("cmd", OWNED_INPUT_SAFE_OUTPUT_ALLOW)
+def test_owned_input_safe_output_allow(fake_project, cmd: str) -> None:
+    """F-3: owned paths as INPUT with safe OUTPUT targets must allow."""
+    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
+    assert rc == 0, f"Expected exit 0 for '{cmd}', got {rc}. Output: {output}"
+    assert output.get("decision") == "allow", f"Expected allow for '{cmd}', got {output}"
+
+
+# ---------------------------------------------------------------------------
+# Semantic parser unit tests (single source of truth for sort output flags)
+# ---------------------------------------------------------------------------
+
+
+class TestExtractSortOutputPath:
+    """_extract_sort_output_path handles all GNU sort output flag forms."""
+
+    def _extract(self, segment: str) -> list[str]:
+        match = RE_SORT_OUTPUT.match(segment)
+        assert match is not None, f"RE_SORT_OUTPUT failed to match: {segment!r}"
+        return _extract_sort_output_path(match)
+
+    def test_exact_short_flag_space_form(self):
+        assert self._extract("sort -o out.txt data.csv") == ["out.txt"]
+
+    def test_combined_flag_space_form(self):
+        assert self._extract("sort -ro out.txt data.csv") == ["out.txt"]
+        assert self._extract("sort -nruo out.txt data.csv") == ["out.txt"]
+
+    def test_attached_gnu_form(self):
+        assert self._extract("sort -oout.txt data.csv") == ["out.txt"]
+        assert self._extract("sort -roout.txt data.csv") == ["out.txt"]
+
+    def test_long_flag_equals_form(self):
+        assert self._extract("sort --output=out.txt data.csv") == ["out.txt"]
+
+    def test_long_flag_space_form(self):
+        assert self._extract("sort --output out.txt data.csv") == ["out.txt"]
+
+    def test_no_output_flag_returns_empty(self):
+        assert self._extract("sort -r data.csv") == []
+        assert self._extract("sort -t , -k 2 data.csv") == []
+
+    def test_value_carrying_flags_not_misdetect(self):
+        """R4-3 guard: -T/-S/-k value forms must not be treated as -o targets."""
+        assert self._extract("sort -T/tmp/work data.csv") == []
+        assert self._extract("sort -S1Go data.csv") == []
+        assert self._extract("sort -k1,1 data.csv") == []
+
+    def test_dangling_flag_returns_empty(self):
+        assert self._extract("sort -o") == []
+        assert self._extract("sort --output") == []
+
+
+# ---------------------------------------------------------------------------
+# Write-intent ↔ extraction consistency (no regex fork drift)
+# ---------------------------------------------------------------------------
+
+
+class TestIntentExtractionConsistency:
+    """Write-intent detection and target extraction must agree for sort."""
+
+    SORT_FORMS = [
+        "sort -o memory/kb/out.txt data.csv",
+        "sort -ro memory/kb/out.txt data.csv",
+        "sort --output=memory/kb/out.txt data.csv",
+        "sort --output memory/kb/out.txt data.csv",
+        "sort -oout.txt data.csv",
+        "sort -roout.txt data.csv",
+        "sort -r data.csv",
+        "sort -T/tmp/work data.csv",
+        "sort -k1,1 data.csv",
+    ]
+
+    @pytest.mark.parametrize("segment", SORT_FORMS)
+    def test_intent_iff_extractable(self, segment: str) -> None:
+        """_segment_has_write_intent True ⟺ semantic parser finds an output target."""
+        match = RE_SORT_OUTPUT.match(segment)
+        extracted = _extract_sort_output_path(match) if match else []
+        assert _segment_has_write_intent(segment) is bool(extracted), (
+            f"intent/extraction drift for {segment!r}: extracted={extracted}"
+        )
+
+
+# ---------------------------------------------------------------------------
+# Defense-in-depth: coarse gate still guards write commands
+# ---------------------------------------------------------------------------
+
+
+COARSE_GATE_WRITE_COMMANDS_BLOCK = [
+    "install -t memory/log app.conf",
+    "install --target-directory=memory/log app.conf",
+    "rsync -a src/ --target-directory=memory/docs/",
+    "mv -t memory/system x",
+]
+
+
+@pytest.mark.parametrize("cmd", COARSE_GATE_WRITE_COMMANDS_BLOCK)
+def test_coarse_gate_write_commands_block(fake_project, cmd: str) -> None:
+    """INFRA-551: readonly-vocab skip must NOT weaken write-command gating."""
+    rc, output = run_guard({"tool_name": "Execute", "tool_input": {"command": cmd}}, cwd=fake_project)
+    assert rc == 2, f"Expected exit 2 for '{cmd}', got {rc}. Output: {output}"
+    assert output.get("decision") == "block", f"Expected block for '{cmd}', got {output}"
+
+
+# ---------------------------------------------------------------------------
+# Extraction dispatch: sort output flag participates in legacy pipeline
+# ---------------------------------------------------------------------------
+
+
+class TestSortExtractionDispatch:
+    """_extract_path_from_execute returns sort output-flag targets."""
+
+    @pytest.mark.parametrize(
+        ("command", "expected"),
+        [
+            ("sort -o backups/y.sql data.csv", ["backups/y.sql"]),
+            ("sort --output=memory/kb/out.txt data.csv", ["memory/kb/out.txt"]),
+            ("sort -ro /tmp/out data.csv", ["/tmp/out"]),
+            ("sort -r data.csv", []),
+        ],
+    )
+    def test_extraction_dispatch(self, command: str, expected: list[str]) -> None:
+        assert _extract_path_from_execute(command) == expected
+
+    def test_redirect_takes_priority_for_sort_with_redirect(self):
+        """sort with BOTH -o and > : both targets extracted by redirect findall."""
+        paths = _extract_path_from_execute("sort -o /tmp/a data.csv > /tmp/b")
+        assert "/tmp/a" in paths and "/tmp/b" in paths
```

## Files in this shard

memory_core/tools/_guard_classify.py
memory_core/tools/_guard_patterns.py
tests/test_guard_infra551.py

## Budget Instructions

You have a maximum of 30 minutes for this review. Focus on the most critical findings first.
Limit your output to the top 20 findings maximum. Return only valid JSON.
