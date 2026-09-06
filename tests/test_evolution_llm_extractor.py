"""
Tests for LLM extractor functionality (extractor.py)

Covers:
- resolve_api_key: API key resolution chain (env → op ref → error)
- AxonhubEngine: HTTP client with retry logic
- BudgetTracker: token budget tracking
- LLMExtractor: high-level extraction with fallback
- _parse_llm_response: JSON parsing robustness
- _build_user_prompt: prompt construction with truncation
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from memory_core.evolution.extractor import (
    AxonhubEngine,
    BudgetTracker,
    LLMExtractor,
    _build_user_prompt,
    _parse_llm_response,
    resolve_api_key,
)

# ---------------------------------------------------------------------------
# resolve_api_key tests
# ---------------------------------------------------------------------------


class TestResolveApiKey:
    """测试 API 密钥解析链"""

    def test_resolve_from_env(self):
        """Test: 从环境变量解析 API 密钥"""
        config = {"llm": {"api_key_env": "TEST_API_KEY"}}
        with patch.dict(os.environ, {"TEST_API_KEY": "test-key-123"}):
            key = resolve_api_key(config)
            assert key == "test-key-123"

    def test_resolve_from_env_default(self):
        """Test: 使用默认环境变量名"""
        with patch.dict(os.environ, {"AXONHUB_API_KEY": "default-key"}):
            config = {"llm": {}}
            key = resolve_api_key(config)
            assert key == "default-key"

    def test_resolve_from_op_ref(self):
        """Test: 从 1Password op read 解析密钥"""
        config = {"llm": {"api_key_env": "NONEXISTENT", "api_key_op_ref": "op://vault/item/field"}}

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "op-secret-key"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            key = resolve_api_key(config)
            assert key == "op-secret-key"
            mock_run.assert_called_once()
            assert "op" in mock_run.call_args[0][0]
            assert "read" in mock_run.call_args[0][0]

    def test_resolve_env_takes_precedence(self):
        """Test: 环境变量优先于 op ref"""
        config = {"llm": {"api_key_env": "TEST_KEY", "api_key_op_ref": "op://vault/item/field"}}

        with patch.dict(os.environ, {"TEST_KEY": "env-key"}):
            key = resolve_api_key(config)
            assert key == "env-key"

    def test_resolve_no_key_raises_error(self):
        """Test: 无密钥来源时抛出错误"""
        config = {"llm": {"api_key_env": "NONEXISTENT"}}
        with pytest.raises(RuntimeError, match="无法解析 API 密钥"):
            resolve_api_key(config)

    def test_resolve_op_read_failure(self):
        """Test: op read 失败时抛出错误"""
        config = {"llm": {"api_key_env": "NONEXISTENT", "api_key_op_ref": "op://vault/item/field"}}

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(RuntimeError, match="无法解析 API 密钥"),
        ):
            resolve_api_key(config)


# ---------------------------------------------------------------------------
# BudgetTracker tests
# ---------------------------------------------------------------------------


class TestBudgetTracker:
    """测试 token 预算追踪"""

    def test_initial_state(self):
        """Test: 初始状态"""
        tracker = BudgetTracker(daily_budget_tokens=1000)
        assert not tracker.is_exceeded
        assert tracker.can_call()
        assert tracker.tokens_used == 0
        assert tracker.llm_calls == 0

    def test_record_usage(self):
        """Test: 记录 token 使用"""
        tracker = BudgetTracker(daily_budget_tokens=1000)
        tracker.record_usage(500)

        assert tracker.tokens_used == 500
        assert tracker.llm_calls == 1
        assert not tracker.is_exceeded
        assert tracker.can_call()

    def test_budget_exceeded(self):
        """Test: 预算超限"""
        tracker = BudgetTracker(daily_budget_tokens=1000)
        tracker.record_usage(1000)

        assert tracker.is_exceeded
        assert not tracker.can_call()

    def test_budget_exceeded_over(self):
        """Test: 超过预算"""
        tracker = BudgetTracker(daily_budget_tokens=1000)
        tracker.record_usage(1500)

        assert tracker.is_exceeded
        assert not tracker.can_call()

    def test_zero_budget(self):
        """Test: 零预算（D14）"""
        tracker = BudgetTracker(daily_budget_tokens=0)

        assert tracker.is_exceeded
        assert not tracker.can_call()


# ---------------------------------------------------------------------------
# _parse_llm_response tests
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    """测试 LLM 响应解析"""

    def test_parse_valid_json(self):
        """Test: 解析有效 JSON"""
        content = json.dumps(
            [
                {
                    "title": "Test Title",
                    "domain": "engineering",
                    "content": "Test content",
                    "confidence": 0.8,
                    "source_refs": [{"project": "proj1", "path": "file.md"}],
                    "genericity": "通用",
                }
            ]
        )

        candidates = _parse_llm_response(content)

        assert len(candidates) == 1
        assert candidates[0]["title"] == "Test Title"
        assert candidates[0]["domain"] == "engineering"
        assert candidates[0]["confidence"] == 0.8

    def test_parse_json_in_code_fence(self):
        """Test: 解析 markdown 代码块中的 JSON"""
        content = """```json
[
    {
        "title": "Test",
        "domain": "operations",
        "content": "Content",
        "confidence": 0.7,
        "source_refs": [],
        "genericity": "通用"
    }
]
```"""

        candidates = _parse_llm_response(content)
        assert len(candidates) == 1

    def test_parse_invalid_domain_normalized(self):
        """Test: 无效 domain 被规范化"""
        content = json.dumps(
            [
                {
                    "title": "Test",
                    "domain": "invalid_domain",
                    "content": "Content",
                    "confidence": 0.5,
                    "source_refs": [],
                    "genericity": "通用",
                }
            ]
        )

        candidates = _parse_llm_response(content)
        assert candidates[0]["domain"] == "engineering"  # 默认域

    def test_parse_invalid_confidence_clamped(self):
        """Test: 无效 confidence 被限制在 [0, 1]"""
        content = json.dumps(
            [
                {
                    "title": "Test",
                    "domain": "engineering",
                    "content": "Content",
                    "confidence": 1.5,
                    "source_refs": [],
                    "genericity": "通用",
                }
            ]
        )

        candidates = _parse_llm_response(content)
        assert candidates[0]["confidence"] == 1.0

    def test_parse_invalid_genericity_normalized(self):
        """Test: 无效 genericity 被规范化"""
        content = json.dumps(
            [
                {
                    "title": "Test",
                    "domain": "engineering",
                    "content": "Content",
                    "confidence": 0.5,
                    "source_refs": [],
                    "genericity": "invalid",
                }
            ]
        )

        candidates = _parse_llm_response(content)
        assert candidates[0]["genericity"] == "通用"

    def test_parse_empty_response(self):
        """Test: 空响应返回空列表"""
        candidates = _parse_llm_response("[]")
        assert candidates == []

    def test_parse_invalid_json(self):
        """Test: 无效 JSON 返回空列表"""
        candidates = _parse_llm_response("not valid json")
        assert candidates == []

    def test_parse_missing_required_fields(self):
        """Test: 缺少必填字段的候选被跳过"""
        content = json.dumps(
            [
                {
                    "title": "",  # 空标题
                    "domain": "engineering",
                    "content": "Content",
                    "confidence": 0.5,
                    "source_refs": [],
                    "genericity": "通用",
                },
                {
                    "title": "Valid",
                    "domain": "engineering",
                    "content": "",  # 空内容
                    "confidence": 0.5,
                    "source_refs": [],
                    "genericity": "通用",
                },
            ]
        )

        candidates = _parse_llm_response(content)
        assert len(candidates) == 0


# ---------------------------------------------------------------------------
# _build_user_prompt tests
# ---------------------------------------------------------------------------


class TestBuildUserPrompt:
    """测试提示词构建"""

    def test_build_prompt_with_project_root(self):
        """Test: 带项目根路径的提示词"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_file = project_root / "test.md"
            test_file.write_text("# Test\n\nContent here")

            changed_files = [
                {
                    "abs_path": test_file,
                    "rel_path": "memory/kb/lessons/test.md",
                    "project_root": project_root,
                }
            ]

            prompt = _build_user_prompt(changed_files, project_root)

            assert project_root.name in prompt
            assert str(project_root) in prompt
            assert "memory/kb/lessons/test.md" in prompt
            assert "Content here" in prompt

    def test_build_prompt_large_file_truncated(self):
        """Test: 大文件被截断"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_file = project_root / "large.md"
            # 创建一个 > 16KB 的文件
            large_content = "x" * 20000
            test_file.write_text(large_content)

            changed_files = [
                {
                    "abs_path": test_file,
                    "rel_path": "large.md",
                    "project_root": project_root,
                }
            ]

            prompt = _build_user_prompt(changed_files, project_root)

            # 应该包含截断标记
            assert "内容过长，已截断" in prompt
            # 提示词长度应该远小于原始内容
            assert len(prompt) < 20000

    def test_build_prompt_multiple_files(self):
        """Test: 多个文件的提示词"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            file1 = project_root / "file1.md"
            file1.write_text("# File 1\n\nContent 1")

            file2 = project_root / "file2.md"
            file2.write_text("# File 2\n\nContent 2")

            changed_files = [
                {"abs_path": file1, "rel_path": "file1.md", "project_root": project_root},
                {"abs_path": file2, "rel_path": "file2.md", "project_root": project_root},
            ]

            prompt = _build_user_prompt(changed_files, project_root)

            assert "file1.md" in prompt
            assert "file2.md" in prompt
            assert "Content 1" in prompt
            assert "Content 2" in prompt


