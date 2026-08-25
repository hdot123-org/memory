"""Tests for guard compound command escape fixes (VAL-GUARD-001~025).

TDD red phase: Tests that should FAIL before implementing Fix-1/2/3.
"""

import pytest

from tests.guard_helpers import run_guard

# ============================================================================
# VAL-GUARD-001: 逃逸矩阵 — 20 条全部 block
# ============================================================================


class TestEscapeMatrix:
    """VAL-GUARD-001: 三方远征逃逸矩阵 20 条逐条 block"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        """Create a fake project with memory/system directory"""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    ESCAPE_MATRIX = [
        # (id, command, description)
        (
            "E1",
            "touch /tmp/decoy.txt && python3 -c \"import shutil; shutil.move('/tmp/decoy.txt', 'memory/system/x')\"",
            "Fix-1 兜底 + Fix-3 python 词汇表",
        ),
        ("E2", 'touch /tmp/d.txt && sh -c "mv /tmp/d.txt memory/system/y"', "Fix-2 分段 + Fix-1 兜底"),
        ("N1", "echo data > /tmp/out.log && mv /tmp/out.log memory/kb/notes.md", "Fix-2 分段：第二段 mv 目标"),
        ("N2", "python3 -c \"import os; os.replace('/tmp/a', 'memory/system/b')\"", "Fix-3 python os.replace"),
        ("N7", "python3 -c \"import shutil; shutil.rmtree('memory/kb')\"", "Fix-3 python shutil.rmtree"),
        ("N3", "echo x | tee /tmp/f && rm -rf memory/kb", "Fix-2 分段：rm 段 block"),
        ("N4", "touch /tmp/f.tar && tar cf x.tar --directory memory/docs .", "Fix-3 tar --directory + Fix-1 兜底"),
        ("N5", "node -e \"require('fs').unlinkSync('memory/kb/temp.md')\"", "Fix-3 node unlinkSync"),
        ("S6", 'D=memory/system; touch "$D/flag"', "Fix-1 兜底：命令文本含 memory/"),
        ("F1", "touch x && mv -t memory/system x", "Fix-3 GNU -t 目标前置"),
        ("F2", "cp -t memory/kb src.txt", "Fix-3 cp -t 目标前置"),
        ("F7", "install -t memory/log app.conf", "Fix-3 install -t 目标前置"),
        ("V-redirect-hitorder", "echo ok > /tmp/a && echo hack >> memory/kb/hack.md", "Fix-2 分段：第二段重定向目标"),
        (
            "E1-variant",
            "touch d.txt && python3 -c \"import shutil; shutil.move('d.txt', 'memory/log/x')\"",
            "Fix-1 + Fix-3 覆盖第四域",
        ),
        ("N4-variant", "cd memory && tar cf /tmp/x.tar .", "Fix-3 cd 段内 owned"),
        ("F1-variant", "mv --target-directory=memory/system /tmp/f", "Fix-3 长旗标 --target-directory="),
        ("E2-variant", "sh -c 'rm memory/system/state.json'", "Fix-2 引号边界 + Fix-1 兜底"),
        (
            "N5-variant",
            "node -e \"require('fs').rmSync('memory/system/cache', {recursive:true})\"",
            "Fix-3 node rmSync",
        ),
        ("S6-variant", 'P=./memory/kb; mkdir "$P/new"', "Fix-1 兜底：memory/ 字面量"),
        ("N3-variant", "tee /tmp/log <<< data; rm -f memory/docs/f.md", "Fix-2 ; 分段 + rm 段 block"),
    ]

    @pytest.mark.parametrize("escape_id,command,desc", ESCAPE_MATRIX)
    def test_escape_matrix_all_blocked(self, fake_project, escape_id, command, desc):
        """每条逃逸命令必须 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{escape_id} ({desc}): expected exit 2, got {exit_code}"
        assert output.get("decision") == "block", f"{escape_id}: decision should be block"
        assert output.get("hookSpecificOutput", {}).get("permissionDecision") == "deny", (
            f"{escape_id}: permissionDecision should be deny"
        )


# ============================================================================
# VAL-GUARD-002: 原始 PoC 确定性拦截
# ============================================================================


