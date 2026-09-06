"""
沉淀写入器：置信度分层路由 + 去重三态 + git 纪律 + gk-ensure

架构 §3.6：
- confidence >= auto_confidence_threshold → <domain>/<slug>.md + INDEX.md 更新
- confidence < threshold 或 unrefined → pending/<slug>.md
- 去重三态（D10）：
  1. 归一化指纹相等 → 跳过
  2. n-gram 重叠 > 0.6 → 合并（追加 source_refs，保留原文）
  3. slug 相同但重叠 ≤ 0.6 → 后缀避让新建
- gk-ensure：全局库分支归位（D8）
- git 纪律（D7）：非 git root 自动 init、每轮单次中文提交、零写入不提交、
  auto_commit=false 只写不提交、push=true 尽力推送失败仅告警、push=false 零尝试
"""

import hashlib
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

# 全局域列表
VALID_DOMAINS = ("operations", "engineering", "collaboration", "governance", "infra", "audit")


# ---------------------------------------------------------------------------
# 归一化指纹与 n-gram 重叠
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """归一化文本：小写 + 去全部空白（用于精确指纹）"""
    return "".join(text.lower().split())


def _normalize_fingerprint(content: str) -> str:
    """归一化指纹（小写 + 去全部空白）"""
    return _normalize_text(content)


def _strip_frontmatter(content: str) -> str:
    """去掉 YAML frontmatter，只保留正文"""
    m = re.match(r"^---\n.*?\n---\n?", content, flags=re.DOTALL)
    if m:
        return content[m.end() :]
    return content


def _body_fingerprint(content: str) -> str:
    """正文归一化指纹（去掉 frontmatter 后归一化）"""
    body = _strip_frontmatter(content)
    return _normalize_text(body)


def _get_bigrams(text: str, n: int = 2) -> list[str]:
    """提取字符级 n-gram"""
    text = _normalize_text(text)
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def _ngram_overlap(text_a: str, text_b: str, n: int = 2) -> float:
    """
    计算两段文本的 n-gram 重叠度（Jaccard 变体：交集 / 并集）

    返回 0.0-1.0 之间的重叠度
    """
    a_norm = _normalize_text(text_a)
    b_norm = _normalize_text(text_b)

    if not a_norm and not b_norm:
        return 1.0  # 两个空文本视为完全重叠
    if not a_norm or not b_norm:
        return 0.0

    bigrams_a = set(_get_bigrams(a_norm, n))
    bigrams_b = set(_get_bigrams(b_norm, n))

    if not bigrams_a and not bigrams_b:
        return 1.0
    if not bigrams_a or not bigrams_b:
        return 0.0

    intersection = bigrams_a & bigrams_b
    union = bigrams_a | bigrams_b
    return len(intersection) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# Slug 生成
# ---------------------------------------------------------------------------


def _generate_slug(title: str) -> str:
    """
    生成 slug（架构 §3.6）

    中文标题保留，英文小写连字符，冲突由调用方加短哈希后缀
    """
    # 保留中文字符
    if any("\u4e00" <= c <= "\u9fff" for c in title):
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title, flags=re.UNICODE)
    else:
        slug = re.sub(r"[^\w]+", "-", title.lower(), flags=re.UNICODE)

    slug = slug.strip("-")
    return slug or "untitled"


def _short_hash(content: str) -> str:
    """短哈希后缀（用于 slug 冲突避让）"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Frontmatter 生成
# ---------------------------------------------------------------------------


def _generate_frontmatter(
    title: str,
    domain: str,
    confidence: float,
    source_refs: list[dict[str, str]],
    unrefined: bool,
    extra: dict[str, Any] | None = None,
) -> str:
    """生成 YAML frontmatter"""
    lines = ["---"]
    lines.append(f'title: "{title}"')
    lines.append(f"domain: {domain}")
    lines.append(f"confidence: {confidence}")
    lines.append(f"created_at: {date.today().isoformat()}")
    lines.append("source: memory-evolve")

    if unrefined:
        lines.append("unrefined: true")

    # source_refs
    if source_refs:
        lines.append("source_refs:")
        for ref in source_refs:
            lines.append(f'  - project: "{ref.get("project", "")}"')
            lines.append(f'    path: "{ref.get("path", "")}"')

    if extra:
        for k, v in extra.items():
            lines.append(f"{k}: {v}")

    lines.append("---")
    return "\n".join(lines)


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    解析 frontmatter，返回 (frontmatter_dict, body)

    如果无 frontmatter，返回 ({}, content)
    """
    m = re.match(r"^---\n(.*?)\n---\n?", content, flags=re.DOTALL)
    if not m:
        return {}, content

    fm_text = m.group(1)
    body = content[m.end() :]
    fm: dict[str, Any] = {}

    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value:
            # 尝试解析数值
            try:
                fm[key] = float(value) if "." in value else int(value)
            except ValueError:
                fm[key] = value

    return fm, body


