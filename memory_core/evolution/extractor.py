"""
LLM 蒸馏引擎（架构 §3.5）

AxonhubEngine: OpenAI 兼容 POST chat/completions，stdlib urllib，不新增三方依赖。
密钥解析链：env api_key_env → api_key_op_ref 运行时 op read → 报错。
提示词：输入=变更文件全文+项目上下文，单文件 >16KB 头尾截断。
输出=JSON 候选数组 {title, domain, content, confidence, source_refs, genericity}。
reasoning 模型处理：max_tokens ≥4096，只解析 choices[0].message.content，忽略 reasoning_content。
降级：API 连续失败重试 2 次后 unrefined 只进 pending、exit 0 不崩溃。
预算：daily_budget_tokens 累计、超限停止 LLM 剩余降级、0 预算启动即超限（D14）。

VAL-EXT-001 / VAL-EXT-002 / VAL-EXT-003 / VAL-EXT-004 / VAL-SED-001
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# 六个全局域（与 sediment.VALID_DOMAINS 保持一致）
VALID_DOMAINS = ("operations", "engineering", "collaboration", "governance", "infra", "audit")

# 单文件大小上限（字节），超过则头尾截断
_MAX_FILE_SIZE = 16 * 1024  # 16KB


# ---------------------------------------------------------------------------
# 候选数据结构
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """蒸馏候选"""

    title: str
    domain: str
    content: str
    confidence: float
    source_refs: list[dict[str, str]]
    genericity: str  # "通用" or "项目专属"
    unrefined: bool = False


# ---------------------------------------------------------------------------
# 密钥解析链
# ---------------------------------------------------------------------------


def resolve_api_key(config: dict[str, Any]) -> str:
    """
    密钥解析链（架构 §3.2）

    1. env api_key_env → 读取环境变量
    2. api_key_op_ref → 运行时 op read（1Password CLI）
    3. 都没有 → 报错

    密钥不落盘、不进日志。
    """
    llm_config = config.get("llm", {})
    api_key_env = llm_config.get("api_key_env", "AXONHUB_API_KEY")
    api_key_op_ref = llm_config.get("api_key_op_ref", "")

    # 1. 尝试从环境变量获取
    key = os.environ.get(api_key_env)
    if key:
        return key

    # 2. 尝试从 1Password op read 获取
    if api_key_op_ref:
        try:
            result = subprocess.run(
                ["op", "read", api_key_op_ref],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # 3. 报错
    raise RuntimeError(
        f"无法解析 API 密钥：环境变量 {api_key_env} 未设置"
        + (f"，且 op read {api_key_op_ref} 失败" if api_key_op_ref else "")
    )


# ---------------------------------------------------------------------------
# AxonhubEngine
# ---------------------------------------------------------------------------


@dataclass
class LLMCallResult:
    """LLM 调用结果"""

    content: str  # choices[0].message.content
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AxonhubEngine:
    """
    OpenAI 兼容 chat/completions 引擎（stdlib urllib，不新增三方依赖）

    架构 §3.5：
    - POST chat/completions
    - glm-5.3 是 reasoning 模型：max_tokens 给足（≥4096），只解析 choices[0].message.content
    - 忽略 reasoning_content
    - 无 /v1/models 依赖
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        llm_config = config.get("llm", {})
        self.base_url = llm_config.get("base_url", "https://node1.tail5e888.ts.net/v1")
        self.model = llm_config.get("model", "glm-5.3")
        self.max_tokens = llm_config.get("max_tokens", 4096)
        self.api_key = resolve_api_key(config)
        # 重试次数
        self.max_retries = 2

    def chat_completion(self, messages: list[dict[str, str]]) -> LLMCallResult:
        """
        调用 chat/completions API

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]

        Returns:
            LLMCallResult

        Raises:
            RuntimeError: API 调用失败（重试 2 次后仍失败）
        """
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=120) as response:
                    response_body = response.read().decode("utf-8")

                result = json.loads(response_body)

                # 只解析 choices[0].message.content，忽略 reasoning_content
                choices = result.get("choices", [])
                if not choices:
                    raise RuntimeError("API 返回空 choices")

                message = choices[0].get("message", {})
                content = message.get("content", "")

                if not content:
                    raise RuntimeError("API 返回空 content")

                # 解析 token 用量
                usage = result.get("usage", {})
                return LLMCallResult(
                    content=content,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                )

            except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
                last_error = e
                if attempt < self.max_retries:
                    print(
                        f"Warning: LLM API 调用失败（第 {attempt + 1} 次），重试中: {e}",
                        file=sys.stderr,
                    )
                continue

        raise RuntimeError(f"LLM API 调用失败（重试 {self.max_retries} 次后）: {last_error}")