# ---------------------------------------------------------------------------
# AxonhubEngine tests
# ---------------------------------------------------------------------------


class TestAxonhubEngine:
    """测试 Axonhub HTTP 客户端"""

    def test_engine_initialization(self):
        """Test: 引擎初始化"""
        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            engine = AxonhubEngine(config)
            assert engine.api_key == "test-key"
            assert engine.base_url == "https://node1.tail5e888.ts.net/v1"
            assert engine.model == "glm-5.3"
            assert engine.max_tokens == 4096

    def test_engine_custom_config(self):
        """Test: 自定义配置"""
        config = {
            "llm": {
                "api_key_env": "TEST_KEY",
                "base_url": "https://custom.api/v1",
                "model": "custom-model",
                "max_tokens": 8192,
            }
        }
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            engine = AxonhubEngine(config)
            assert engine.base_url == "https://custom.api/v1"
            assert engine.model == "custom-model"
            assert engine.max_tokens == 8192

    def test_engine_retry_on_failure(self):
        """Test: 失败时重试"""
        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            engine = AxonhubEngine(config)

            # Mock urlopen 使其失败两次后成功
            mock_response = Mock()
            mock_response.read.return_value = json.dumps(
                {
                    "choices": [{"message": {"content": "test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                }
            ).encode("utf-8")
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)

            call_count = [0]

            def mock_urlopen(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise OSError("Connection failed")
                return mock_response

            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                result = engine.chat_completion([{"role": "user", "content": "test"}])

                assert result.content == "test response"
                assert result.total_tokens == 30
                assert call_count[0] == 3  # 重试了 2 次

    def test_engine_all_retries_fail(self):
        """Test: 所有重试都失败"""
        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            engine = AxonhubEngine(config)

            with (
                patch("urllib.request.urlopen", side_effect=OSError("Connection failed")),
                pytest.raises(RuntimeError, match="LLM API 调用失败"),
            ):
                engine.chat_completion([{"role": "user", "content": "test"}])


# ---------------------------------------------------------------------------
# LLMExtractor tests
# ---------------------------------------------------------------------------


class TestLLMExtractor:
    """测试高级 LLM 提取器"""

    def test_extractor_initialization(self):
        """Test: 提取器初始化"""
        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            extractor = LLMExtractor(config)
            assert extractor._engine is not None
            assert extractor.tokens_used == 0
            assert extractor.llm_calls == 0

    def test_extractor_initialization_no_key(self):
        """Test: 无密钥时初始化（应该降级）"""
        config = {"llm": {"api_key_env": "NONEXISTENT"}}
        extractor = LLMExtractor(config)
        assert extractor._engine is None
        assert extractor._engine_init_error is not None

    def test_extractor_budget_exceeded(self):
        """Test: 预算超限时降级"""
        config = {"llm": {"api_key_env": "TEST_KEY", "daily_budget_tokens": 0}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            extractor = LLMExtractor(config)

            with tempfile.TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                test_file = project_root / "test.md"
                test_file.write_text("# Test\n\nContent")

                changed_files = [
                    {
                        "abs_path": test_file,
                        "rel_path": "test.md",
                        "project_root": project_root,
                    }
                ]

                candidates = extractor.extract_from_files(changed_files)

                # 应该降级为 unrefined
                assert len(candidates) == 1
                assert candidates[0].unrefined is True

    def test_extractor_no_engine_fallback(self):
        """Test: 无引擎时降级"""
        config = {"llm": {"api_key_env": "NONEXISTENT"}}
        extractor = LLMExtractor(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_file = project_root / "test.md"
            test_file.write_text("# Test\n\nContent")

            changed_files = [
                {
                    "abs_path": test_file,
                    "rel_path": "test.md",
                    "project_root": project_root,
                }
            ]

            candidates = extractor.extract_from_files(changed_files)

            # 应该降级为 unrefined
            assert len(candidates) == 1
            assert candidates[0].unrefined is True

    def test_extractor_llm_call_failure_fallback(self):
        """Test: LLM 调用失败时降级"""
        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            extractor = LLMExtractor(config)

            # Mock 引擎使其失败
            extractor._engine = Mock()
            extractor._engine.chat_completion.side_effect = RuntimeError("API failed")

            with tempfile.TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                test_file = project_root / "test.md"
                test_file.write_text("# Test\n\nContent")

                changed_files = [
                    {
                        "abs_path": test_file,
                        "rel_path": "test.md",
                        "project_root": project_root,
                    }
                ]

                candidates = extractor.extract_from_files(changed_files)

                # 应该降级为 unrefined
                assert len(candidates) == 1
                assert candidates[0].unrefined is True

    def test_extractor_project_specific_confidence_reduction(self):
        """Test: 项目专属候选置信度降低"""
        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            extractor = LLMExtractor(config)

            # Mock 成功响应
            from memory_core.evolution.extractor import LLMCallResult

            mock_result = LLMCallResult(
                content=json.dumps(
                    [
                        {
                            "title": "Project Specific",
                            "domain": "engineering",
                            "content": "This is project-specific content",
                            "confidence": 0.9,
                            "source_refs": [{"project": "proj1", "path": "file.md"}],
                            "genericity": "项目专属",
                        }
                    ]
                ),
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            )

            extractor._engine = Mock()
            extractor._engine.chat_completion.return_value = mock_result

            with tempfile.TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                test_file = project_root / "test.md"
                test_file.write_text("# Test\n\nContent")

                changed_files = [
                    {
                        "abs_path": test_file,
                        "rel_path": "test.md",
                        "project_root": project_root,
                    }
                ]

                candidates = extractor.extract_from_files(changed_files)

                # 项目专属候选的置信度应该被降低
                assert len(candidates) == 1
                assert candidates[0].genericity == "项目专属"
                assert candidates[0].confidence <= 0.5

    def test_extractor_tracking(self):
        """Test: token 和调用次数追踪"""
        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            extractor = LLMExtractor(config)

            # Mock 成功响应
            from memory_core.evolution.extractor import LLMCallResult

            mock_result = LLMCallResult(
                content=json.dumps(
                    [
                        {
                            "title": "Test",
                            "domain": "engineering",
                            "content": "Content",
                            "confidence": 0.8,
                            "source_refs": [],
                            "genericity": "通用",
                        }
                    ]
                ),
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
            )

            extractor._engine = Mock()
            extractor._engine.chat_completion.return_value = mock_result

            with tempfile.TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                test_file = project_root / "test.md"
                test_file.write_text("# Test\n\nContent")

                changed_files = [
                    {
                        "abs_path": test_file,
                        "rel_path": "test.md",
                        "project_root": project_root,
                    }
                ]

                extractor.extract_from_files(changed_files)

                assert extractor.tokens_used == 300
                assert extractor.llm_calls == 1


    def test_prompt_includes_project_context(self):
        """Test: LLM prompt 包含项目名与路径（项目上下文传递）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "my-cool-project"
            project_root.mkdir()
            test_file = project_root / "lesson.md"
            test_file.write_text("# Lesson\n\nContent here")

            changed_files = [
                {
                    "abs_path": test_file,
                    "rel_path": "lesson.md",
                    "project_root": project_root,
                }
            ]

            prompt = _build_user_prompt(changed_files, project_root)

            # 必须包含项目名称和路径
            assert "my-cool-project" in prompt, "prompt 缺少项目名"
            assert str(project_root) in prompt, "prompt 缺少项目路径"
            assert "项目名称" in prompt or "project" in prompt.lower()

    def test_batch_failure_isolation(self):
        """Test: 第二批 API 失败不丢弃第一批已精炼候选（批次级错误隔离）"""
        from memory_core.evolution.extractor import LLMCallResult

        config = {"llm": {"api_key_env": "TEST_KEY"}}
        with patch.dict(os.environ, {"TEST_KEY": "test-key"}):
            extractor = LLMExtractor(config)

            call_count = [0]

            def mock_chat_completion(messages):
                call_count[0] += 1
                if call_count[0] == 1:
                    return LLMCallResult(
                        content=json.dumps(
                            [
                                {
                                    "title": "Refined Insight",
                                    "domain": "engineering",
                                    "content": "A well-distilled cross-project lesson",
                                    "confidence": 0.9,
                                    "source_refs": [{"project": "proj", "path": "file.md"}],
                                    "genericity": "通用",
                                }
                            ]
                        ),
                        prompt_tokens=100,
                        completion_tokens=200,
                        total_tokens=300,
                    )
                raise RuntimeError("API batch 2 failed")

            extractor._engine = Mock()
            extractor._engine.chat_completion.side_effect = mock_chat_completion

            with tempfile.TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                # 创建 15 个文件确保分两批（batch_size=10）
                for i in range(15):
                    f = project_root / f"file_{i:02d}.md"
                    f.write_text(f"# Lesson {i}\n\nContent {i}")

                changed_files = [
                    {
                        "abs_path": project_root / f"file_{i:02d}.md",
                        "rel_path": f"file_{i:02d}.md",
                        "project_root": project_root,
                    }
                    for i in range(15)
                ]

                candidates = extractor.extract_from_files(changed_files)

                # 第一批应有 1 个精炼候选
                refined = [c for c in candidates if not c.unrefined]
                unrefined = [c for c in candidates if c.unrefined]
                assert len(refined) >= 1, "第一批精炼候选被丢弃！"
                assert refined[0].title == "Refined Insight"
                # 第二批应有降级候选
                assert len(unrefined) > 0, "第二批应降级为 unrefined"
                assert call_count[0] == 2


# ---------------------------------------------------------------------------
# Integration tests with CLI
# ---------------------------------------------------------------------------


class TestLLMExtractorCLI:
    """测试 LLM 提取器与 CLI 的集成"""

    def test_cli_run_with_llm(self):
        """Test: CLI run 命令使用 LLM"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # 创建临时项目
            project_root = tmpdir / "project"
            project_root.mkdir()
            lessons_dir = project_root / "memory" / "kb" / "lessons"
            lessons_dir.mkdir(parents=True)

            test_file = lessons_dir / "test.md"
            test_file.write_text("# Test Lesson\n\nThis is a test lesson.")

            # 创建临时全局库根
            global_kb_root = tmpdir / "global_kb"
            global_kb_root.mkdir()

            # 创建临时 evolution 根
            evolution_root = tmpdir / "evolution"
            evolution_root.mkdir()

            env = os.environ.copy()
            env["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_kb_root)
            env["MEMORY_CORE_EVOLUTION_ROOT"] = str(evolution_root)
            env["TEST_API_KEY"] = "test-key"

            # 运行 CLI（不使用 LLM，因为测试环境没有真实 API）
            # cwd 通过 __file__ 推导仓库根，不硬编码绝对路径
            _llm_test_repo_root = Path(__file__).resolve().parent.parent
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "memory_core.tools.evolve_cli",
                    "run",
                    "--project",
                    str(project_root),
                    "--no-llm",
                ],
                cwd=str(_llm_test_repo_root),
                capture_output=True,
                text=True,
                env=env,
            )

            assert result.returncode == 0
            assert "报告已写入" in result.stderr or result.returncode == 0