class TestOriginalPoc:
    """VAL-GUARD-002: 原始 PoC 修复前后均 block"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_original_poc_blocked(self, fake_project):
        """原始 PoC: mkdir -p tmp && mv important_file memory/system/"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "mkdir -p tmp && mv important_file memory/system/"},
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_poc_prefix_variant_blocked(self, fake_project):
        """PoC 前缀变形: true && mkdir -p tmp && mv important_file memory/system/"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "true && mkdir -p tmp && mv important_file memory/system/"},
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_poc_comment_variant_blocked(self, fake_project):
        """PoC 注释变形: # comment\\nmkdir -p tmp && mv important_file memory/system/"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "# comment\nmkdir -p tmp && mv important_file memory/system/"},
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-003: Fix-1 兜底无条件化（单元级）
# ============================================================================


class TestFix1UnconditionalGate:
    """VAL-GUARD-003: Fix-1 段级写意图门控无条件执行"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_non_empty_extraction_still_blocks_owned_literal(self, fake_project):
        """非空提取列表不再遮蔽 owned 字面量（写意图段）"""
        # 第一段提取到 /tmp/x（非空），第二段有写意图且含 memory/ 字面量
        payload = {"tool_name": "Execute", "tool_input": {"command": "echo hi > /tmp/x && mv /tmp/y memory/README"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, "Should block due to write intent + memory/ literal in second segment"
        assert output.get("decision") == "block"

    def test_backslash_variant_blocked(self, fake_project):
        """memory\\ 反斜杠形态也应 block（写意图段）"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "echo hi > /tmp/x && mv /tmp/y memory\\README"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_agents_md_literal_blocked(self, fake_project):
        """AGENTS.md 字面量也应 block（写意图段）"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "echo hi > /tmp/x && rm AGENTS.md"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-004: Fix-3 词汇表扩展（单元级）
# ============================================================================


class TestFix3Vocabulary:
    """VAL-GUARD-004: GNU -t / python / node 词汇表"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    GNU_T_VARIANTS = [
        ("mv -t memory/system x", "mv -t"),
        ("mv --target-directory=memory/system x", "mv --target-directory="),
        ("cp -t memory/kb src.txt", "cp -t"),
        ("cp --target-directory=memory/kb src.txt", "cp --target-directory="),
        ("install -t memory/log app.conf", "install -t"),
        ("install --target-directory=memory/log app.conf", "install --target-directory="),
        ("rsync -a src/ -t memory/docs/", "rsync -t"),
        ("rsync -a src/ --target-directory=memory/docs/", "rsync --target-directory="),
    ]

    @pytest.mark.parametrize("command,desc", GNU_T_VARIANTS)
    def test_gnu_t_target_directory(self, fake_project, command, desc):
        """GNU -t / --target-directory=DEST 目标前置"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block"

    PYTHON_WRITE_APIS = [
        ("python3 -c \"import os; os.replace('/tmp/a', 'memory/system/b')\"", "os.replace"),
        ("python3 -c \"import os; os.rename('/tmp/a', 'memory/system/b')\"", "os.rename"),
        ("python3 -c \"import shutil; shutil.move('/tmp/a', 'memory/system/b')\"", "shutil.move"),
        ("python3 -c \"import shutil; shutil.copy('/tmp/a', 'memory/system/b')\"", "shutil.copy"),
        ("python3 -c \"import shutil; shutil.copy2('/tmp/a', 'memory/system/b')\"", "shutil.copy2"),
        ("python3 -c \"import shutil; shutil.copyfile('/tmp/a', 'memory/system/b')\"", "shutil.copyfile"),
        ("python3 -c \"import shutil; shutil.rmtree('memory/kb')\"", "shutil.rmtree"),
        ("python3 -c \"import os; os.remove('memory/system/x')\"", "os.remove"),
        ("python3 -c \"import os; os.unlink('memory/system/x')\"", "os.unlink"),
        (
            "python3 -c \"from pathlib import Path; Path('memory/system/a').write_text('x')\"",
            "Path.write_text (implicit target)",
        ),
        (
            "python3 -c \"from pathlib import Path; Path('memory/system/a').write_bytes(b'x')\"",
            "Path.write_bytes (implicit target)",
        ),
    ]

    @pytest.mark.parametrize("command,desc", PYTHON_WRITE_APIS)
    def test_python_write_apis(self, fake_project, command, desc):
        """Python 写入 API 词汇表"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block"

    NODE_WRITE_APIS = [
        ("node -e \"require('fs').unlinkSync('memory/kb/temp.md')\"", "unlinkSync"),
        ("node -e \"require('fs').rmSync('memory/system/cache', {recursive:true})\"", "rmSync"),
        ("node -e \"require('fs').rmdirSync('memory/kb/old')\"", "rmdirSync"),
        ("node -e \"require('fs').renameSync('/tmp/a', 'memory/system/b')\"", "renameSync"),
        ("node -e \"require('fs').cpSync('/tmp/a', 'memory/system/b')\"", "cpSync"),
    ]

    @pytest.mark.parametrize("command,desc", NODE_WRITE_APIS)
    def test_node_write_apis(self, fake_project, command, desc):
        """Node 写入 API 词汇表"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-005: cd 语义段拦截
# ============================================================================


class TestCdSemantics:
    """VAL-GUARD-005: cd <owned> 段拦截"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_cd_owned_segment_blocked(self, fake_project):
        """cd memory && rm -f x.md 应 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "cd memory && rm -f x.md"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_cd_non_owned_allowed(self, fake_project):
        """cd /tmp && rm -f x.md 应 allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "cd /tmp && rm -f x.md"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0
        assert output.get("decision") == "allow"