# ---------------------------------------------------------------------------
# 提示词构建
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一个跨项目经验蒸馏专家。你的任务是从项目经验文件中提取通用的、可复用的经验教训。

## 输出格式

输出一个 JSON 数组，每个元素是一个候选经验，结构如下：

```json
[
  {
    "title": "简明标题（中文优先）",
    "domain": "operations|engineering|collaboration|governance|infra|audit 之一",
    "content": "蒸馏改写后的 Markdown 正文（不是逐字复制！要综合改写，提取核心经验）",
    "confidence": 0.0-1.0 之间的数值（你对这条经验的质量和通用性的信心）",
    "source_refs": [
      {"project": "项目名称", "path": "相对路径"}
    ],
    "genericity": "通用 或 项目专属"
  }
]
```

## 关键规则

1. **蒸馏而非复制**：content 必须是改写综合，不得逐字照抄原文。提取核心经验，用自己的话重新表述。
2. **domain 选择**：从以下六域中选择最合适的：
   - operations: 运维、部署、监控、备份恢复
   - engineering: 编码、架构、测试、性能
   - collaboration: 团队协作、流程、沟通
   - governance: 治理、规范、决策、策略
   - infra: 基础设施、网络、CI/CD、工具链
   - audit: 审计、安全、合规、日志
3. **confidence 评分**：
   - 0.9+: 高质量、通用性强、多项目可复用
   - 0.7-0.9: 中等质量、有一定通用性
   - 0.5-0.7: 低质量或过于具体
   - <0.5: 不建议沉淀
4. **genericity 判定**：
   - "通用": 跨项目可复用的经验
   - "项目专属": 只适用于特定项目的经验（如具体端口号、项目特定配置）
5. **source_refs**: 必须指向输入中的真实文件路径。
6. 如果没有值得提取的经验，输出空数组 `[]`。

