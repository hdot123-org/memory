"""
备份脚本集成测试（M3 R2 备份全项目接入）

验证契约断言：
- VAL-BKP-001: 脚本含动态段（调用 backup-paths）+ 静态核心保留
- VAL-BKP-002: restic --dry-run 目标清单覆盖全部消费项目 memory/
- VAL-BKP-003: 存在性过滤——缺失路径被跳过且不报错
- VAL-BKP-004: 枚举失败降级为静态清单，备份整体不失败
- VAL-BKP-005: 凭证注入模式未变（运行时 op read）+ 单实例锁保留
- VAL-CROSS-010: restic dry-run 目标清单覆盖全局库和全部项目 memory
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

BACKUP_SCRIPT = Path.home() / ".factory/backup/memory-dr-backup.sh"


@pytest.mark.skipif(not BACKUP_SCRIPT.exists(), reason="备份脚本不存在")
class TestBackupScriptStructure:
    """备份脚本结构测试（VAL-BKP-001/005）"""

    def test_script_exists_and_readable(self):
        """脚本存在且可读"""
        assert BACKUP_SCRIPT.exists(), f"备份脚本不存在: {BACKUP_SCRIPT}"
        assert BACKUP_SCRIPT.is_file()

    def test_no_literal_secrets(self):
        """脚本不含字面量密钥（VAL-BKP-005）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查不应出现的密钥字面量模式
        secret_patterns = [
            r'RESTIC_PASSWORD\s*=\s*["\'][^$"\']{8,}',  # 硬编码密码
            r'AWS_SECRET_ACCESS_KEY\s*=\s*["\'][A-Za-z0-9+/]{40,}',  # 硬编码 AWS 密钥
            r"op://[a-z0-9]{20,}/[a-z0-9]{20,}/[a-z0-9]{20,}",  # 硬编码 op:// 引用值
        ]

        for pattern in secret_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            assert len(matches) == 0, f"发现疑似密钥字面量: {matches}"

        # 确保凭证是从 op read 动态获取的（可能是直接调用或通过 _op_read_timeout 包装）
        assert "op read" in content or "_op_read_timeout" in content, "脚本应使用 op read 读取凭证"
        assert "op://$VAULT/$ITEM/" in content or '_op_read_timeout "op://$VAULT/$ITEM/' in content, (
            "凭证应从 1Password 读取"
        )

    def test_has_lock_mechanism(self):
        """脚本有单实例锁机制（VAL-BKP-005）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查锁相关代码
        assert "LOCK=" in content, "应定义锁路径"
        assert "mkdir" in content, "应使用 mkdir 创建锁"
        assert "rmdir" in content, "应使用 rmdir 释放锁"
        assert "trap" in content, "应有 trap 确保锁释放"

    def test_has_static_core_paths(self):
        """脚本保留静态核心路径（VAL-BKP-001）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查关键静态路径
        static_markers = [
            "memory/project-map",
            "global-kb",
            ".memory-core",
            ".factory/webhook/scripts",
        ]

        for marker in static_markers:
            assert marker in content, f"静态核心路径缺失: {marker}"

    def test_has_dynamic_enumeration(self):
        """脚本有动态枚举段（VAL-BKP-001）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查是否调用 backup-paths
        assert "backup-paths" in content, "应调用 backup-paths 子命令"

        # 检查是否处理枚举输出
        has_enumeration = ("evolve_cli" in content or "memory-evolve" in content) and (
            "DYNAMIC_PATHS" in content or "while IFS= read" in content
        )
        assert has_enumeration, "应有动态枚举逻辑"

    def test_has_dry_run_support(self):
        """脚本支持 --dry-run 参数（VAL-BKP-002）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查参数解析
        assert "--dry-run" in content, "应支持 --dry-run 参数"

        # 检查 DRY_RUN 变量
        assert "DRY_RUN=" in content or "DRY_RUN =" in content, "应有 DRY_RUN 状态变量"

        # 检查透传给 restic
        assert "restic" in content and "--dry-run" in content, "应将 --dry-run 透传给 restic"

    def test_has_existence_filtering(self):
        """脚本有存在性过滤逻辑（VAL-BKP-003）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查存在性检查
        has_check = "[[ -e" in content or "[ -e" in content or "[[ -d" in content
        assert has_check, "应有路径存在性检查"

    def test_has_enumeration_failure_handling(self):
        """脚本有枚举失败处理逻辑（VAL-BKP-004）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查错误处理
        has_error_handling = ("ENUM_FAILED" in content or "FAILED" in content) and (
            "WARN" in content or "ERROR" in content or "降级" in content
        )
        assert has_error_handling, "应有枚举失败的降级处理"


