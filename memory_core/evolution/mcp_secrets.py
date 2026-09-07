"""
共享 MCP JSON-RPC 客户端（memory_core/evolution/mcp_secrets.py）

从 extractor.py 抽取的 MCP 凭证解析逻辑，供备份脚本和 extractor 复用。
功能：
- 读 ~/.factory/mcp.json 解析 1password-connect 条目（URL + apikey 头）
- SSE 帧解析（event: message + data: {json}、纯 JSON）
- MCP 初始化握手（session_id 提取）
- resolve_secret: 完整 op:// 引用解析链

架构 §0 + M3 备份凭证 MCP 化

注意：apikey 头只存 mcp.json 不进 config；api_key_mcp_url 显式非空时用该 URL 解析
（修正 extractor.py:79 footgun：旧逻辑 `if not api_key_mcp_url` 门控导致显式 URL 跳过 MCP）
"""

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def parse_op_ref(op_ref: str) -> tuple[str, str, str] | None:
    """
    解析 op://vault_id/item_id/field_label 三段引用

    Args:
        op_ref: op:// 引用（如 op://vault_id/item_id/field_label）

    Returns:
        (vault_id, item_id, field_label) 元组，解析失败返回 None
    """
    if not op_ref or not isinstance(op_ref, str):
        return None

    op_ref = op_ref.strip()
    if not op_ref.startswith("op://"):
        return None

    # 去掉 op:// 前缀，然后按 / 分割
    remainder = op_ref[5:]  # len("op://") == 5
    parts = remainder.split("/")
    if len(parts) < 3:
        return None

    vault_id = parts[0]
    item_id = parts[1]
    field_label = parts[2]

    if not vault_id or not item_id or not field_label:
        return None

    return (vault_id, item_id, field_label)


def parse_sse_response(response_data: str) -> dict[str, Any] | None:
    """
    解析 SSE 响应（event: message + data: {json}）或纯 JSON

    Args:
        response_data: HTTP 响应体（可能是 SSE 格式或纯 JSON）

    Returns:
        解析后的字典，失败返回 None
    """
    if not response_data:
        return None

    # 尝试解析为 SSE 格式
    for line in response_data.split("\n"):
        if line.startswith("data: "):
            json_str = line[6:].strip()
            if json_str:
                try:
                    result = json.loads(json_str)
                    return result if isinstance(result, dict) else None
                except json.JSONDecodeError:
                    continue

    # 尝试解析为纯 JSON
    try:
        result = json.loads(response_data)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def read_mcp_config(mcp_config_path: Path | None = None) -> tuple[str, str]:
    """
    读取 ~/.factory/mcp.json 的 1password-connect 条目

    Args:
        mcp_config_path: mcp.json 路径（测试用），默认 ~/.factory/mcp.json

    Returns:
        (url, apikey) 元组，条目不存在或解析失败返回 ("", "")
    """
    if mcp_config_path is None:
        mcp_config_path = Path.home() / ".factory" / "mcp.json"

    if not mcp_config_path.exists():
        return ("", "")

    try:
        with mcp_config_path.open(encoding="utf-8") as f:
            mcp_config = json.load(f)

        servers = mcp_config.get("mcpServers", {})
        entry = servers.get("1password-connect", {})
        if not entry:
            return ("", "")

        url = entry.get("url", "")

        # apikey 可能在 headers 字典下，也可能直接在顶层
        apikey = entry.get("apikey", "")
        if not apikey:
            headers = entry.get("headers", {})
            if isinstance(headers, dict):
                apikey = headers.get("apikey", "")

        return (url, apikey)

    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return ("", "")