只输出 JSON，不要输出其他内容。"""


def _build_user_prompt(
    changed_files: list[dict[str, Any]],
    project_root: Path | None = None,
) -> str:
    """
    构建用户提示词

    Args:
        changed_files: [{"abs_path": Path, "rel_path": str, "project_root": Path, ...}]
        project_root: 项目根路径

    Returns:
        用户提示词文本
    """
    parts = []

    if project_root:
        parts.append(f"项目名称: {project_root.name}")
        parts.append(f"项目路径: {project_root}")
        parts.append("")

    parts.append("## 输入文件")
    parts.append("")

    for fc in changed_files:
        abs_path = fc.get("abs_path")
        if not abs_path:
            continue
        if isinstance(abs_path, str):
            abs_path = Path(abs_path)

        rel_path = fc.get("rel_path", str(abs_path))

        try:
            content = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = "(无法读取文件内容)"

        # 单文件 >16KB 头尾截断
        file_bytes = content.encode("utf-8")
        if len(file_bytes) > _MAX_FILE_SIZE:
            half = _MAX_FILE_SIZE // 2
            head = file_bytes[:half].decode("utf-8", errors="replace")
            tail = file_bytes[-half:].decode("utf-8", errors="replace")
            content = head + "\n\n... [内容过长，已截断] ...\n\n" + tail

        parts.append(f"### 文件: {rel_path}")
        parts.append("```")
        parts.append(content)
        parts.append("```")
        parts.append("")

    parts.append("## 任务")
    parts.append("")
    parts.append("请从上述文件中提取值得跨项目复用的经验教训。")
    parts.append("记住：蒸馏改写，不要逐字复制。")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 候选解析
# ---------------------------------------------------------------------------


def _parse_llm_response(content: str) -> list[dict[str, Any]]:
    """
    解析 LLM 返回的 JSON 候选数组

    健壮解析：处理 markdown code fence 包裹、多余文本等情况。
    """
    # 尝试提取 JSON（可能被 markdown code fence 包裹）
    json_str = content.strip()

    # 移除可能的 markdown code fence
    code_fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", json_str, re.DOTALL)
    if code_fence_match:
        json_str = code_fence_match.group(1).strip()

    # 尝试提取第一个 [ 到最后一个 ]
    bracket_start = json_str.find("[")
    bracket_end = json_str.rfind("]")
    if bracket_start >= 0 and bracket_end > bracket_start:
        json_str = json_str[bracket_start : bracket_end + 1]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    # 校验并规范化每个候选
    candidates: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue

        # 必填字段
        title = item.get("title", "")
        domain = item.get("domain", "")
        content_text = item.get("content", "")
        confidence = item.get("confidence", 0.0)
        source_refs = item.get("source_refs", [])
        genericity = item.get("genericity", "通用")

        if not title or not content_text:
            continue

        # 规范化 domain
        if domain not in VALID_DOMAINS:
            domain = "engineering"  # 默认域

        # 规范化 confidence
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        # 规范化 source_refs
        if not isinstance(source_refs, list):
            source_refs = []
        normalized_refs: list[dict[str, str]] = []
        for ref in source_refs:
            if isinstance(ref, dict):
                normalized_refs.append(
                    {
                        "project": str(ref.get("project", "")),
                        "path": str(ref.get("path", "")),
                    }
                )

        # 规范化 genericity
        if genericity not in ("通用", "项目专属"):
            genericity = "通用"

        candidates.append(
            {
                "title": str(title),
                "domain": domain,
                "content": str(content_text),
                "confidence": confidence,
                "source_refs": normalized_refs,
                "genericity": genericity,
                "unrefined": False,
            }
        )

    return candidates


# ---------------------------------------------------------------------------
# 预算追踪
# ---------------------------------------------------------------------------


@dataclass
class BudgetTracker:
    """
    每日 token 预算追踪

    D14: daily_budget_tokens=0 为合法值，启动即超限
    """

    daily_budget_tokens: int
    tokens_used: int = 0
    llm_calls: int = 0

    @property
    def is_exceeded(self) -> bool:
        """是否已超限"""
        return self.tokens_used >= self.daily_budget_tokens

    def can_call(self) -> bool:
        """是否还能发起 LLM 调用"""
        return not self.is_exceeded

    def record_usage(self, tokens: int) -> None:
        """记录一次调用的 token 用量"""
        self.tokens_used += tokens
        self.llm_calls += 1


# ---------------------------------------------------------------------------
# LLMExtractor（高级提取器）
# ---------------------------------------------------------------------------


class LLMExtractor:
    """
    LLM 蒸馏提取器

    架构 §3.5：
    - 真实 LLM 调用（AxonhubEngine）
    - 预算追踪（daily_budget_tokens 累计）
    - 降级：API 失败 → unrefined + pending
    - genericity=项目专属 → 不晋升仅记录
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.budget = BudgetTracker(
            daily_budget_tokens=config.get("llm", {}).get("daily_budget_tokens", 2_000_000),
        )
        self._engine: AxonhubEngine | None = None
        self._engine_init_error: str | None = None

        # 初始化引擎（可能因密钥问题失败）
        try:
            self._engine = AxonhubEngine(config)
        except RuntimeError as e:
            self._engine_init_error = str(e)

    @property
    def tokens_used(self) -> int:
        return self.budget.tokens_used

    @property
    def llm_calls(self) -> int:
        return self.budget.llm_calls

    def extract_from_files(
        self,
        changed_files: list[dict[str, Any]],
        project_root: Path | None = None,
    ) -> list[Candidate]:
        """
        从变更文件列表提取候选

        Args:
            changed_files: [{"abs_path": Path, "rel_path": str, "sha256": str, "project_root": Path}]
            project_root: 项目根

        Returns:
            候选列表
        """
        if not changed_files:
            return []

        # 预算检查（D14: 0 预算启动即超限）
        if not self.budget.can_call():
            print(
                f"Warning: LLM 预算已超限（{self.budget.tokens_used}/{self.budget.daily_budget_tokens}），"
                "降级为 unrefined 模式",
                file=sys.stderr,
            )
            return self._fallback_no_llm(changed_files, project_root)

        # 引擎初始化失败 → 降级
        if self._engine is None:
            print(
                f"Warning: LLM 引擎初始化失败（{self._engine_init_error}），降级为 unrefined 模式",
                file=sys.stderr,
            )
            return self._fallback_no_llm(changed_files, project_root)

        # 尝试 LLM 调用
        try:
            return self._extract_with_llm(changed_files, project_root)
        except RuntimeError as e:
            print(
                f"Warning: LLM 调用失败，降级为 unrefined 模式: {e}",
                file=sys.stderr,
            )
            return self._fallback_no_llm(changed_files, project_root)

    def _extract_with_llm(
        self,
        changed_files: list[dict[str, Any]],
        project_root: Path | None,
    ) -> list[Candidate]:
        """使用 LLM 提取候选"""
        assert self._engine is not None

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(changed_files, project_root)},
        ]

        result = self._engine.chat_completion(messages)
        self.budget.record_usage(result.total_tokens)

        # 解析候选
        parsed = _parse_llm_response(result.content)

        if not parsed:
            # LLM 未产出有效候选 → 降级
            return self._fallback_no_llm(changed_files, project_root)

        # 转换为 Candidate 对象
        candidates: list[Candidate] = []
        for item in parsed:
            # genericity=项目专属 → 不晋升仅记录（confidence 强制降低）
            if item["genericity"] == "项目专属":
                item["confidence"] = min(item["confidence"], 0.5)

            # 确保 source_refs 非空
            if not item["source_refs"]:
                for fc in changed_files:
                    rel_path = fc.get("rel_path", "")
                    if rel_path:
                        item["source_refs"].append(
                            {
                                "project": str(project_root) if project_root else "",
                                "path": rel_path,
                            }
                        )

            candidates.append(
                Candidate(
                    title=item["title"],
                    domain=item["domain"],
                    content=item["content"],
                    confidence=item["confidence"],
                    source_refs=item["source_refs"],
                    genericity=item["genericity"],
                    unrefined=False,
                )
            )

        return candidates

    def _fallback_no_llm(
        self,
        changed_files: list[dict[str, Any]],
        project_root: Path | None,
    ) -> list[Candidate]:
        """降级：无 LLM 原样捕获"""
        fallback = NoLlmExtractor(self.config)
        return fallback.extract_from_files(changed_files, project_root)


# ---------------------------------------------------------------------------
# NoLlmExtractor（向后兼容）
# ---------------------------------------------------------------------------


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
            if not abs_path:  # None or empty string
                continue
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


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def extract_candidates(
    changed_files: list[dict[str, Any]],
    use_llm: bool = False,
    config: dict[str, Any] | None = None,
) -> list[Candidate]:
    """
    提取候选的统一入口

    Args:
        changed_files: 变更文件列表
        use_llm: 是否使用 LLM
        config: 配置

    Returns:
        候选列表
    """
    config = config or {}

    if use_llm:
        extractor = LLMExtractor(config)
        return extractor.extract_from_files(changed_files)

    extractor = NoLlmExtractor(config)
    return extractor.extract_from_files(changed_files)
