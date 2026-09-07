"""
Tests for memory_core.evolution.mcp_secrets — 共享 MCP JSON-RPC 客户端

覆盖：
- read_mcp_config: 读 ~/.factory/mcp.json 解析 1password-connect 条目
- SSE 帧解析（event: message + data: {json}、纯 JSON）
- MCP 初始化握手（session_id 提取）
- resolve_secret: 完整 op:// 引用解析链
- resolve_api_key 语义修正（api_key_mcp_url 显式非空时使用该 URL）
- parse_op_ref: op://vault/item/field 三段解析
"""

import json
from unittest.mock import MagicMock, patch

from memory_core.evolution.mcp_secrets import (
    McpSecretResolver,
    parse_op_ref,
    parse_sse_response,
    read_mcp_config,
)


class TestParseOpRef:
    """op:// 引用解析"""

    def test_valid_op_ref(self):
        """标准 op://vault/item/field 三段"""
        vault, item, field = parse_op_ref("op://ozqqpvh5yvvxvyu64npq62a3ti/arh3eyylx2snevicwvb3px7iui/api_key")
        assert vault == "ozqqpvh5yvvxvyu64npq62a3ti"
        assert item == "arh3eyylx2snevicwvb3px7iui"
        assert field == "api_key"

    def test_valid_op_ref_r2_fields(self):
        """R2 凭证字段解析"""
        for field_name in ["ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "password", "S3_ENDPOINT"]:
            vault, item, field = parse_op_ref(
                f"op://ozqqpvh5yvvxvyu64npq62a3ti/zchdyrqaykfx6icgs6xuamrfym/{field_name}"
            )
            assert vault == "ozqqpvh5yvvxvyu64npq62a3ti"
            assert item == "zchdyrqaykfx6icgs6xuamrfym"
            assert field == field_name

    def test_invalid_prefix(self):
        """非 op:// 前缀返回 None"""
        assert parse_op_ref("https://example.com") is None
        assert parse_op_ref("vault/item/field") is None

    def test_too_few_parts(self):
        """段数不足返回 None"""
        assert parse_op_ref("op://vault/item") is None
        assert parse_op_ref("op://vault") is None

    def test_empty_string(self):
        """空字符串返回 None"""
        assert parse_op_ref("") is None
        assert parse_op_ref("  ") is None


class TestParseSseResponse:
    """SSE 帧解析"""

    def test_pure_json(self):
        """纯 JSON 响应"""
        data = '{"result": {"content": [{"type": "text", "text": "hello"}]}}'
        result = parse_sse_response(data)
        assert result is not None
        assert result["result"]["content"][0]["text"] == "hello"

    def test_sse_format(self):
        """SSE 格式（event: message + data: {json}）"""
        data = 'event: message\ndata: {"result": {"content": [{"type": "text", "text": "value"}]}}\n\n'
        result = parse_sse_response(data)
        assert result is not None
        assert result["result"]["content"][0]["text"] == "value"

    def test_sse_with_extra_lines(self):
        """SSE 含多余行"""
        data = 'event: message\nid: 123\ndata: {"id": 1, "result": "ok"}\n\n'
        result = parse_sse_response(data)
        assert result is not None
        assert result["result"] == "ok"

    def test_invalid_json_returns_none(self):
        """无效 JSON 返回 None"""
        assert parse_sse_response("not json at all") is None
        assert parse_sse_response("data: not-json\n\n") is None

    def test_empty_data_returns_none(self):
        """空输入返回 None"""
        assert parse_sse_response("") is None
        assert parse_sse_response("   ") is None

    def test_non_dict_json_returns_none(self):
        """非字典 JSON 返回 None"""
        assert parse_sse_response("[1, 2, 3]") is None
        assert parse_sse_response('"string"') is None


class TestReadMcpConfig:
    """读 mcp.json 配置"""

    def test_read_1password_connect(self, tmp_path):
        """正确解析 1password-connect 条目"""
        mcp_json = {
            "mcpServers": {
                "1password-connect": {
                    # BOUNDARY 4.3：测试夹具用 localhost dummy，禁止硬编码业务内网 IP
                    "url": "http://localhost:9080/mcp/1password",
                    "headers": {"apikey": "test-api-key-12345"},
                    "type": "http",
                }
            }
        }
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps(mcp_json))

        url, apikey = read_mcp_config(config_path)
        assert url == "http://localhost:9080/mcp/1password"
        assert apikey == "test-api-key-12345"

    def test_apikey_at_top_level(self, tmp_path):
        """apikey 在条目顶层（非 headers 内）"""
        mcp_json = {
            "mcpServers": {
                "1password-connect": {
                    "url": "http://example.com/mcp",
                    "apikey": "top-level-key",
                }
            }
        }
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps(mcp_json))

        url, apikey = read_mcp_config(config_path)
        assert url == "http://example.com/mcp"
        assert apikey == "top-level-key"

    def test_missing_entry_returns_empty(self, tmp_path):
        """无 1password-connect 条目返回空字符串"""
        mcp_json = {"mcpServers": {"other": {"url": "http://other.com"}}}
        config_path = tmp_path / "mcp.json"
        config_path.write_text(json.dumps(mcp_json))

        url, apikey = read_mcp_config(config_path)
        assert url == ""
        assert apikey == ""

    def test_missing_file_returns_empty(self, tmp_path):
        """文件不存在返回空字符串"""
        config_path = tmp_path / "nonexistent.json"
        url, apikey = read_mcp_config(config_path)
        assert url == ""
        assert apikey == ""

    def test_invalid_json_returns_empty(self, tmp_path):
        """无效 JSON 返回空字符串"""
        config_path = tmp_path / "mcp.json"
        config_path.write_text("not valid json")

        url, apikey = read_mcp_config(config_path)
        assert url == ""
        assert apikey == ""


