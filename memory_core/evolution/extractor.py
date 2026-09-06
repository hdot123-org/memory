"""
LLM 蒸馏器：--no-llm 降级路径（本 feature 实现）

架构 §3.5：
- --no-llm：原样捕获 + unrefined: true，一律进 pending/
- 真实 LLM 路径在 llm-extractor-engine feature 实现
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Candidate:
    """蒸馏候选"""

    title: str
    domain: str
    content: str
    confidence: float
    source_refs: list[dict[str, str]]
    genericity: str
    unrefined: bool


class NoLlmExtractor:
    """
    无 LLM 降级提取器

    原样捕获内容，标记 unrefined: true
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def extract_from_files(
        self,
        changed_files: list[dict[str, Any]],
        project_root: Path | None = None,
    ) -> list[Candidate]:
        """
        从变更文件列表提取候选

        Args:
            changed_files: [{"abs_path": Path, "rel_path": str, "sha256": str, "project_root": Path}]
            project_root: 项目根（如果 changed_files 未携带）

        Returns:
            候选列表
        """
        candidates = []

        for fc in changed_files:
            abs_path = fc.get("abs_path") or fc.get("path")
            if isinstance(abs_path, str):
                abs_path = Path(abs_path)
            rel_path = fc.get("rel_path", str(abs_path))
            fc_project = fc.get("project_root") or project_root

            try:
                content = abs_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            title = self._extract_title(content, abs_path)
            source_ref = {
                "project": str(fc_project) if fc_project else "",
                "path": rel_path,
            }

            candidates.append(
                Candidate(
                    title=title,
                    domain="engineering",
                    content=content,
                    confidence=0.0,
                    source_refs=[source_ref],
                    genericity="通用",
                    unrefined=True,
                )
            )

        return candidates

    def _extract_title(self, content: str, path: Path) -> str:
        """从内容或路径提取标题"""
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line:
                return line[:80]
        return path.stem


def extract_candidates(
    changed_files: list[dict[str, Any]],
    use_llm: bool = False,
    config: dict[str, Any] | None = None,
) -> list[Candidate]:
    """
    提取候选的统一入口

    Args:
        changed_files: 变更文件列表
        use_llm: 是否使用 LLM（本 feature 只实现 False 路径）
        config: 配置

    Returns:
        候选列表
    """
    if use_llm:
        # TODO: llm-extractor-engine feature
        raise NotImplementedError("LLM extraction not yet implemented")

    extractor = NoLlmExtractor(config)
    return extractor.extract_from_files(changed_files)