def _parse_source_refs_from_content(content: str) -> list[dict[str, str]]:
    """从 frontmatter 原文解析 source_refs 列表"""
    refs: list[dict[str, str]] = []
    m = re.match(r"^---\n(.*?)\n---\n?", content, flags=re.DOTALL)
    if not m:
        return refs

    fm_text = m.group(1)
    in_source_refs = False
    current_project = ""
    current_path = ""

    for line in fm_text.split("\n"):
        stripped = line.strip()
        if stripped == "source_refs:":
            in_source_refs = True
            continue
        if in_source_refs:
            if stripped.startswith("- project:"):
                if current_project or current_path:
                    refs.append({"project": current_project, "path": current_path})
                current_project = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                current_path = ""
            elif stripped.startswith("path:"):
                current_path = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            elif not stripped.startswith("-") and ":" in stripped:
                # 新字段，结束 source_refs
                if current_project or current_path:
                    refs.append({"project": current_project, "path": current_path})
                in_source_refs = False
                current_project = ""
                current_path = ""

    # 最后一组
    if in_source_refs and (current_project or current_path):
        refs.append({"project": current_project, "path": current_path})

    return refs


# ---------------------------------------------------------------------------
# INDEX.md 操作
# ---------------------------------------------------------------------------


def _ensure_index(global_kb_root: Path) -> Path:
    """确保 INDEX.md 存在并返回其路径"""
    index_path = global_kb_root / "INDEX.md"
    if not index_path.exists():
        header = "# INDEX\n\n| 标题 | 域 | 文件 |\n|------|----|------|\n"
        index_path.write_text(header, encoding="utf-8")
    return index_path


def _index_has_entry(index_path: Path, file_rel: str) -> bool:
    """检查 INDEX.md 是否已包含某文件的行"""
    if not index_path.exists():
        return False
    try:
        content = index_path.read_text(encoding="utf-8")
        return file_rel in content
    except OSError:
        return False