# ============================================================================
# VAL-GUARD-006: find -delete / -fprintf 拦截
# ============================================================================


class TestFindDelete:
    """VAL-GUARD-006: find -delete / -fprintf 指向 owned 域"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_find_delete_blocked(self, fake_project):
        """find memory/docs -name '*.tmp' -delete 应 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "find memory/docs -name '*.tmp' -delete"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_find_fprintf_blocked(self, fake_project):
        """find . -fprintf memory/system/list.txt '%p\\n' 应 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "find . -fprintf memory/system/list.txt '%p\\n'"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-007: 长旗标参数对齐
# ============================================================================


class TestLongFlags:
    """VAL-GUARD-007: --exclude=x 类长旗标不破坏参数对齐"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_long_flag_owned_target_blocked(self, fake_project):
        """rsync -a --exclude='*.pyc' /tmp/src/ memory/docs/ 应 block"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "rsync -a --exclude='*.pyc' /tmp/src/ memory/docs/"},
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_long_flag_non_owned_target_allowed(self, fake_project):
        """rsync -a --exclude='*.pyc' /tmp/src/ /tmp/dst/ 应 allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "rsync -a --exclude='*.pyc' /tmp/src/ /tmp/dst/"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0
        assert output.get("decision") == "allow"


# ============================================================================
# VAL-GUARD-008: 残余矩阵 — 逐条 allow
# ============================================================================


class TestResidualMatrix:
    """VAL-GUARD-008: 零字面量残余矩阵 6 条逐条 allow"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    RESIDUAL_MATRIX = [
        ("V-cd", "cd memory && cd kb && rm -f x.md", "纯 cwd 语义"),
        ("V-cd-variant", "cd memory && cd system && touch pwned", "纯 cwd 语义变体"),
        ("V-find-delete", 'd="memory"; b="kb"; find "$d/$b" -name x -delete', "变量拆散"),
        ("V-find-delete-variant", 'd1="memo"; d2="ry/kb"; rm -rf "$d1/$d2"', "变量拆散变体"),
        ("V-base64", "echo bWVtb3J5L2ti | base64 -d | xargs rm -f", "编码路径"),
        (
            "V-base64-variant",
            "python3 -c \"import base64,os; os.remove(base64.b64decode('bWVtb3J5L3N5c3RlbQ==').decode())\"",
            "编码路径变体",
        ),
    ]

    @pytest.mark.parametrize("residual_id,command,desc", RESIDUAL_MATRIX)
    def test_residual_matrix_all_allowed(self, fake_project, residual_id, command, desc):
        """每条残余命令必须 allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0, f"{residual_id} ({desc}): expected exit 0, got {exit_code}"
        assert output.get("decision") == "allow", f"{residual_id}: decision should be allow"


# ============================================================================
# VAL-GUARD-009: 残余边界 — 字面量重现即拦
# ============================================================================


class TestResidualBoundary:
    """VAL-GUARD-009: 残余形态中 owned 字面量重现时立即 block"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_residual_literal_reappear_blocked(self, fake_project):
        """cd memory && cd kb && rm -f memory/system/x.md 应 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "cd memory && cd kb && rm -f memory/system/x.md"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-010: S6 与残余的边界一致性
# ============================================================================