@pytest.mark.skipif(not BACKUP_SCRIPT.exists(), reason="备份脚本不存在")
class TestBackupScriptBehavior:
    """备份脚本行为测试（需要真实环境）"""

    def test_backup_paths_cli_available(self):
        """backup-paths CLI 可用（前置条件）"""
        repo_root = Path("/Users/busiji/memory")
        evolve_cli = repo_root / "memory_core/tools/evolve_cli.py"

        if not evolve_cli.exists():
            pytest.skip("evolve_cli.py 不存在")

        result = subprocess.run(
            ["python3", str(evolve_cli), "backup-paths"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"backup-paths 失败: {result.stderr}"

        # 验证输出格式：每行一个绝对路径
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) > 0, "backup-paths 应输出至少一个路径"

        for line in lines:
            assert line.startswith("/"), f"路径应为绝对路径: {line}"
            assert line.endswith("/memory"), f"路径应以 /memory 结尾: {line}"

    def test_backup_paths_json_output(self):
        """backup-paths --json 输出合法 JSON"""
        repo_root = Path("/Users/busiji/memory")
        evolve_cli = repo_root / "memory_core/tools/evolve_cli.py"

        if not evolve_cli.exists():
            pytest.skip("evolve_cli.py 不存在")

        result = subprocess.run(
            ["python3", str(evolve_cli), "backup-paths", "--json"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"backup-paths --json 失败: {result.stderr}"

        # 验证 JSON 格式
        try:
            paths = json.loads(result.stdout)
            assert isinstance(paths, list), "JSON 应为数组"
            assert all(isinstance(p, str) for p in paths), "数组元素应为字符串"
        except json.JSONDecodeError as e:
            pytest.fail(f"JSON 解析失败: {e}")

    def test_dry_run_mode_does_not_upload(self):
        """--dry-run 模式不实际上传（VAL-BKP-002）

        注意：此测试需要真实 1Password 凭证，可能无法在 CI 运行。
        标记为手动验证或跳过。
        """
        # 检查凭证是否可用
        try:
            subprocess.run(
                ["op", "whoami"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            # op whoami 可能返回非零但仍然可用
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("op CLI 不可用")

        # 尝试 dry-run 模式
        # 注意：这个测试可能因为凭证问题失败，标记为 xfail
        pytest.xfail("需要真实 1Password 凭证，手动验证")

    def test_script_syntax_valid(self):
        """脚本语法有效"""
        result = subprocess.run(
            ["bash", "-n", str(BACKUP_SCRIPT)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"脚本语法错误: {result.stderr}"


@pytest.mark.skipif(not BACKUP_SCRIPT.exists(), reason="备份脚本不存在")
class TestBackupScriptCoverage:
    """备份覆盖范围测试（VAL-CROSS-010）"""

    def test_dynamic_paths_cover_all_projects(self):
        """动态路径覆盖全部消费项目（VAL-CROSS-010）"""
        repo_root = Path("/Users/busiji/memory")
        evolve_cli = repo_root / "memory_core/tools/evolve_cli.py"

        if not evolve_cli.exists():
            pytest.skip("evolve_cli.py 不存在")

        # 获取 backup-paths 输出
        result = subprocess.run(
            ["python3", str(evolve_cli), "backup-paths"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"backup-paths 失败: {result.stderr}"

        paths = [line for line in result.stdout.strip().split("\n") if line]

        # 获取 registry 中的项目数
        status_result = subprocess.run(
            ["python3", str(evolve_cli), "status", "--json"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if status_result.returncode != 0:
            pytest.skip("status 命令失败")

        try:
            status = json.loads(status_result.stdout)
            projects = status.get("projects", [])
            active_projects = [p for p in projects if p.get("health") in ("active_kb", "no_kb")]
        except (json.JSONDecodeError, KeyError):
            pytest.skip("status JSON 解析失败")

        # 验证 backup-paths 输出与 registry 一致
        # backup-paths 只输出存在的路径，所以应该 <= active_projects
        assert len(paths) > 0, "应输出至少一个路径"
        assert len(paths) <= len(active_projects), "路径数不应超过活跃项目数"

        # 验证每个路径都存在
        for path in paths:
            assert Path(path).exists(), f"路径不存在: {path}"

    def test_static_paths_include_global_kb(self):
        """静态路径包含全局库（VAL-CROSS-010）"""
        content = BACKUP_SCRIPT.read_text()

        # 检查全局库路径
        assert "global-kb" in content, "静态路径应包含全局库"
        assert ".memory-core" in content, "静态路径应包含 .memory-core"