class TestMcpSecretResolver:
    """MCP 密钥解析器"""

    def _make_resolver_with_stub(self, url: str, apikey: str, response_text: str) -> McpSecretResolver:
        """创建带 stub HTTP 响应的解析器"""
        resolver = McpSecretResolver(mcp_url=url, apikey=apikey)

        # Mock urlopen for both initialize and tool call
        init_response_data = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "1password", "version": "1.0"},
                },
            }
        )

        tool_response_data = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "content": [{"type": "text", "text": response_text}],
                },
            }
        )

        call_count = 0

        def mock_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 1:
                mock_resp.read.return_value = init_response_data.encode("utf-8")
                mock_resp.headers = {"Mcp-Session-Id": "test-session-123"}
                mock_resp.__enter__ = lambda s: s
                mock_resp.__exit__ = MagicMock(return_value=False)
            else:
                mock_resp.read.return_value = tool_response_data.encode("utf-8")
                mock_resp.headers = {}
                mock_resp.__enter__ = lambda s: s
                mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        resolver._urlopen = mock_urlopen
        return resolver

    def test_resolve_secret_success(self):
        """成功解析 op:// 引用"""
        resolver = self._make_resolver_with_stub(
            url="http://test:9080/mcp/1password",
            apikey="test-key",
            response_text="resolved-secret-value",
        )

        result = resolver.resolve_secret("op://vault123/item456/api_key")
        assert result == "resolved-secret-value"

    def test_resolve_secret_invalid_ref(self):
        """无效 op:// 引用返回 None"""
        resolver = McpSecretResolver(mcp_url="http://test:9080", apikey="key")
        assert resolver.resolve_secret("invalid-ref") is None
        assert resolver.resolve_secret("") is None

    def test_resolve_secret_mcp_error_response(self):
        """MCP 返回错误响应时返回 None"""
        resolver = McpSecretResolver(mcp_url="http://test:9080", apikey="key")

        error_response = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "error": {"code": -32000, "message": "Secret not found"},
            }
        )

        call_count = 0

        def mock_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 1:
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}},
                    }
                ).encode("utf-8")
                mock_resp.headers = {"Mcp-Session-Id": "sess"}
            else:
                mock_resp.read.return_value = error_response.encode("utf-8")
                mock_resp.headers = {}
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        resolver._urlopen = mock_urlopen
        result = resolver.resolve_secret("op://vault/item/field")
        assert result is None

    def test_resolve_secret_network_error(self):
        """网络错误时返回 None（不抛异常）"""
        import urllib.error

        resolver = McpSecretResolver(mcp_url="http://unreachable:9999", apikey="key")

        def mock_urlopen(req, timeout=10):
            raise urllib.error.URLError("Connection refused")

        resolver._urlopen = mock_urlopen
        result = resolver.resolve_secret("op://vault/item/field")
        assert result is None

    def test_resolve_secret_is_error_flag(self):
        """result.isError 为真时返回 None（MCP 协议错误标志）"""
        resolver = McpSecretResolver(mcp_url="http://test:9080", apikey="key")

        error_response = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": "Error: Item not found"}],
                },
            }
        )

        call_count = 0

        def mock_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 1:
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}},
                    }
                ).encode("utf-8")
                mock_resp.headers = {"Mcp-Session-Id": "sess"}
            else:
                mock_resp.read.return_value = error_response.encode("utf-8")
                mock_resp.headers = {}
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        resolver._urlopen = mock_urlopen
        result = resolver.resolve_secret("op://vault/item/field")
        assert result is None, "isError=True 时应返回 None"

    def test_resolve_secret_error_prefix_text(self):
        """文本以 'Error' 开头时返回 None（防止错误文本被当作密钥）"""
        resolver = McpSecretResolver(mcp_url="http://test:9080", apikey="key")

        error_text_response = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "content": [{"type": "text", "text": "Error: Secret not found in vault"}],
                },
            }
        )

        call_count = 0

        def mock_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 1:
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}},
                    }
                ).encode("utf-8")
                mock_resp.headers = {"Mcp-Session-Id": "sess"}
            else:
                mock_resp.read.return_value = error_text_response.encode("utf-8")
                mock_resp.headers = {}
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        resolver._urlopen = mock_urlopen
        result = resolver.resolve_secret("op://vault/item/field")
        assert result is None, "Error 前缀文本应返回 None"

    def test_resolve_secret_validates_three_parameters(self):
        """read_secret 收到解析后的 vault_id/item_id/field_label 三段参数（SKILL 硬约束 8）"""
        received_args = {}

        def mock_urlopen(req, timeout=10):
            mock_resp = MagicMock()
            request_data = json.loads(req.data.decode())

            if request_data.get("method") == "initialize":
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}},
                    }
                ).encode("utf-8")
                mock_resp.headers = {"Mcp-Session-Id": "sess-123"}
            elif request_data.get("method") == "tools/call":
                # 捕获 read_secret 收到的参数
                params = request_data.get("params", {})
                received_args["tool_name"] = params.get("name")
                received_args["arguments"] = params.get("arguments", {})
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {"content": [{"type": "text", "text": "secret-value-xyz"}]},
                    }
                ).encode("utf-8")
                mock_resp.headers = {}
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        resolver = McpSecretResolver(mcp_url="http://test:9080", apikey="key")
        resolver._urlopen = mock_urlopen

        result = resolver.resolve_secret("op://vault-abc/item-def/field-ghi")

        # 验证 read_secret 收到三段参数（不是整串 op://）
        assert received_args["tool_name"] == "read_secret"
        assert received_args["arguments"]["vault_id"] == "vault-abc"
        assert received_args["arguments"]["item_id"] == "item-def"
        assert received_args["arguments"]["field_label"] == "field-ghi"
        assert result == "secret-value-xyz"