class TestS6Boundary:
    """VAL-GUARD-010: S6 block 与变量拆散 allow 成对固化"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_s6_complete_indicator_blocked(self, fake_project):
        """S6: D=memory/system; touch "$D/flag" 含完整指示串 → block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": 'D=memory/system; touch "$D/flag"'}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_s6_scattered_allowed(self, fake_project):
        """变量拆散: d1='memo'; d2='ry/kb'; rm -rf '$d1/$d2' 无完整指示串 → allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": 'd1="memo"; d2="ry/kb"; rm -rf "$d1/$d2"'}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0
        assert output.get("decision") == "allow"


# ============================================================================
# VAL-GUARD-011: 日常开发命令对照矩阵 — 全部 allow
# ============================================================================


class TestControlMatrix:
    """VAL-GUARD-011: 11 条日常开发命令全部 allow"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "src").mkdir()
        return tmp_path

    CONTROL_MATRIX = [
        ("git status", "git status --short --branch", "git 只读"),
        ("pytest", "python -m pytest tests/test_guard_classify.py -q --no-cov", "测试运行"),
        ("ruff", "ruff check memory_core/", "lint"),
        ("mkdir build", "mkdir -p build && touch build/out.txt", "构建目录"),
        ("echo /tmp", "echo data > /tmp/session.log", "/tmp 文件"),
        ("write src", "echo 'print(1)' > src/app.py", "写普通源码"),
        ("touch normal", "touch normal.txt", "普通文件"),
        ("compound legal", "python -m pytest -q --no-cov && ruff check .", "复合合法命令"),
        ("grep owned /tmp", 'grep "memory/kb" src/app.py > /tmp/out.txt', "读语义 + /tmp 重定向"),
        ("commit owned msg", 'git commit -m "docs: update memory/kb notes"', "commit message 含 owned"),
        ("echo owned /tmp", 'echo "see memory/system for details" > /tmp/note.txt', "echo owned + /tmp 重定向"),
    ]

    @pytest.mark.parametrize("name,command,desc", CONTROL_MATRIX)
    def test_control_matrix_all_allowed(self, fake_project, name, command, desc):
        """每条日常命令必须 allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0, f"{name} ({desc}): expected exit 0, got {exit_code}"
        assert output.get("decision") == "allow", f"{name}: decision should be allow"


# ============================================================================
# VAL-GUARD-012: 引号内操作符不切分
# ============================================================================


class TestQuoteBoundary:
    """VAL-GUARD-012: 引号内 && / ; / | 是字符串内容不切分"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "src").mkdir()
        return tmp_path

    QUOTE_BOUNDARY_CASES = [
        ('echo "a && b" > /tmp/x', "引号内 && 是内容"),
        ('git commit -m "fix: a && b && c"', "commit message 含 &&"),
        ("echo 'memory || docs' > /tmp/note.txt", "引号内含 owned 词根"),
        ('grep "a;b" src/app.py', "引号内 ; 是 grep 模式"),
    ]

    @pytest.mark.parametrize("command,desc", QUOTE_BOUNDARY_CASES)
    def test_quote_boundary_not_split(self, fake_project, command, desc):
        """引号内操作符不应被误切分"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0, f"{desc}: should allow"
        assert output.get("decision") == "allow"


# ============================================================================
# VAL-GUARD-013: 空命令与空白命令
# ============================================================================


class TestEmptyCommands:
    """VAL-GUARD-013: 空命令 / 纯空白命令 allow"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    EMPTY_CASES = [
        ("", "空字符串"),
        ("   ", "纯空格"),
        ("\t\n", "制表符和换行"),
    ]

    @pytest.mark.parametrize("command,desc", EMPTY_CASES)
    def test_empty_or_whitespace_allowed(self, fake_project, command, desc):
        """空命令和纯空白命令应 allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0, f"{desc}: should allow"
        assert output.get("decision") == "allow"

    def test_execute_without_command_field_allowed(self, fake_project):
        """Execute 无 command 字段应 allow"""
        payload = {"tool_name": "Execute", "tool_input": {}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0
        assert output.get("decision") == "allow"


# ============================================================================
# VAL-GUARD-014: 直接攻击对照矩阵 — 全部 block
# ============================================================================


class TestLegacyBlocks:
    """VAL-GUARD-014: 既有单段直接攻击全部维持 block"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    LEGACY_ATTACKS = [
        ("mv x memory/system/y", "RE_MV 末位目标"),
        ("rm -rf memory/kb", "RE_RM"),
        ("echo x > memory/system/f", "RE_REDIRECT"),
        ("rm -f memory/*/cache", "uncertain 通配 + owned 字符串"),
    ]

    @pytest.mark.parametrize("command,desc", LEGACY_ATTACKS)
    def test_legacy_attacks_still_blocked(self, fake_project, command, desc):
        """直接攻击必须 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-015: uncertain 通配语义保留
# ============================================================================


class TestUncertainWildcard:
    """VAL-GUARD-015: uncertain-path 语义在分段化后保留"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_owned_uncertain_blocked(self, fake_project):
        """rm -f memory/*/tmp && echo done 应 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "rm -f memory/*/tmp && echo done"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_non_owned_uncertain_allowed(self, fake_project):
        """rm -f /tmp/*/cache && echo done 应 allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "rm -f /tmp/*/cache && echo done"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0
        assert output.get("decision") == "allow"


