"""Runner 工具链契约测试（memory-core 侧）

memory-core 与 infra-core 共享宿主工具池（runner-tools.toml 归 infra-core 管理），
本测试仅验证 memory-core CI 对宿主工具池的消费行为（2026-08-28 runner-hardening）。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


class TestMemoryCoreCICacheIntegration:
    """memory-core setup-venv 对共享缓存目录的集成"""

    def test_setup_venv_exports_cache_dirs(self):
        """setup-venv 必须导出 UV_CACHE_DIR/PIP_CACHE_DIR（共享池）"""
        content = _read(".github/actions/setup-venv/action.yml")

        assert "UV_CACHE_DIR=/var/cache/uv" in content or 'UV_CACHE_DIR="/var/cache/uv"' in content
        assert "PIP_CACHE_DIR=/var/cache/pip" in content or 'PIP_CACHE_DIR="/var/cache/pip"' in content
        assert "UV_CACHE_DIR=$UV_CACHE_DIR" in content
        assert "PIP_CACHE_DIR=$PIP_CACHE_DIR" in content

    def test_setup_venv_preserves_per_run_venv_isolation(self):
        """setup-venv 必须保持 per-run venv 隔离（护栏铁律）"""
        content = _read(".github/actions/setup-venv/action.yml")
        assert "venv-${RUN_ID}-${RUN_ATTEMPT}" in content


class TestMemoryCoreCIHostPriority:
    """memory-core CI 工具调用必须走宿主优先"""

    def test_ci_shellcheck_host_priority(self):
        """test job 的 shellcheck 必须优先用宿主预装"""
        content = _read(".github/workflows/ci.yml")
        assert "command -v shellcheck" in content
        assert "::warning::shellcheck not found on host" in content

    def test_ci_actionlint_host_priority(self):
        """test job 的 actionlint 必须优先用宿主预装"""
        content = _read(".github/workflows/ci.yml")
        assert "command -v actionlint" in content
        assert "::warning::actionlint not found on host" in content

    def test_ci_no_unconditional_tool_download(self):
        """CI 不得无条件下载工具（必须走宿主优先逻辑）"""
        content = _read(".github/workflows/ci.yml")
        # 不应存在裸的 bash <(curl ...download-actionlint.bash) 模式
        # （infra-core 旧 actionlint job 的 every-run curl 正是本 issue 要消除的故障模式）
        assert "bash <(curl" not in content, "CI 不应存在无条件下载的 bash <(curl ...) 模式"


class TestVersionConsistency:
    """memory-core fallback 版本必须与 infra-core runner-tools.toml 一致"""

    def test_fallback_versions_match_infra_core(self):
        """fallback 下载版本必须对齐 infra-core runner-tools.toml"""
        from pathlib import Path

        infra_root = Path(__file__).resolve().parent.parent.parent / "infra-core"
        if not infra_root.exists():
            import pytest

            pytest.skip(f"infra-core 不可达：{infra_root}")

        import tomllib

        manifest = (infra_root / "runner-tools.toml").read_text(encoding="utf-8")
        data = tomllib.loads(manifest)

        ci = _read(".github/workflows/ci.yml")
        # shellcheck fallback
        import re

        sc = re.search(r"shellcheck/releases/download/v([\d.]+)/", ci)
        assert sc, "未找到 shellcheck fallback URL"
        assert sc.group(1) == data["tools"]["shellcheck"], (
            f"memory-core shellcheck fallback={sc.group(1)}, infra-core pinned={data['tools']['shellcheck']}"
        )
        # actionlint fallback
        al = re.search(r"actionlint/releases/download/v([\d.]+)/", ci)
        assert al, "未找到 actionlint fallback URL"
        assert al.group(1) == data["tools"]["actionlint"], (
            f"memory-core actionlint fallback={al.group(1)}, infra-core pinned={data['tools']['actionlint']}"
        )
