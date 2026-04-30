#!/usr/bin/env python3
"""前置分析脚本：扫描源码目录，生成交叉审查方向和审查员分配建议。

用法：
    python3 templates/analyze-for-review.py <源码目录> [--reviewers N] [--max-lines-per-reviewer L]

输出：
    1. 文件列表（按行数降序）
    2. 依赖图（import 关系）+ 入度排名
    3. 接口文件（需多人覆盖）
    4. 建议的审查员分配表
    5. 交叉审查方向
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


# ── 工具函数 ──────────────────────────────────────────────

def count_lines(filepath: Path) -> int:
    try:
        return sum(1 for _ in filepath.open(encoding="utf-8", errors="replace"))
    except Exception:
        return 0


def scan_files(source_dir: Path) -> list[tuple[Path, int]]:
    """扫描目录下所有源码文件，返回 [(相对路径, 行数)] 按行数降序。"""
    extensions = {".py", ".ts", ".js", ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".h", ".hpp"}
    skip_dirs = {".git", "__pycache__", "node_modules", "vendor", "build", "dist", ".venv", "venv"}
    results = []
    for f in sorted(source_dir.rglob("*")):
        if not f.is_file() or f.suffix not in extensions:
            continue
        parts = f.relative_to(source_dir).parts
        if any(p in skip_dirs or p.startswith(".") for p in parts):
            continue
        results.append((f.relative_to(source_dir), count_lines(f)))
    results.sort(key=lambda x: -x[1])
    return results


def build_stem_map(files: list[tuple[Path, int]], source_dir: Path) -> dict[str, str]:
    """构建 stem(文件名去后缀) → 相对路径 的映射。"""
    mapping: dict[str, str] = {}
    for rel, _ in files:
        stem = rel.stem
        if stem.startswith("_") and stem != "__init__":
            continue
        mapping[stem] = str(rel)
    return mapping


def extract_relative_imports(filepath: Path, source_dir: Path) -> list[str]:
    """提取 Python 相对/同级/绝对 import 中引用的同项目模块 stem。"""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel_path = filepath.relative_to(source_dir)
    parent = filepath.parent
    stems = set()

    # 1) from .xxx import Y — 同级模块
    for m in re.finditer(r"from\s+\.(\w[\w]*)", text):
        stems.add(m.group(1))

    # 2) from ..xxx import Y — 上级目录模块
    for m in re.finditer(r"from\s+\.\.(\w[\w]*)", text):
        stems.add(m.group(1))

    # 3) from .xxx.yyy import Z — 同级包内模块
    for m in re.finditer(r"from\s+\.([\w]+(?:\.[\w]+)*)", text):
        parts = m.group(1).split(".")
        stems.add(parts[-1])  # 取最后一个 stem

    # 4) from ..xxx.yyy import Z — 上级包内模块
    for m in re.finditer(r"from\s+\.\.([\w]+(?:\.[\w]+)*)", text):
        parts = m.group(1).split(".")
        stems.add(parts[-1])

    # 5) from workspace.tools.xxx import Y — 绝对路径项目导入
    for m in re.finditer(r"from\s+workspace\.tools(?:\.[\w]+)*\.(\w[\w]*)", text):
        stems.add(m.group(1))

    # 6) from workspace.tools import xxx
    for m in re.finditer(r"from\s+workspace\.tools\s+import\s+([\w,\s]+)", text):
        for name in m.group(1).split(","):
            name = name.strip()
            if name:
                stems.add(name)

    # 7) import xxx (同目录下的裸模块名)
    for m in re.finditer(r"(?<!from\s)\bimport\s+([\w]+)", text):
        name = m.group(1)
        if (parent / f"{name}.py").exists() or (parent / name / "__init__.py").exists():
            stems.add(name)

    return sorted(stems)


def resolve_stems(stems: list[str], stem_map: dict[str, str]) -> list[str]:
    """将 stem 列表解析为相对路径列表。"""
    resolved = []
    for stem in stems:
        if stem in stem_map:
            resolved.append(stem_map[stem])
    return sorted(set(resolved))


def build_dependency_graph(
    files: list[tuple[Path, int]],
    source_dir: Path,
    stem_map: dict[str, str],
) -> dict[str, list[str]]:
    """构建依赖图：文件 → 它 import 的同项目文件。"""
    graph: dict[str, list[str]] = {}
    for rel, _ in files:
        filepath = source_dir / rel
        stems = extract_relative_imports(filepath, source_dir)
        resolved = resolve_stems(stems, stem_map)
        graph[str(rel)] = resolved
    return graph


def compute_in_degree(graph: dict[str, list[str]]) -> dict[str, int]:
    """计算每个文件被多少其他文件 import（入度）。"""
    in_deg: dict[str, int] = defaultdict(int)
    for _, deps in graph.items():
        for dep in deps:
            in_deg[dep] += 1
    # 确保所有文件都出现
    all_files = set(graph.keys()) | {d for deps in graph.values() for d in deps}
    for f in all_files:
        in_deg.setdefault(f, 0)
    return dict(sorted(in_deg.items(), key=lambda x: -x[1]))


# ── 分配逻辑 ──────────────────────────────────────────────

def suggest_allocation(
    files: list[tuple[Path, int]],
    in_degree: dict[str, int],
    graph: dict[str, list[str]],
    num_reviewers: int,
    max_lines: int,
) -> dict:
    # 识别接口文件：入度 >= 2 或入度最高的前 3
    hub_candidates = [(f, d) for f, d in in_degree.items() if d >= 2]
    hub_candidates.sort(key=lambda x: -x[1])
    hub_files = [f for f, _ in hub_candidates]
    # 兜底：至少取入度最高的 3 个
    if len(hub_files) < 3:
        for f, _ in list(in_degree.items()):
            if f not in hub_files:
                hub_files.append(f)
            if len(hub_files) >= 3:
                break

    # 分配比例
    num_cross = max(2, num_reviewers // 5)
    num_specialist = max(1, num_reviewers // 10)
    num_primary = num_reviewers - num_cross - num_specialist

    # 贪心分配主审员（按行数均衡）
    buckets: list[list[tuple[str, int]]] = [[] for _ in range(num_primary)]
    loads = [0] * num_primary
    for rel, lines in files:
        idx = loads.index(min(loads))
        buckets[idx].append((str(rel), lines))
        loads[idx] += lines

    # 生成交叉审查方向
    cross_dirs: list[list[str]] = [[] for _ in range(num_cross)]
    for i, hub in enumerate(hub_files):
        cross_dirs[i % num_cross].append(hub)

    # 生成详细的交叉审查关系
    cross_relations: list[dict] = []
    for hub in hub_files:
        callers = sorted(f for f, deps in graph.items() if hub in deps)
        if callers:
            cross_relations.append({"hub": hub, "callers": callers})

    return {
        "hub_files": hub_files,
        "num_primary": num_primary,
        "num_cross": num_cross,
        "num_specialist": num_specialist,
        "primary": {
            f"R{i+1}": {"files": buckets[i], "total_lines": loads[i]}
            for i in range(num_primary)
        },
        "cross_dirs": cross_dirs,
        "cross_relations": cross_relations,
    }


# ── 输出 ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="审查前置分析")
    parser.add_argument("source_dir", help="源代码目录")
    parser.add_argument("--reviewers", type=int, default=10, help="审查员总数")
    parser.add_argument("--max-lines", type=int, default=1500, help="每人最大行数")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.is_dir():
        print(f"错误：{source_dir} 不是目录", file=sys.stderr)
        sys.exit(1)

    sep = "=" * 60

    # 1. 文件扫描
    files = scan_files(source_dir)
    total_lines = sum(l for _, l in files)

    print(sep)
    print("代码审查前置分析")
    print(sep)
    print(f"\n源文件：{len(files)} 个，共 {total_lines} 行\n")
    print(f"{'文件':<55} {'行数':>6}")
    print("-" * 63)
    for rel, lines in files:
        print(f"{str(rel):<55} {lines:>6}")

    # 2. 依赖分析
    stem_map = build_stem_map(files, source_dir)
    graph = build_dependency_graph(files, source_dir, stem_map)
    in_degree = compute_in_degree(graph)

    print(f"\n依赖图（入度排名）\n")
    print(f"{'文件':<55} {'入度':>6}")
    print("-" * 63)
    for f, deg in in_degree.items():
        print(f"{f:<55} {deg:>6}")

    print(f"\n依赖详情（出度 > 0 的文件）\n")
    for f, deps in sorted(graph.items()):
        if deps:
            print(f"  {f} → {', '.join(deps)}")

    # 3. 分配
    alloc = suggest_allocation(files, in_degree, graph, args.reviewers, args.max_lines)

    print(f"\n接口文件（需多人覆盖）：")
    for f in alloc["hub_files"]:
        deg = in_degree.get(f, 0)
        print(f"  • {f}  (入度 {deg})")

    print(f"\n分配建议（{args.reviewers} 审查员）")
    print(f"  主审员：{alloc['num_primary']} 人")
    print(f"  交叉审查员：{alloc['num_cross']} 人")
    print(f"  专项审查员：{alloc['num_specialist']} 人")

    print("\n── 第一层：主审员 ──")
    for rid, info in alloc["primary"].items():
        flist = ", ".join(f"{f}({l})" for f, l in info["files"])
        print(f"  {rid} [{info['total_lines']} 行]: {flist}")

    print("\n── 第二层：交叉审查员 ──")
    for i, dirs in enumerate(alloc["cross_dirs"]):
        rid = f"R{alloc['num_primary'] + i + 1}"
        if dirs:
            print(f"  {rid}: {', '.join(dirs)}")
        else:
            print(f"  {rid}: (待分配)")

    n_specialist_start = alloc["num_primary"] + alloc["num_cross"]
    print("\n── 第三层：专项审查员 ──")
    specialties = ["安全 + 并发", "崩溃链路"]
    for i in range(alloc["num_specialist"]):
        rid = f"R{n_specialist_start + i + 1}"
        print(f"  {rid}: {specialties[i % len(specialties)]}")

    print("\n── 交叉审查具体方向 ──")
    for i, rel in enumerate(alloc["cross_relations"]):
        rid = f"R{alloc['num_primary'] + (i % alloc['num_cross']) + 1}"
        callers = ", ".join(rel["callers"])
        print(f"  {rid}: {callers} → {rel['hub']}")

    print(f"\n── 模板变量 ──")
    print(f"__SOURCE_DIR__    = {source_dir}")
    print(f"__TOTAL_FILES__   = {len(files)}")
    print(f"__TOTAL_LINES__   = {total_lines}")
    print(f"__HUB_FILES__     = {', '.join(alloc['hub_files'])}")
    print(f"\n完成。将输出填入 templates/code-review-template.md 即可。")


if __name__ == "__main__":
    main()