# ============================================================================
# VAL-GUARD-023: 单段多重定向逃逸拦截
# ============================================================================


class TestMultiRedirect:
    """VAL-GUARD-023: 单段多重定向 findall 语义"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_multi_redirect_single_segment_blocked(self, fake_project):
        """echo x 1>/tmp/a 2>memory/kb/err.log 应 block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "echo x 1>/tmp/a 2>memory/kb/err.log"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-024: heredoc + 换行分隔逃逸拦截
# ============================================================================


class TestHeredocEscape:
    """VAL-GUARD-024: heredoc + 换行分隔逃逸"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_heredoc_newline_escape_blocked(self, fake_project):
        """cat > /tmp/decoy.txt << 'EOF'\\nbody\\nEOF\\ntouch memory/kb/pwned 应 block"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "cat > /tmp/decoy.txt << 'EOF'\nbody\nEOF\ntouch memory/kb/pwned"},
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"


# ============================================================================
# VAL-GUARD-025: MEMORY_HOOK_FORCE=1 语义固化
# ============================================================================


class TestForceBypass:
    """VAL-GUARD-025: MEMORY_HOOK_FORCE=1 窄旁路语义"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "backups").mkdir()
        return tmp_path

    def test_force_escape_still_blocked(self, fake_project, monkeypatch):
        """FORCE=1 下逃逸矩阵抽样仍 block"""
        monkeypatch.setenv("MEMORY_HOOK_FORCE", "1")

        # E1 抽样
        payload = {
            "tool_name": "Execute",
            "tool_input": {
                "command": "touch /tmp/decoy.txt && python3 -c \"import shutil; shutil.move('/tmp/decoy.txt', 'memory/system/x')\""
            },
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

        # F1 抽样
        payload = {"tool_name": "Execute", "tool_input": {"command": "touch x && mv -t memory/system x"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

        # 原始 PoC 抽样
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "mkdir -p tmp && mv important_file memory/system/"},
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2
        assert output.get("decision") == "block"

    def test_force_file_type_bypass_allowed(self, fake_project, monkeypatch):
        """FORCE=1 + 文件类型黑名单路径仍 allow"""
        monkeypatch.setenv("MEMORY_HOOK_FORCE", "1")

        payload = {"tool_name": "Execute", "tool_input": {"command": "touch backups/x.bak"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0
        assert output.get("decision") == "allow"


# ============================================================================
# Round 3: Scrutiny Round-2 Blocking Escapes (R3-1 ~ R3-6)
# ============================================================================


class TestRound3Escapes:
    """Round 3: 6 blocking escapes from scrutiny round-2"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory" / "kb").mkdir(parents=True)
        (tmp_path / "backups").mkdir()
        return tmp_path

    # R3-1: &>/>& redirect operators not detected
    R3_REDIRECT_VARIANTS = [
        ("echo hi &> memory/kb/x", "&> redirect to owned"),
        ("git log &> memory/kb/out.txt", "&> redirect with git"),
        ("cat src/a.py &> memory/kb/out.txt", "&> redirect with cat"),
        ("echo hi >& memory/kb/x", ">& redirect to owned"),
        ("sort data.csv >& memory/kb/out.txt", ">& redirect with sort"),
    ]

    @pytest.mark.parametrize("command,desc", R3_REDIRECT_VARIANTS)
    def test_r3_1_ampersand_redirect_blocked(self, fake_project, command, desc):
        """R3-1: &>/>& redirect to owned paths should block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block", f"{desc}: decision should be block"

    # R3-2: git stash in readonly set
    R3_STASH_VARIANTS = [
        ("git stash push memory/kb/x", "stash push owned"),
        ("git stash push -m wip memory/kb", "stash push -m owned"),
        ("git stash pop memory/kb", "stash pop with owned arg"),
    ]

    @pytest.mark.parametrize("command,desc", R3_STASH_VARIANTS)
    def test_r3_2_git_stash_blocked(self, fake_project, command, desc):
        """R3-2: git stash should not be in readonly set"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block", f"{desc}: decision should be block"

    # R3-3: sed --in-place long flag not detected
    R3_SED_INPLACE_VARIANTS = [
        ("sed --in-place 's/a/b/' memory/kb/README.md", "--in-place long flag"),
        ("sed --in-place=.bak 's/a/b/' memory/kb/README.md", "--in-place=EXT long flag"),
        ("sed -i 's/a/b/' memory/kb/README.md", "-i short flag (baseline)"),
        ("sed -in 's/a/b/' memory/kb/README.md", "-in combined short flags"),
    ]

    @pytest.mark.parametrize("command,desc", R3_SED_INPLACE_VARIANTS)
    def test_r3_3_sed_inplace_blocked(self, fake_project, command, desc):
        """R3-3: sed --in-place and variants should block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block", f"{desc}: decision should be block"

    # R3-4: sort -o/--output= not handled
    R3_SORT_OUTPUT_VARIANTS = [
        ("sort -o memory/kb/out.txt data.csv", "sort -o owned target"),
        ("sort --output=memory/kb/out.txt data.csv", "sort --output= owned target"),
        ("sort -o /tmp/out.txt data.csv", "sort -o /tmp (control, should allow)"),
    ]

    @pytest.mark.parametrize("command,desc", R3_SORT_OUTPUT_VARIANTS[:2])
    def test_r3_4_sort_output_blocked(self, fake_project, command, desc):
        """R3-4: sort -o/--output= to owned paths should block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block", f"{desc}: decision should be block"

    def test_r3_4_sort_output_tmp_allowed(self, fake_project):
        """R3-4 control: sort -o /tmp should allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "sort -o /tmp/out.txt data.csv"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0, "sort -o /tmp should allow"
        assert output.get("decision") == "allow"

    # R3-5: _check_redirect_targets (unified helper) missing file type blacklist
    R3_REDIRECT_BLACKLIST_VARIANTS = [
        ("git show HEAD > backups/y.sql", "git show to backups/.sql"),
        ("git diff > backups/x.bak", "git diff to backups/.bak"),
        ("git status > backups/s.sql", "git status to backups/.sql"),
        ("sed -n '1p' input.txt > backups/y.sql", "sed -n to backups/.sql"),
        ("echo data > backups/dump.sqlite", "echo to backups/.sqlite"),
    ]

    @pytest.mark.parametrize("command,desc", R3_REDIRECT_BLACKLIST_VARIANTS)
    def test_r3_5_redirect_file_type_blacklist_blocked(self, fake_project, command, desc):
        """R3-5: redirect to file-type-blacklisted targets should block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block", f"{desc}: decision should be block"

    # R3-6: ruff format / ruff check --fix not handled
    R3_RUFF_WRITE_VARIANTS = [
        ("ruff format memory/kb/", "ruff format owned"),
        ("ruff check --fix memory/kb/x.py", "ruff check --fix owned"),
        ("ruff check memory/kb/", "ruff check readonly (control, should allow)"),
    ]

    @pytest.mark.parametrize("command,desc", R3_RUFF_WRITE_VARIANTS[:2])
    def test_r3_6_ruff_write_blocked(self, fake_project, command, desc):
        """R3-6: ruff format and ruff check --fix should block"""
        payload = {"tool_name": "Execute", "tool_input": {"command": command}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, f"{desc}: should block"
        assert output.get("decision") == "block", f"{desc}: decision should be block"

    def test_r3_6_ruff_check_readonly_allowed(self, fake_project):
        """R3-6 control: ruff check (readonly) should allow"""
        payload = {"tool_name": "Execute", "tool_input": {"command": "ruff check memory/kb/"}}
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 0, "ruff check (readonly) should allow"
        assert output.get("decision") == "allow"


# ============================================================================
# Round 3: Non-blocking items (NB-1, NB-2)
# ============================================================================


class TestRound3NonBlocking:
    """Round 3: Non-blocking items to document or fix"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory" / "kb").mkdir(parents=True)
        return tmp_path

    def test_nb_2_2to1_redirect_not_split(self, fake_project):
        """NB-2: 2>&1 should not be split by command splitter"""
        # Command with 2>&1 and owned literal should still work correctly
        payload = {"tool_name": "Execute", "tool_input": {"command": "grep memory/kb src/ 2>&1 > /tmp/out.txt"}}
        exit_code, output = run_guard(payload, fake_project)
        # Should allow (grep is readonly, > /tmp is safe)
        assert exit_code == 0, "grep with 2>&1 to /tmp should allow"
        assert output.get("decision") == "allow"