def _add_index_entry(index_path: Path, title: str, domain: str, file_rel: str) -> None:
    """向 INDEX.md 追加一行"""
    if _index_has_entry(index_path, file_rel):
        return  # 幂等

    try:
        content = index_path.read_text(encoding="utf-8")
        new_line = f"| {title} | {domain} | {file_rel} |\n"
        if not content.endswith("\n"):
            content += "\n"
        content += new_line
        index_path.write_text(content, encoding="utf-8")
    except OSError as e:
        print(f"Warning: Cannot update INDEX.md: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 去重三态核心
# ---------------------------------------------------------------------------


def _scan_existing_files(directory: Path) -> list[dict[str, Any]]:
    """扫描目录下的全部 .md 文件，返回带指纹信息的列表"""
    results: list[dict[str, Any]] = []
    if not directory.exists():
        return results

    for md_file in directory.rglob("*.md"):
        if md_file.name == "INDEX.md":
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            fp = _body_fingerprint(content)
            results.append(
                {
                    "path": md_file,
                    "fingerprint": fp,
                    "content": content,
                }
            )
        except OSError:
            pass
    return results


def _find_dedup_target(
    new_body: str,
    target_dir: Path,
    slug: str,
) -> tuple[str, dict[str, Any] | None]:
    """
    在目标目录下查找去重目标（D10 三态判定）

    Returns:
        (action, existing_info)
        action: "skip" / "merge" / "suffix_new" / "new"
        existing_info: 匹配到的已有文件信息（skip/merge 时非 None）
    """
    new_fp = _normalize_text(new_body)
    existing_files = _scan_existing_files(target_dir)

    # 1. 精确指纹匹配 → skip
    for ef in existing_files:
        if ef["fingerprint"] == new_fp:
            return "skip", ef

    # 2. n-gram 重叠 > 0.6 → merge
    for ef in existing_files:
        overlap = _ngram_overlap(new_body, _strip_frontmatter(ef["content"]))
        if overlap > 0.6:
            return "merge", ef

    # 3. slug 相同但重叠 ≤ 0.6 → suffix_new
    for ef in existing_files:
        if ef["path"].stem == slug:
            return "suffix_new", ef

    # 4. 全新
    return "new", None


def _merge_source_refs(existing_path: Path, new_source_refs: list[dict[str, str]]) -> None:
    """
    合并追加 source_refs 到已有文件（保留原文全部）

    在文件末尾追加 ## Sources 区（或在已有 Sources 区去重追加）
    FIX: 重复合并时去重——先剥离已有 ## Sources 区再重写，避免重复行/重复区段
    """
    try:
        content = existing_path.read_text(encoding="utf-8")
    except OSError:
        return

    # 解析已有 source_refs（从 frontmatter）
    existing_refs = _parse_source_refs_from_content(content)
    existing_keys = {(r["project"], r["path"]) for r in existing_refs}

    # 也收集正文 ## Sources 区里已有的引用（避免与 frontmatter 重复）
    body_sources = _parse_body_sources(content)
    for ref in body_sources:
        key = (ref.get("project", ""), ref.get("path", ""))
        if key not in existing_keys:
            existing_keys.add(key)
            existing_refs.append(ref)

    # 追加新的（去重）
    added = False
    for ref in new_source_refs:
        key = (ref.get("project", ""), ref.get("path", ""))
        if key not in existing_keys:
            existing_keys.add(key)
            existing_refs.append(ref)
            added = True

    if not added:
        return  # 无新增引用

    # 剥离已有的 ## Sources 区（避免重复区段）
    body = _strip_existing_sources_section(content)

    # 重写完整的 ## Sources 区
    sources_lines = ["\n\n## Sources\n"]
    for ref in existing_refs:
        sources_lines.append(f"- project: {ref['project']}\n")
        sources_lines.append(f"  path: {ref['path']}\n")

    new_content = body.rstrip() + "".join(sources_lines)
    try:
        existing_path.write_text(new_content, encoding="utf-8")
    except OSError as e:
        print(f"Warning: Cannot merge source_refs to {existing_path}: {e}", file=sys.stderr)


def _strip_existing_sources_section(content: str) -> str:
    """剥离正文中已有的 ## Sources 区段（从 `## Sources` 到下一个 `## ` 或文件末尾）"""
    # 查找 ## Sources 起始位置
    pattern = re.compile(r"^## Sources\s*$", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return content

    start = match.start()
    # 查找下一个 ## 标题（作为 Sources 区段结束）
    next_heading = re.search(r"^## ", content[match.end() :], re.MULTILINE)
    if next_heading:
        end = match.end() + next_heading.start()
        return content[:start] + content[end:]
    else:
        return content[:start]


def _parse_body_sources(content: str) -> list[dict[str, str]]:
    """从正文 ## Sources 区解析已有的 source 引用"""
    refs: list[dict[str, str]] = []
    pattern = re.compile(r"^## Sources\s*$", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return refs

    # 提取 Sources 区段（到下一个 ## 或文件末尾）
    start = match.end()
    next_heading = re.search(r"^## ", content[start:], re.MULTILINE)
    section = content[start : start + next_heading.start()] if next_heading else content[start:]

    # 解析 - project: xxx / path: yyy 格式
    current_project = ""
    current_path = ""
    for line in section.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- project:"):
            if current_project or current_path:
                refs.append({"project": current_project, "path": current_path})
            current_project = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            current_path = ""
        elif stripped.startswith("path:"):
            current_path = stripped.split(":", 1)[1].strip().strip('"').strip("'")

    if current_project or current_path:
        refs.append({"project": current_project, "path": current_path})

    return refs


# ---------------------------------------------------------------------------
# 候选路由与写入
# ---------------------------------------------------------------------------


def _route_candidate(
    cand: dict[str, Any],
    global_kb_root: Path,
    threshold: float,
) -> dict[str, Any]:
    """
    路由单个候选到目标域并写入

    Returns:
        {"action": "skip"/"merge"/"written"/"none", "path": Path|None, ...}
    """
    title = cand.get("title", "untitled")
    content = cand.get("content", "")
    domain = cand.get("domain", "engineering")
    confidence = cand.get("confidence", 0.0)
    source_refs = cand.get("source_refs", [])
    unrefined = cand.get("unrefined", True)

    # 确定目标目录
    if unrefined or confidence < threshold:
        target_dir = global_kb_root / "pending"
        is_formal = False
    else:
        target_dir = global_kb_root / domain
        is_formal = True

    target_dir.mkdir(parents=True, exist_ok=True)

    # 生成 slug
    slug = _generate_slug(title)

    # 去重三态判定
    action, existing_info = _find_dedup_target(content, target_dir, slug)

    if action == "skip":
        return {"action": "skip", "path": existing_info["path"] if existing_info else None}

    if action == "merge":
        assert existing_info is not None
        _merge_source_refs(existing_info["path"], source_refs)
        return {"action": "merge", "path": existing_info["path"]}

    if action == "suffix_new":
        # 加短哈希后缀
        suffix = _short_hash(content)
        file_name = f"{slug}-{suffix}.md"
    else:
        file_name = f"{slug}.md"

    target_path = target_dir / file_name

    # 如果文件仍存在（理论上不应该，防御性检查）
    if target_path.exists():
        suffix = _short_hash(content + datetime.now().isoformat())
        file_name = f"{slug}-{suffix}.md"
        target_path = target_dir / file_name

    # 生成文件内容
    frontmatter = _generate_frontmatter(
        title=title,
        domain=domain,
        confidence=confidence,
        source_refs=source_refs,
        unrefined=unrefined,
    )
    file_content = f"{frontmatter}\n\n{content}\n"

    try:
        target_path.write_text(file_content, encoding="utf-8")
    except OSError as e:
        print(f"Warning: Failed to write {target_path}: {e}", file=sys.stderr)
        return {"action": "error", "path": None}

    # 更新 INDEX（仅正式域）
    if is_formal:
        index_path = _ensure_index(global_kb_root)
        file_rel = f"{domain}/{file_name}"
        _add_index_entry(index_path, title, domain, file_rel)

    return {"action": "written", "path": target_path}


def write_candidates(
    candidates: list[dict[str, Any]],
    global_kb_root: Path,
    config: dict[str, Any] | None = None,
) -> dict[str, int]:
    """
    写入候选列表到全局库（统一入口）

    Args:
        candidates: 候选列表
        global_kb_root: 全局库根路径
        config: 配置

    Returns:
        统计：{written, skipped_duplicate, merged}
    """
    config = config or {}
    threshold = config.get("promote", {}).get("auto_confidence_threshold", 0.8)

    stats = {"written": 0, "skipped_duplicate": 0, "merged": 0}

    for cand in candidates:
        result = _route_candidate(cand, global_kb_root, threshold)
        action = result["action"]
        if action == "skip":
            stats["skipped_duplicate"] += 1
        elif action == "merge":
            stats["merged"] += 1
        elif action == "written":
            stats["written"] += 1

    return stats


def write_unrefined_candidates(
    candidates: list[dict[str, Any]],
    global_kb_root: Path,
    config: dict[str, Any] | None = None,
) -> dict[str, int]:
    """
    写入 unrefined 候选到 pending/（向后兼容入口）

    所有候选标记 unrefined=True，一律进 pending/
    """
    # 确保全部标记 unrefined
    for cand in candidates:
        cand["unrefined"] = True
    return write_candidates(candidates, global_kb_root, config)


# ---------------------------------------------------------------------------
# gk-ensure：全局库分支归位（D8）
# ---------------------------------------------------------------------------


def _is_git_repo(path: Path) -> bool:
    """检查是否为 git 仓库"""
    return (path / ".git").exists()


def _git_run(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    """运行 git 命令"""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _is_worktree_clean(cwd: Path) -> bool:
    """检查工作区是否干净"""
    try:
        result = _git_run(["status", "--porcelain"], cwd, check=True)
        return not result.stdout.strip()
    except subprocess.CalledProcessError:
        return False


def _has_branch(cwd: Path, branch: str) -> bool:
    """检查是否存在指定分支"""
    try:
        result = _git_run(["branch", "--list", branch], cwd, check=True)
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def _current_branch(cwd: Path) -> str | None:
    """获取当前分支名"""
    try:
        result = _git_run(["branch", "--show-current"], cwd, check=True)
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def gk_ensure(global_kb_root: Path) -> tuple[int, str]:
    """
    全局库 git 归位（D8）

    - 无 fix/audit-round2 分支 → no-op, exit 0（幂等）
    - 有 fix/audit-round2 → 合并到 main
    - 工作区脏 → exit 1，不动现场，不 stash
    - 非 git 仓库 → exit 0

    Returns:
        (exit_code, message)
    """
    if not _is_git_repo(global_kb_root):
        return 0, "not a git repo, no-op"

    current = _current_branch(global_kb_root)

    # 检查 fix/audit-round2 分支
    if not _has_branch(global_kb_root, "fix/audit-round2"):
        return 0, "no fix/audit-round2 branch, already on main (D8 no-op)"

    # 检查 main 分支
    has_main = _has_branch(global_kb_root, "main")

    # 检查脏工作区
    if not _is_worktree_clean(global_kb_root):
        return 1, "dirty worktree, aborting (no stash, preserving state)"

    # 如果当前在 fix/audit-round2 且 main 存在
    if current == "fix/audit-round2" and has_main:
        # 切到 main
        try:
            _git_run(["checkout", "main"], global_kb_root)
            # 合并 fix/audit-round2
            _git_run(["merge", "--no-edit", "fix/audit-round2"], global_kb_root)
            return 0, "merged fix/audit-round2 into main"
        except subprocess.CalledProcessError as e:
            return 1, f"merge failed: {e.stderr}"

    if current == "fix/audit-round2" and not has_main:
        # main 不存在，重命名分支
        try:
            _git_run(["branch", "-m", "fix/audit-round2", "main"], global_kb_root)
            return 0, "renamed fix/audit-round2 to main"
        except subprocess.CalledProcessError as e:
            return 1, f"rename failed: {e.stderr}"

    if current == "main":
        # 已在 main，检查是否需要合并
        try:
            _git_run(["merge", "--no-edit", "fix/audit-round2"], global_kb_root)
            return 0, "merged fix/audit-round2 into main"
        except subprocess.CalledProcessError as e:
            return 1, f"merge failed: {e.stderr}"

    # 其他分支 → 先切 main 再合并
    if has_main:
        try:
            _git_run(["checkout", "main"], global_kb_root)
            _git_run(["merge", "--no-edit", "fix/audit-round2"], global_kb_root)
            return 0, "merged fix/audit-round2 into main"
        except subprocess.CalledProcessError as e:
            return 1, f"merge failed: {e.stderr}"

    return 0, "already resolved"


# ---------------------------------------------------------------------------
# Git 纪律（D7）
# ---------------------------------------------------------------------------


def _ensure_git_repo(global_kb_root: Path) -> bool:
    """确保全局库是 git 仓库（D7：非 git root 自动 init）"""
    if _is_git_repo(global_kb_root):
        return True

    try:
        _git_run(["init", "-b", "main"], global_kb_root)
        # 配置用户信息（使用环境既有身份）
        # 不覆盖既有配置，只在未配置时设置
        result = _git_run(["config", "user.name"], global_kb_root, check=False)
        if result.returncode != 0:
            _git_run(["config", "user.name", "memory-evolve"], global_kb_root, check=False)
        result = _git_run(["config", "user.email"], global_kb_root, check=False)
        if result.returncode != 0:
            _git_run(["config", "user.email", "evolve@memory.local"], global_kb_root, check=False)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Warning: git init failed: {e}", file=sys.stderr)
        return False


def git_commit_if_needed(
    global_kb_root: Path,
    config: dict[str, Any] | None = None,
    summary: str | None = None,
) -> bool:
    """
    如果有变更则 git commit（中文信息）

    Args:
        global_kb_root: 全局库根路径
        config: 配置（git 段）
        summary: 可选的提交摘要

    Returns:
        是否产生了新提交
    """
    config = config or {}
    git_config = config.get("git", {})
    auto_commit = git_config.get("auto_commit", True)
    do_push = git_config.get("push", True)

    if not auto_commit:
        return False

    # 确保是 git 仓库（D7）
    if not _ensure_git_repo(global_kb_root):
        return False

    # 检查是否有变更
    try:
        result = _git_run(["status", "--porcelain"], global_kb_root)
        if not result.stdout.strip():
            return False  # 无变更，不提交

        # 统计新增文件数（用于提交信息）
        new_files = [line for line in result.stdout.split("\n") if line.startswith("??")]
        modified_files = [line for line in result.stdout.split("\n") if line.startswith(" M") or line.startswith("M ")]
        count = len(new_files) + len(modified_files)
        if count == 0:
            count = 1

        # 添加并提交
        _git_run(["add", "-A"], global_kb_root)

        commit_msg = summary or f"feat(evolve): 沉淀 {count} 条经验（{date.today().isoformat()}）"

        _git_run(["commit", "-m", commit_msg], global_kb_root)

        # 推送（push=true 时尽力推送，失败仅告警）
        if do_push:
            _try_push(global_kb_root)

        return True

    except subprocess.CalledProcessError as e:
        print(f"Warning: git commit failed: {e}", file=sys.stderr)
        return False


def _try_push(global_kb_root: Path) -> None:
    """尽力推送，失败仅 stderr 告警"""
    # 检查是否有远端
    try:
        result = _git_run(["remote"], global_kb_root, check=False)
        if not result.stdout.strip():
            return  # 无远端，不推送（不告警）

        push_result = _git_run(["push"], global_kb_root, check=False)
        if push_result.returncode != 0:
            print("Warning: git push failed (推送失败仅告警)", file=sys.stderr)
    except subprocess.CalledProcessError:
        print("Warning: git push failed (推送失败仅告警)", file=sys.stderr)
