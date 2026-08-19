"""Tests for scripts/qa/coverage_gap_finder.py (PR: editable-install filename 兼容).

2026-08-19 事故：自建 runner（editable install）下 coverage XML 的 class filename
无 memory_core/ 前缀（如 "tools/doc_router.py"），旧过滤 `startswith("memory_core/")`
拒绝全部 class → "no modules found in coverage XML" → gap json 不产出。
回归测试：两种 filename 形式都必须被解析。
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "qa" / "coverage_gap_finder.py"


def _load_module():
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    try:
        import coverage_gap_finder as mod  # noqa: PLC0415
        return mod
    finally:
        sys.path.pop(0)


def _write_xml(tmp_path: Path, filenames: list[str]) -> Path:
    """构造最小 coverage XML：每个 filename 一个 class 节点。"""
    root = ET.Element("coverage", {"line-rate": "0.5", "branch-rate": "0.4", "version": "7"})
    pkg = ET.SubElement(root, "packages")
    p = ET.SubElement(pkg, "package", {"name": "memory_core", "line-rate": "0.5", "branch-rate": "0.4"})
    cls_elem = ET.SubElement(p, "classes")
    for fn in filenames:
        c = ET.SubElement(cls_elem, "class", {
            "filename": fn, "name": Path(fn).stem,
            "line-rate": "0.5", "branch-rate": "0.4", "complexity": "1",
        })
        for lineno, hits in ((1, "1"), (2, "0")):
            ET.SubElement(c, "line", {"number": str(lineno), "hits": hits, "branch": "False"})
    out = tmp_path / "coverage_gap.xml"
    ET.ElementTree(root).write(out, encoding="unicode")
    return out


def test_parse_accepts_prefixed_filenames(tmp_path):
    """传统形式（memory_core/ 前缀）必须解析出模块。"""
    mod = _load_module()
    xml = _write_xml(tmp_path, ["memory_core/ownership.py"])
    modules = mod.parse_coverage_xml(xml)
    assert [m.name for m in modules] == ["ownership"]


def test_parse_accepts_editable_install_relative_filenames(tmp_path):
    """editable install 形式（无 memory_core/ 前缀）必须解析出模块。

    2026-08-19 回归：自建 runner 上 gap json 不产出的根因。
    """
    mod = _load_module()
    xml = _write_xml(tmp_path, ["ownership.py", "tools/doc_router.py"])
    names = sorted(m.name for m in mod.parse_coverage_xml(xml))
    assert names == ["doc_router", "ownership"]


def test_parse_rejects_non_package_files(tmp_path):
    """tests/ 与 scripts/ 文件不得混入（editable 形式下前缀匹配的误吞风险）。"""
    mod = _load_module()
    xml = _write_xml(tmp_path, ["tests/test_x.py", "scripts/run.py", "memory_core/ownership.py"])
    names = [m.name for m in mod.parse_coverage_xml(xml)]
    assert names == ["ownership"]
