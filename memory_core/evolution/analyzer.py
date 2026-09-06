"""
增量分析器：sha256 游标去抖、排除特定路径、配置开关、文件限额

架构 §3.4：
- 游标状态：state.json
- 输入范围：memory/kb/lessons/**.md, decisions/**.md, docs/**.md, log/{today}.md
- 排除：memory/kb/global/, patterns/registry.jsonl
- 变更判定：sha256（mtime 仅做快速预筛）
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class FileChange:
    """单个文件变更"""

    abs_path: Path
    rel_path: str  # 相对于 project_root
    project_root: Path
    sha256: str


@dataclass
class AnalysisResult:
    """单项目分析结果"""

    project_root: Path
    changed_files: list[FileChange] = field(default_factory=list)
    skipped_by_cap: int = 0
    error: str | None = None


class IncrementalAnalyzer:
    """
    增量分析器：基于 sha256 游标去抖

    架构 §3.4
    """

    def __init__(self, state_file: Path, config: dict[str, Any]):
        """
        Args:
            state_file: state.json 路径
            config: 配置字典（analyze 段）
        """
        self.state_file = state_file
        self.include_docs = config.get("analyze", {}).get("include_docs", True)
        self.include_daily_logs = config.get("analyze", {}).get("include_daily_logs", True)
        self.max_files_per_project = config.get("analyze", {}).get("max_files_per_project", 50)
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        """加载游标状态"""
        if not self.state_file.exists():
            return {"projects": {}}
        try:
            with self.state_file.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"projects": {}}

    def _save_state(self) -> None:
        """保存游标状态"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)

    def _compute_sha256(self, path: Path) -> str:
        """计算文件 sha256"""
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _get_project_cursors(self, project_root: Path) -> dict[str, dict[str, Any]]:
        """获取项目的游标字典"""
        key = str(project_root.resolve())
        project_state = self._state.get("projects", {}).get(key, {})
        return project_state.get("file_cursors", {})

    def _update_project_cursors(self, project_root: Path, cursors: dict[str, dict[str, Any]]) -> None:
        """更新项目的游标"""
        key = str(project_root.resolve())
        if "projects" not in self._state:
            self._state["projects"] = {}
        if key not in self._state["projects"]:
            self._state["projects"][key] = {"file_cursors": {}, "stats": {}}
        self._state["projects"][key]["file_cursors"] = cursors

    def _collect_candidate_files(self, project_root: Path) -> list[Path]:
        """收集候选文件（按配置开关）"""
        files: list[Path] = []
        kb_dir = project_root / "memory" / "kb"

        # lessons & decisions（始终包含）
        for sub in ("lessons", "decisions"):
            sub_dir = kb_dir / sub
            if sub_dir.exists():
                for md in sub_dir.rglob("*.md"):
                    # 排除 global/ 与 patterns/registry.jsonl
                    rel = md.relative_to(project_root)
                    if "memory/kb/global" in str(rel):
                        continue
                    if "memory/kb/patterns/registry.jsonl" in str(rel):
                        continue
                    files.append(md)

        # docs（按配置）
        if self.include_docs:
            docs_dir = project_root / "memory" / "docs"
            if docs_dir.exists():
                for md in docs_dir.rglob("*.md"):
                    files.append(md)

        # daily logs（按配置，只取今天）
        if self.include_daily_logs:
            log_dir = project_root / "memory" / "log"
            if log_dir.exists():
                today = date.today().isoformat()  # YYYY-MM-DD
                today_log = log_dir / f"{today}.md"
                if today_log.exists():
                    files.append(today_log)

        return sorted(files, key=lambda p: str(p.relative_to(project_root)))

    def analyze_project(self, project_root: Path) -> AnalysisResult:
        """
        分析单个项目的变更文件

        Args:
            project_root: 项目根路径

        Returns:
            分析结果（变更文件列表 + 跳过计数）
        """
        result = AnalysisResult(project_root=project_root)

        try:
            # 收集候选文件
            all_files = self._collect_candidate_files(project_root)
            cursors = self._get_project_cursors(project_root)

            # 检测变更
            changed: list[FileChange] = []
            for f in all_files:
                rel_path = str(f.relative_to(project_root))
                current_sha = self._compute_sha256(f)
                cursor = cursors.get(rel_path)

                if cursor is None or cursor.get("sha256") != current_sha:
                    changed.append(
                        FileChange(
                            abs_path=f,
                            rel_path=rel_path,
                            project_root=project_root,
                            sha256=current_sha,
                        )
                    )

            # 文件限额（D15：字典序前 N）
            if len(changed) > self.max_files_per_project:
                # changed 已经按 rel_path 字典序排序（因为 all_files 是 sorted 的）
                result.skipped_by_cap = len(changed) - self.max_files_per_project
                result.changed_files = changed[: self.max_files_per_project]
            else:
                result.changed_files = changed

        except PermissionError as e:
            result.error = f"Permission denied: {e}"
        except OSError as e:
            result.error = f"OS error: {e}"

        return result

    def update_cursors(self, project_root: Path, processed_files: list[FileChange]) -> None:
        """
        更新游标（只推进已处理的文件）

        Args:
            project_root: 项目根路径
            processed_files: 本轮实际处理的文件列表
        """
        cursors = self._get_project_cursors(project_root)
        for fc in processed_files:
            cursors[fc.rel_path] = {"sha256": fc.sha256}
        self._update_project_cursors(project_root, cursors)
        self._save_state()

    def update_stats(
        self,
        project_root: Path,
        candidates_count: int,
        changed_count: int,
        skipped_by_cap: int,
    ) -> None:
        """更新项目统计"""
        key = str(project_root.resolve())
        if key not in self._state.get("projects", {}):
            self._state.setdefault("projects", {})[key] = {
                "file_cursors": {},
                "stats": {},
            }
        self._state["projects"][key]["stats"] = {
            "last_run_at": date.today().isoformat(),
            "candidates_count": candidates_count,
            "changed_count": changed_count,
            "skipped_by_cap": skipped_by_cap,
        }
        self._save_state()
