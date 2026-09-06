"""
沉淀写入器：unrefined 候选写入 pending/（本 feature）

架构 §3.6：
- unrefined → pending/<slug>.md
- 正式域路径在后续 feature 实现（需要真实 LLM 蒸馏）
- 本 feature 只实现 pending/ 写入 + frontmatter 生成
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


def _generate_slug(title: str) -> str:
    """
    生成 slug（架构 §3.6）

    中文标题保留，英文小写连字符
    """
    # 保留中文字符
    if any("\u4e00" <= c <= "\u9fff" for c in title):
        # 中文：直接用作 slug（去除特殊字符）
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title, flags=re.UNICODE)
    else:
        # 英文：小写 + 连字符
        slug = re.sub(r"[^\w]+", "-", title.lower(), flags=re.UNICODE)

    slug = slug.strip("-")
    return slug or "untitled"


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


def write_unrefined_candidates(
    candidates: list[dict[str, Any]],
    global_kb_root: Path,
    config: dict[str, Any] | None = None,
) -> dict[str, int]:
    """
    写入 unrefined 候选到 pending/

    Args:
        candidates: 候选列表（dict 形式，便于 JSON 序列化）
        global_kb_root: 全局库根路径
        config: 配置

    Returns:
        统计：{written: int, skipped_duplicate: int}
    """
    stats = {"written": 0, "skipped_duplicate": 0}

    pending_dir = global_kb_root / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    # 收集已有文件的归一化指纹（用于去重）
    existing_fingerprints = set()
    for existing in pending_dir.glob("*.md"):
        try:
            content = existing.read_text(encoding="utf-8")
            fingerprint = _normalize_fingerprint(content)
            existing_fingerprints.add(fingerprint)
        except OSError:
            pass

    for cand in candidates:
        title = cand.get("title", "untitled")
        content = cand.get("content", "")
        domain = cand.get("domain", "engineering")
        confidence = cand.get("confidence", 0.0)
        source_refs = cand.get("source_refs", [])
        unrefined = cand.get("unrefined", True)

        # 生成文件内容
        frontmatter = _generate_frontmatter(
            title=title,
            domain=domain,
            confidence=confidence,
            source_refs=source_refs,
            unrefined=unrefined,
        )
        file_content = f"{frontmatter}\n\n{content}\n"

        # 去重检查
        fingerprint = _normalize_fingerprint(file_content)
        if fingerprint in existing_fingerprints:
            stats["skipped_duplicate"] += 1
            continue

        # 生成唯一文件名
        slug = _generate_slug(title)
        target_path = pending_dir / f"{slug}.md"

        # 冲突处理：加后缀
        counter = 2
        while target_path.exists():
            target_path = pending_dir / f"{slug}-{counter}.md"
            counter += 1

        # 写入
        try:
            target_path.write_text(file_content, encoding="utf-8")
            existing_fingerprints.add(fingerprint)  # 防止后续重复
            stats["written"] += 1
        except OSError as e:
            print(f"Warning: Failed to write {target_path}: {e}", file=sys.stderr)

    return stats


def _normalize_fingerprint(content: str) -> str:
    """归一化指纹（小写 + 去全部空白）"""
    return "".join(content.lower().split())


def git_commit_if_needed(
    global_kb_root: Path,
    config: dict[str, Any] | None = None,
) -> bool:
    """
    如果有变更则 git commit（中文信息）

    Args:
        global_kb_root: 全局库根路径
        config: 配置（git 段）

    Returns:
        是否产生了新提交
    """
    config = config or {}
    git_config = config.get("git", {})
    auto_commit = git_config.get("auto_commit", True)
    do_push = git_config.get("push", True)

    if not auto_commit:
        return False

    # 检查是否是 git 仓库
    git_dir = global_kb_root / ".git"
    if not git_dir.exists():
        # 自动初始化（D7）
        try:
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=global_kb_root,
                capture_output=True,
                check=True,
            )
            # 配置用户信息（使用环境默认）
            subprocess.run(
                ["git", "config", "user.name", "memory-evolve"],
                cwd=global_kb_root,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "evolve@memory.local"],
                cwd=global_kb_root,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Warning: git init failed: {e}", file=sys.stderr)
            return False

    # 检查是否有变更
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=global_kb_root,
            capture_output=True,
            text=True,
            check=True,
        )
        if not result.stdout.strip():
            return False  # 无变更

        # 统计新增文件数（用于提交信息）
        new_files = [
            line for line in result.stdout.split("\n") if line.startswith("??")
        ]
        count = len(new_files) if new_files else 1

        # 添加并提交
        subprocess.run(
            ["git", "add", "-A"],
            cwd=global_kb_root,
            capture_output=True,
            check=True,
        )

        commit_msg = f"feat(evolve): 沉淀 {count} 条经验（{date.today().isoformat()}）"
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=global_kb_root,
            capture_output=True,
            check=True,
        )

        # 尝试推送（尽力而为）
        if do_push:
            try:
                subprocess.run(
                    ["git", "push"],
                    cwd=global_kb_root,
                    capture_output=True,
                    check=False,  # 失败不报错
                )
            except subprocess.CalledProcessError:
                # push 失败只告警不失败
                print("Warning: git push failed (no remote?)", file=sys.stderr)

        return True

    except subprocess.CalledProcessError as e:
        print(f"Warning: git commit failed: {e}", file=sys.stderr)
        return False
