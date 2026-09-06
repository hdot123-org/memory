"""
项目注册枚举：从 lifecycle 注册表现读去重，提供健康分类
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ProjectEntry:
    """单个注册项目条目"""

    git_root: Path
    health: str  # active_kb / no_kb / missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "git_root": str(self.git_root),
            "health": self.health,
        }


class EvolutionRegistry:
    """
    lifecycle 注册表现读去重枚举器

    权威源：~/.memory-core/project-lifecycle/path-index.json ∪ projects/*.json
    健康分类：active_kb / no_kb / missing
    """

    def __init__(self, lifecycle_root: Path | None = None):
        """
        初始化注册表

        Args:
            lifecycle_root: lifecycle 注册表根目录，默认 ~/.memory-core/project-lifecycle
        """
        if lifecycle_root is None:
            lifecycle_root = Path.home() / ".memory-core" / "project-lifecycle"
        self.lifecycle_root = lifecycle_root

    def get_all_entries(self) -> list[ProjectEntry]:
        """
        获取全部注册项目（去重 + 健康分类）

        Returns:
            去重后的项目条目列表
        """
        # 1. 读取 path-index.json
        path_index_roots = self._read_path_index()

        # 2. 读取 projects/*.json
        projects_roots = self._read_projects_dir()

        # 3. 合并去重（按 git_root）
        all_roots = set()
        all_roots.update(path_index_roots)
        all_roots.update(projects_roots)

        # 4. 健康分类
        entries = []
        for git_root in all_roots:
            health = self._classify_health(git_root)
            entries.append(ProjectEntry(git_root=git_root, health=health))

        return entries

    def _read_path_index(self) -> list[Path]:
        """读取 path-index.json 中的 git_root（M1 scrutiny 修复：逐条目容错）"""
        path_index_file = self.lifecycle_root / "path-index.json"
        if not path_index_file.exists():
            return []

        try:
            with path_index_file.open(encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to read path-index.json: {e}", file=sys.stderr)
            return []

        paths_dict = data.get("paths", {})
        if not isinstance(paths_dict, dict):
            print("Warning: path-index.json 'paths' is not a dict", file=sys.stderr)
            return []

        roots = []
        for key, info in paths_dict.items():
            try:
                if not isinstance(info, dict):
                    print(f"Warning: path-index.json entry '{key}' is not a dict, skipping", file=sys.stderr)
                    continue
                git_root = info.get("git_root")
                if git_root:
                    roots.append(Path(git_root))
            except (TypeError, AttributeError) as e:
                print(f"Warning: Failed to parse path-index.json entry '{key}': {e}", file=sys.stderr)
                continue

        return roots

    def _read_projects_dir(self) -> list[Path]:
        """读取 projects/*.json 中的 git_root"""
        projects_dir = self.lifecycle_root / "projects"
        if not projects_dir.exists():
            return []

        roots = []
        try:
            for json_file in projects_dir.glob("*.json"):
                try:
                    with json_file.open(encoding="utf-8") as f:
                        data = json.load(f)
                    git_root = data.get("git_root")
                    if git_root:
                        roots.append(Path(git_root))
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    print(f"Warning: Failed to read {json_file}: {e}", file=sys.stderr)
                    continue
        except OSError as e:
            print(f"Warning: Failed to read projects directory: {e}", file=sys.stderr)

        return roots

    def _classify_health(self, git_root: Path) -> str:
        """
        分类项目健康状态

        Args:
            git_root: 项目根路径

        Returns:
            active_kb / no_kb / missing
        """
        if not git_root.exists():
            return "missing"

        kb_dir = git_root / "memory" / "kb"
        if not kb_dir.exists():
            return "no_kb"

        # 递归检查是否有任何文件（排除空目录）
        try:
            for item in kb_dir.rglob("*"):
                if item.is_file():
                    return "active_kb"
        except OSError:
            pass

        return "no_kb"

    def get_backup_paths(self) -> list[str]:
        """
        获取全部消费项目的 memory 目录绝对路径（用于 restic 备份）

        M1 scrutiny 加固：resolve() 后有序去重（symlink 别名不重复）

        Returns:
            存在于磁盘的 <git_root>/memory 绝对路径列表（排序去重）
        """
        entries = self.get_all_entries()
        seen: set[str] = set()
        backup_paths: list[str] = []

        for entry in entries:
            memory_dir = entry.git_root / "memory"
            if memory_dir.exists() and memory_dir.is_dir():
                resolved = str(memory_dir.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    backup_paths.append(resolved)

        return sorted(backup_paths)