class McpSecretResolver:
    """
    MCP 密钥解析器

    通过 1password MCP（HTTP）解析 op:// 引用：
    1. 初始化握手（获取 session_id）
    2. 调用 read_secret 工具（vault_id/item_id/field_label 三段）
    3. 提取响应中的 text 内容

    密钥不落盘、不进日志。
    """

    def __init__(
        self,
        mcp_url: str,
        apikey: str,
        timeout: int = 10,
    ):
        """
        Args:
            mcp_url: MCP 端点 URL（如 http://example.com:9080/mcp/1password）
            apikey: MCP apikey 头值
            timeout: HTTP 超时（秒）
        """
        self.mcp_url = mcp_url
        self.apikey = apikey
        self.timeout = timeout
        # 允许测试覆盖 urlopen
        self._urlopen = urllib.request.urlopen

    def resolve_secret(self, op_ref: str) -> str | None:
        """
        解析 op:// 引用，返回密钥值

        Args:
            op_ref: op:// 引用（如 op://vault_id/item_id/field_label）

        Returns:
            解析出的密钥值，失败返回 None
        """
        parsed = parse_op_ref(op_ref)
        if not parsed:
            return None

        vault_id, item_id, field_label = parsed

        try:
            # 1. 初始化握手
            session_id = self._initialize()
            if not session_id:
                return None

            # 2. 调用 read_secret
            call_response = self._call_tool(
                session_id,
                "read_secret",
                {
                    "vault_id": vault_id,
                    "item_id": item_id,
                    "field_label": field_label,
                },
            )
            if not call_response:
                return None

            # 3. 提取结果
            return self._extract_text(call_response)

        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, TimeoutError, OSError):
            return None

    def _initialize(self) -> str | None:
        """执行 MCP 初始化握手，返回 session_id"""
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "memory-core", "version": "1.0"},
            },
        }

        init_data = json.dumps(init_request).encode("utf-8")
        init_req = urllib.request.Request(
            self.mcp_url,
            data=init_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "apikey": self.apikey,
            },
            method="POST",
        )

        with self._urlopen(init_req, timeout=self.timeout) as response:
            init_response_data = response.read().decode("utf-8")
            session_id = response.headers.get("Mcp-Session-Id", "")

            # 验证响应
            parsed = parse_sse_response(init_response_data)
            if not parsed or "error" in parsed:
                return None

            return session_id if session_id else None

    def _call_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """调用 MCP 工具，返回响应"""
        call_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        call_data = json.dumps(call_request).encode("utf-8")
        call_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "apikey": self.apikey,
        }
        if session_id:
            call_headers["Mcp-Session-Id"] = session_id

        call_req = urllib.request.Request(
            self.mcp_url,
            data=call_data,
            headers=call_headers,
            method="POST",
        )

        with self._urlopen(call_req, timeout=self.timeout) as response:
            call_response_data = response.read().decode("utf-8")
            return parse_sse_response(call_response_data)

    def _extract_text(self, response: dict[str, Any]) -> str | None:
        """从 MCP 响应中提取 text 内容

        错误处理：
        - 顶层 'error' 键存在 → 返回 None
        - result.isError 为真 → 返回 None（MCP 协议错误标志）
        - 提取的文本以 'Error' 开头 → 返回 None（防止错误文本被当作密钥返回）
        """
        # 检查错误响应
        if "error" in response:
            return None

        if "result" not in response:
            return None

        result = response["result"]

        # 检查 result.isError 标志（MCP 协议错误指示）
        if result.get("isError", False):
            return None

        content = result.get("content", [])
        if not content or not isinstance(content, list):
            return None

        for item_data in content:
            if item_data.get("type") == "text":
                text_value = item_data.get("text", "")
                text = str(text_value).strip() if text_value else None
                # 防止错误文本被当作密钥返回（如 "Error: Item not found"）
                if text and text.startswith("Error"):
                    return None
                return text

        return None


def resolve_via_mcp(
    mcp_url: str,
    apikey: str,
    op_ref: str,
    timeout: int = 10,
) -> str | None:
    """
    便捷函数：通过 MCP 解析 op:// 引用

    Args:
        mcp_url: MCP 端点 URL
        apikey: MCP apikey 头值
        op_ref: op:// 引用
        timeout: HTTP 超时（秒）

    Returns:
        解析出的密钥值，失败返回 None
    """
    resolver = McpSecretResolver(mcp_url, apikey, timeout)
    return resolver.resolve_secret(op_ref)