class TestResolveApiKeySemantics:
    """
    测试 api_key_mcp_url 语义修正（orchestrator 追加缺陷修复）

    旧行为（footgun）：api_key_mcp_url 显式非空 → 跳过 MCP 解析块
    新行为（修正后）：api_key_mcp_url 显式非空 → 用该 URL 解析，apikey 仍从 mcp.json 读
    """

    def test_explicit_mcp_url_uses_that_url(self, tmp_path):
        """显式设置 api_key_mcp_url（非空）时，使用该 URL 解析"""
        # 创建临时 mcp.json（提供 apikey）
        mcp_json = {
            "mcpServers": {
                "1password-connect": {
                    "url": "http://default-url:9080/mcp",
                    "headers": {"apikey": "mcp-json-apikey"},
                }
            }
        }
        mcp_config_path = tmp_path / "mcp.json"
        mcp_config_path.write_text(json.dumps(mcp_json))

        # 配置：显式 URL + op_ref
        config = {
            "llm": {
                "api_key_env": "NONEXISTENT_ENV_VAR_FOR_TEST",
                "api_key_op_ref": "op://vault/item/api_key",
                "api_key_mcp_url": "http://explicit-url:9080/mcp",
            }
        }

        # Mock: 清空环境变量 + mock urlopen 追踪 URL
        called_urls = []

        def mock_urlopen(req, timeout=10):
            called_urls.append(req.full_url)
            mock_resp = MagicMock()
            if "initialize" in req.data.decode():
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}},
                    }
                ).encode("utf-8")
                mock_resp.headers = {"Mcp-Session-Id": "sess"}
            else:
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {"content": [{"type": "text", "text": "resolved-key-12345"}]},
                    }
                ).encode("utf-8")
                mock_resp.headers = {}
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch.dict("os.environ", {}, clear=False):
            # 确保环境变量不存在
            import os

            os.environ.pop("NONEXISTENT_ENV_VAR_FOR_TEST", None)

            with (
                patch("urllib.request.urlopen", side_effect=mock_urlopen),
                patch("memory_core.evolution.extractor._MCP_CONFIG_PATH", mcp_config_path),
            ):
                from memory_core.evolution.extractor import resolve_api_key

                key = resolve_api_key(config)

        assert key == "resolved-key-12345"
        # 验证使用了显式 URL 而非 mcp.json 的默认 URL
        assert any("explicit-url" in url for url in called_urls), f"应使用显式 URL，实际调用: {called_urls}"

    def test_empty_mcp_url_reads_from_mcp_json(self, tmp_path):
        """api_key_mcp_url 为空时，从 mcp.json 读取 URL"""
        mcp_json = {
            "mcpServers": {
                "1password-connect": {
                    "url": "http://mcp-json-url:9080/mcp",
                    "headers": {"apikey": "mcp-json-apikey"},
                }
            }
        }
        mcp_config_path = tmp_path / "mcp.json"
        mcp_config_path.write_text(json.dumps(mcp_json))

        config = {
            "llm": {
                "api_key_env": "NONEXISTENT_ENV_VAR_FOR_TEST",
                "api_key_op_ref": "op://vault/item/api_key",
                "api_key_mcp_url": "",
            }
        }

        called_urls = []

        def mock_urlopen(req, timeout=10):
            called_urls.append(req.full_url)
            mock_resp = MagicMock()
            if b"initialize" in req.data:
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}},
                    }
                ).encode("utf-8")
                mock_resp.headers = {"Mcp-Session-Id": "sess"}
            else:
                mock_resp.read.return_value = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {"content": [{"type": "text", "text": "resolved-key-via-mcpjson"}]},
                    }
                ).encode("utf-8")
                mock_resp.headers = {}
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("NONEXISTENT_ENV_VAR_FOR_TEST", None)

            with (
                patch("urllib.request.urlopen", side_effect=mock_urlopen),
                patch("memory_core.evolution.extractor._MCP_CONFIG_PATH", mcp_config_path),
            ):
                from memory_core.evolution.extractor import resolve_api_key

                key = resolve_api_key(config)

        assert key == "resolved-key-via-mcpjson"
        # 验证使用了 mcp.json 的 URL
        assert any("mcp-json-url" in url for url in called_urls), f"应使用 mcp.json URL，实际调用: {called_urls}"
