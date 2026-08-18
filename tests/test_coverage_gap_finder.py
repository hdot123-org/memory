"""coverage_gap_finder.py 的 --xml-path 与产物清理契约测试。

背景（2026-08-19）：qa.yml coverage-audit job 原先让 gap finder 内部单线程
再跑一遍全量 pytest（pve 上 268s），与随后的 -n 6 pytest 重复。改造后
workflow 先跑 pytest 产出 coverage.xml，gap finder 用 --xml-path 复用解析。
本文件锁定三个契约：
1. --xml-path 解析外部 XML 且不删除该文件（后续 upload step 依赖它）
2. 无 --xml-path 时自生成的 coverage_gap.xml 正常清理
3. xdist 可用时 pytest 参数注入 -n auto，不可用时回退单线程
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from tests.script_module_helpers import load_script_module

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "qa" / "coverage_gap_finder.py"

COVERAGE_XML = textwrap.dedent("""\
    <?xml version="1.0" ?>
    <coverage version="7.6.1" timestamp="1" line-rate="0.6" branch-rate="0.5" lines-covered="6" lines-valid="10">
      <sources><source>.</source></sources>
      <packages>
        <package name="memory_core" line-rate="0.6" branch-rate="0.5" complexity="0">
          <classes>
            <class name="memory_hook_gateway" filename="memory_core/memory_hook_gateway.py" line-rate="1.0" branch-rate="1.0" complexity="0">
              <methods/>
              <lines>
                <line number="1" hits="1"/>
                <line number="2" hits="1"/>
              </lines>
            </class>
            <class name="version_sync" filename="memory_core/version_sync.py" line-rate="0.0" branch-rate="0.0" complexity="0">
              <methods/>
              <lines>
                <line number="1" hits="0"/>
                <line number="2" hits="0"/>
                <line number="3" hits="0"/>
              </lines>
            </class>
            <class name="Ignored" filename="tests/__pycache__/test_x.cpython-312.pyc" line-rate="1.0" branch-rate="1.0" complexity="0">
              <methods/>
              <lines>
                <line number="1" hits="1"/>
              </lines>
            </class>
          </classes>
        </package>
      </packages>
    </coverage>
""")


@pytest.fixture
def mod():
    """加载被测脚本（exec 前注册进 sys.modules，dataclass 需要 __module__ 可解析）。"""
    return load_script_module(SCRIPT_PATH, "coverage_gap_finder_under_test")


def _write_xml(tmp_path: Path, name: str = "coverage.xml") -> Path:
    xml_path = tmp_path / name
    xml_path.write_text(COVERAGE_XML, encoding="utf-8")
    return xml_path


class TestXmlPathParsing:
    """--xml-path：解析外部 XML、产出报告、绝不删除外部文件。"""

    def test_xml_path_parses_and_keeps_file(self, tmp_path, capsys, monkeypatch, mod):
        xml = _write_xml(tmp_path)
        json_out = tmp_path / "gap.json"

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", [
            "coverage_gap_finder.py",
            "--target", "80",
            "--xml-path", str(xml),
            "--json", str(json_out),
        ])
        code = mod.main()

        # 目标 80% vs 实际 2/5 行覆盖 → 退出码 1（报告性质，脚本约定）
        assert code == 1
        # 契约 1：外部 XML 必须保留（upload step 还要上传它）
        assert xml.exists()
        # 自生成的 coverage_gap.xml 不应出现
        assert not (tmp_path / "coverage_gap.xml").exists()
        # JSON 报告已产出且包含核心模块统计
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["module_count"] == 2  # __pycache__ 条目被过滤
        assert data["covered_lines"] == 2
        assert data["missed_lines"] == 3
        out = capsys.readouterr().out
        assert "Coverage Gap Analysis Report" in out

    def test_xml_path_missing_file_fails_fast(self, tmp_path, capsys, monkeypatch, mod):
        monkeypatch.chdir(tmp_path)
        missing = tmp_path / "nope.xml"
        monkeypatch.setattr(sys, "argv", [
            "coverage_gap_finder.py", "--target", "80", "--xml-path", str(missing),
        ])
        code = mod.main()
        assert code == 1
        assert "nope.xml" in capsys.readouterr().out

    def test_parse_skips_dunder_and_pycache(self, tmp_path, mod):
        xml = _write_xml(tmp_path)
        modules = mod.parse_coverage_xml(xml)
        names = {m.name for m in modules}
        # CORE_MODULES 中 memory_hook_gateway / version_sync 均在；pycache 条目被过滤
        assert names == {"memory_hook_gateway", "version_sync"}


class TestSelfGeneratedXmlCleanup:
    """无 --xml-path：自生成 coverage_gap.xml 用后清理。"""

    def test_self_generated_xml_cleaned_when_target_met(self, tmp_path, capsys, monkeypatch, mod):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "coverage_gap.xml").write_text(COVERAGE_XML, encoding="utf-8")

        calls = []

        def fake_run_coverage():
            calls.append(1)
            return Path("coverage_gap.xml")  # 复用预置文件模拟已生成

        monkeypatch.setattr(mod, "run_coverage", fake_run_coverage)
        monkeypatch.setattr(sys, "argv", ["coverage_gap_finder.py", "--target", "0"])
        # target 0 → overall 40% ≥ 0 → 退出码 0，走清理分支
        code = mod.main()
        capsys.readouterr()
        assert code == 0
        assert not (tmp_path / "coverage_gap.xml").exists()


class TestXdistArgs:
    """xdist 参数注入：可用时 -n auto，不可用时单线程回退。"""

    def test_xdist_args_type(self, mod):
        args = mod._pytest_xdist_args()
        # CI 与本地均安装 pytest-xdist → 非空且为 -n auto；否则空列表
        assert args in ([], ["-n", "auto"])

    def test_run_coverage_cmd_includes_auto_when_xdist_present(self, tmp_path, monkeypatch, mod):
        recorded = {}

        def fake_subprocess_run(cmd, **kwargs):
            recorded["cmd"] = cmd
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(mod.subprocess, "run", fake_subprocess_run)
        monkeypatch.chdir(tmp_path)
        mod.run_coverage()
        cmd = recorded["cmd"]
        assert cmd[0] == sys.executable
        assert "-m" in cmd and "pytest" in cmd
        if mod._pytest_xdist_args():
            assert "-n" in cmd and "auto" in cmd
        assert "--cov-report=xml:coverage_gap.xml" in cmd
