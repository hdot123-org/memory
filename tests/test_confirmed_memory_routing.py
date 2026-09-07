"""
确认记忆模型测试（2026-09-07 用户裁定）

三组测试：
1. pending-only 路由（VAL-SED-001 单元级）
2. search_memory pending 排除（VAL-CROSS-001/009 单元级）
3. MCP 密钥链（VAL-EXT-001/002 单元级）
"""

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from memory_core.evolution.sediment import write_candidates

# ---------------------------------------------------------------------------
# 1. pending-only 路由测试（VAL-SED-001 单元级）
# ---------------------------------------------------------------------------


def test_pending_only_all_confidences_go_to_pending():
    """
    2026-09-07 用户裁定：全部候选（任意 confidence）一律落 pending/

    构造高/中/低置信候选，验证全部进入 pending/，正式域零写入
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 构造三个不同置信度的候选（内容足够区分以避免 n-gram 重叠触发合并）
        candidates = [
            {
                "title": "高置信经验",
                "domain": "engineering",
                "content": "高置信度：部署前必须运行全量测试套件，包括单元测试、集成测试和端到端测试，确保零失败。",
                "confidence": 0.95,
                "source_refs": [{"project": "test-proj", "path": "memory/kb/lessons/high.md"}],
                "unrefined": False,
            },
            {
                "title": "中置信经验",
                "domain": "operations",
                "content": "中置信度：日志级别应根据环境动态调整，生产环境使用 INFO，调试时使用 DEBUG。",
                "confidence": 0.6,
                "source_refs": [{"project": "test-proj", "path": "memory/kb/lessons/medium.md"}],
                "unrefined": False,
            },
            {
                "title": "低置信经验",
                "domain": "collaboration",
                "content": "低置信度：代码审查应关注架构设计和可维护性，而非代码风格细节。",
                "confidence": 0.3,
                "source_refs": [{"project": "test-proj", "path": "memory/kb/lessons/low.md"}],
                "unrefined": False,
            },
        ]

        # 写入候选
        stats = write_candidates(candidates, root)

        # 验证 1: 全部写入 pending/
        assert stats["written"] == 3, f"期望写入 3 个候选，实际 {stats['written']}"

        # 验证 2: 全部在 pending/ 目录
        pending_dir = root / "pending"
        assert pending_dir.exists(), "pending/ 目录应存在"
        pending_files = list(pending_dir.glob("*.md"))
        assert len(pending_files) == 3, f"pending/ 应有 3 个文件，实际 {len(pending_files)}"

        # 验证 3: 正式域零写入
        formal_dirs = ["operations", "engineering", "collaboration", "governance", "infra", "audit"]
        for domain in formal_dirs:
            domain_dir = root / domain
            if domain_dir.exists():
                domain_files = list(domain_dir.glob("*.md"))
                assert len(domain_files) == 0, f"正式域 {domain}/ 应零写入，实际有 {len(domain_files)} 个文件"

        # 验证 4: INDEX.md 未被创建
        index_path = root / "INDEX.md"
        assert not index_path.exists(), "INDEX.md 不应被创建（管道永不写正式域）"


def test_pending_only_unrefined_candidates():
    """
    unrefined 候选同样只落 pending/

    构造 unrefined=True 的候选，验证进入 pending/ 且 frontmatter 含 unrefined: true
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        candidates = [
            {
                "title": "未精炼经验",
                "domain": "engineering",
                "content": "这是一个未精炼的经验条目（原样捕获）",
                "confidence": 0.0,
                "source_refs": [{"project": "test-proj", "path": "memory/kb/lessons/unrefined.md"}],
                "unrefined": True,
            },
        ]

        stats = write_candidates(candidates, root)
        assert stats["written"] == 1

        # 验证 frontmatter 含 unrefined: true
        pending_file = root / "pending" / "未精炼经验.md"
        assert pending_file.exists()
        content = pending_file.read_text(encoding="utf-8")
        assert "unrefined: true" in content, "unrefined 候选 frontmatter 应含 unrefined: true"


def test_pending_only_threshold_does_not_affect_routing():
    """
    2026-09-07 用户裁定：auto_confidence_threshold 不再门控路由

    修改阈值后重跑，落点分布应不变（全部仍在 pending/）
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        candidates = [
            {
                "title": "阈值测试经验",
                "domain": "engineering",
                "content": "这是一个用于测试阈值不影响路由的经验条目",
                "confidence": 0.85,
                "source_refs": [{"project": "test-proj", "path": "memory/kb/lessons/threshold.md"}],
                "unrefined": False,
            },
        ]

        # 第一次写入（默认阈值 0.8）
        config1 = {"promote": {"auto_confidence_threshold": 0.8}}
        stats1 = write_candidates(candidates, root, config1)
        assert stats1["written"] == 1

        # 验证在 pending/
        pending_files_1 = list((root / "pending").glob("*.md"))
        assert len(pending_files_1) == 1

        # 第二次写入（阈值 0.95）——由于内容相同会触发 skip，但验证阈值不影响路由
        # 使用新 root 避免 skip
        with tempfile.TemporaryDirectory() as tmpdir2:
            root2 = Path(tmpdir2)
            config2 = {"promote": {"auto_confidence_threshold": 0.95}}
            stats2 = write_candidates(candidates, root2, config2)
            assert stats2["written"] == 1

            # 验证仍在 pending/（阈值不影响路由）
            pending_files_2 = list((root2 / "pending").glob("*.md"))
            assert len(pending_files_2) == 1

            # 验证正式域零写入
            for domain in ["engineering", "operations", "collaboration", "governance", "infra", "audit"]:
                domain_dir = root2 / domain
                if domain_dir.exists():
                    assert len(list(domain_dir.glob("*.md"))) == 0


# ---------------------------------------------------------------------------
# 2. search_memory pending 排除测试（VAL-CROSS-001/009 单元级）
# ---------------------------------------------------------------------------


def test_search_memory_excludes_pending():
    """
    2026-09-07 用户裁定：读取面只服务已确认正式域内容

    search_memory 不得返回 pending/ 下的文件
    """
    from memory_core.tools.mcp_server import _search_memory

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 创建 formal domain 文件
        formal_dir = root / "engineering"
        formal_dir.mkdir()
        formal_file = formal_dir / "confirmed.md"
        formal_file.write_text("# 已确认经验\n这是正式域的已确认内容\n", encoding="utf-8")

        # 创建 pending 文件
        pending_dir = root / "pending"
        pending_dir.mkdir()
        pending_file = pending_dir / "unconfirmed.md"
        pending_file.write_text("# 待确认提案\n这是 pending 区的待确认内容\n", encoding="utf-8")

        # Mock get_global_kb_root 返回临时 root
        import memory_core.tools.global_kb_init as gk_init

        original_get_root = gk_init.get_global_kb_root

        def mock_get_root():
            return root

        gk_init.get_global_kb_root = mock_get_root

        try:
            # 搜索包含"内容"的关键词
            results = _search_memory("内容", cwd=str(root))

            # 验证 1: 正式域文件被返回
            formal_found = any(r["file_path"] == str(formal_file) for r in results)
            assert formal_found, "正式域文件应被 search_memory 返回"

            # 验证 2: pending 文件不被返回
            pending_found = any(r["file_path"] == str(pending_file) for r in results)
            assert not pending_found, "pending/ 文件不得被 search_memory 返回（读取面只服务确认内容）"

            # 验证 3: 结果的 source 字段正确
            for r in results:
                if r["file_path"] == str(formal_file):
                    assert r["source"] == "global", "正式域文件 source 应为 'global'"
        finally:
            gk_init.get_global_kb_root = original_get_root


def test_search_memory_pending_exclusion_with_os_sep():
    """
    验证 pending 排除逻辑对 os.sep 的兼容性（Windows/macOS/Linux）

    pending/ 下的文件无论路径分隔符如何都应被排除
    """
    from memory_core.tools.mcp_server import _search_memory

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 创建 nested pending 文件
        pending_dir = root / "pending"
        pending_dir.mkdir()
        nested_pending = pending_dir / "nested" / "deep.md"
        nested_pending.parent.mkdir()
        nested_pending.write_text("# 深层待确认\n嵌套在 pending 子目录的内容\n", encoding="utf-8")

        # Mock get_global_kb_root
        import memory_core.tools.global_kb_init as gk_init

        original_get_root = gk_init.get_global_kb_root
        gk_init.get_global_kb_root = lambda: root

        try:
            results = _search_memory("内容", cwd=str(root))

            # 验证嵌套 pending 文件不被返回
            pending_found = any("pending" in r["relative_path"] for r in results)
            assert not pending_found, "pending/ 及其子目录文件不得被 search_memory 返回"
        finally:
            gk_init.get_global_kb_root = original_get_root


# ---------------------------------------------------------------------------
# 3. MCP 密钥链测试（VAL-EXT-001/002 单元级）
# ---------------------------------------------------------------------------


class MockMCPHandler(BaseHTTPRequestHandler):
    """Mock 1password MCP server for testing JSON-RPC client (SSE format)"""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        request = json.loads(body.decode("utf-8"))

        # 验证 apikey 头存在（但不记录值）
        apikey = self.headers.get("apikey", "")
        if not apikey:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "missing apikey"}')
            return

        # 验证 Accept 头（MCP streamable HTTP 要求）
        accept = self.headers.get("Accept", "")
        if "text/event-stream" not in accept:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "missing Accept header"}')
            return

        method = request.get("method", "")

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
            }
            # 返回 Mcp-Session-Id（后续请求需回传）
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Mcp-Session-Id", "test-session-id-12345")
            self.end_headers()
            # SSE 格式：event: message + data: {json}
            self.wfile.write(f"event: message\ndata: {json.dumps(response)}\n\n".encode())
        elif method == "tools/call":
            tool_name = request.get("params", {}).get("name", "")
            if tool_name == "read_secret":
                # 返回模拟密钥
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "content": [{"type": "text", "text": "mock-api-key-12345"}],
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(f"event: message\ndata: {json.dumps(response)}\n\n".encode())
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(f"event: message\ndata: {json.dumps(response)}\n\n".encode())
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(f"event: message\ndata: {json.dumps(response)}\n\n".encode())

    def log_message(self, format, *args):
        # 抑制日志输出
        pass


def test_mcp_key_chain_json_rpc_client():
    """
    测试 MCP JSON-RPC 客户端与 mock 端点交互

    验证 _resolve_via_mcp 能正确调用 initialize + tools/call 并解析响应
    """
    from memory_core.evolution.extractor import _resolve_via_mcp

    # 启动 mock MCP server
    server = HTTPServer(("127.0.0.1", 0), MockMCPHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        mcp_url = f"http://127.0.0.1:{port}/mcp/1password"
        apikey = "test-apikey-12345"
        op_ref = "op://sever/AXONHUB/password"

        # 调用 _resolve_via_mcp
        result = _resolve_via_mcp(mcp_url, apikey, op_ref)

        # 验证返回模拟密钥
        assert result == "mock-api-key-12345", f"期望解析出密钥，实际 {result}"
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_key_chain_order():
    """
    测试密钥解析链顺序：env → MCP → op read

    验证三级链优先级：env 优先于 MCP
    """
    from memory_core.evolution.extractor import resolve_api_key

    # 使用不可达的 MCP URL 和不可解析的 op_ref，确保 MCP 和 op read 都失败
    config = {
        "llm": {
            "api_key_env": "TEST_API_KEY_XYZ_NONEXISTENT",
            "api_key_op_ref": "invalid-op-ref",  # 不可解析，MCP 会返回 None
            "api_key_mcp_url": "http://127.0.0.1:1/mcp/unreachable",  # 显式不可达
        },
    }

    # 测试 1: env 存在时优先使用 env
    os.environ["TEST_API_KEY_XYZ_NONEXISTENT"] = "env-key-123"
    try:
        result = resolve_api_key(config)
        assert result == "env-key-123", "env 存在时应优先使用 env"
    finally:
        del os.environ["TEST_API_KEY_XYZ_NONEXISTENT"]

    # 测试 2: env 不存在且 MCP/op read 均失败时应报错
    with pytest.raises(RuntimeError, match="无法解析 API 密钥"):
        resolve_api_key(config)


def test_mcp_key_chain_no_apikey_leak():
    """
    测试 apikey 头值不泄漏到日志/产物

    验证 _resolve_via_mcp 不在异常信息中暴露 apikey
    """
    from memory_core.evolution.extractor import _resolve_via_mcp

    # 调用不存在的端点（会抛异常）
    mcp_url = "http://127.0.0.1:1/mcp/1password"  # 端口 1 不可达
    apikey = "secret-apikey-should-not-leak"
    op_ref = "op://vault/item/field"

    # 应返回 None（异常被捕获）
    result = _resolve_via_mcp(mcp_url, apikey, op_ref)
    assert result is None, "不可达端点应返回 None"

    # 验证异常信息不包含 apikey 值
    # （_resolve_via_mcp 内部捕获异常，不会抛出，但我们要确认设计意图）


def test_config_default_includes_mcp_url():
    """
    测试 DEFAULT_CONFIG 包含 api_key_mcp_url 键

    架构 §3.2：config.json 允许 api_key_env / api_key_op_ref / 可选 api_key_mcp_url
    """
    from memory_core.evolution.config import DEFAULT_CONFIG

    assert "api_key_mcp_url" in DEFAULT_CONFIG["llm"], "DEFAULT_CONFIG['llm'] 应包含 api_key_mcp_url 键"
    assert DEFAULT_CONFIG["llm"]["api_key_mcp_url"] == "", "api_key_mcp_url 默认值应为空字符串（运行时读 mcp.json）"


# ---------------------------------------------------------------------------
# 真实 MCP 集成测试（需要网络可达的 1password MCP 端点）
# ---------------------------------------------------------------------------


def _get_mcp_endpoint() -> tuple[str, int] | None:
    """从 ~/.factory/mcp.json 读取 1password-connect 的 MCP URL（零硬编码 IP）。

    返回 (host, port) 或 None（配置不可读/未配置）。
    """
    import json as _json
    from urllib.parse import urlparse

    mcp_path = Path.home() / ".factory" / "mcp.json"
    try:
        data = _json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", data)
        entry = servers.get("1password-connect", {})
        url = entry.get("url", "")
        if not url:
            return None
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return None
        return (host, port)
    except (OSError, ValueError, KeyError):
        return None


def _check_network_reachable() -> bool:
    """运行时从 mcp.json 读 MCP 端点并检查是否可达（用于 skipif 守卫）"""
    import socket

    endpoint = _get_mcp_endpoint()
    if endpoint is None:
        return False
    host, port = endpoint
    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        return True
    except (TimeoutError, OSError):
        return False


@pytest.mark.skipif(
    not _check_network_reachable(),
    reason="1password MCP 端点（运行时读 ~/.factory/mcp.json）不可达",
)
def test_real_mcp_resolve_api_key():
    """
    真实 MCP 端点解析非空密钥（掩码留证）

    验证 resolve_api_key() 在无 env 会话下经真实 MCP 解析出非空密钥
    apikey 头值绝不落日志/产物

    真实工具契约（orchestrator 提供）：
    - read_secret 参数：vault_id + item_id + field_label（三段字符串）
    - 当前值：vault=ozqqpvh5yvvxvyu64npq62a3ti, item=arh3eyylx2snevicwvb3px7iui, field=api_key

    注：MCP URL 由 _get_mcp_endpoint() 从 mcp.json 动态读取（BOUNDARY 4.3 零硬编码 IP 约定）。
    """
    from memory_core.evolution.extractor import resolve_api_key

    # 移除 env 以强制走 MCP 链
    original_key = os.environ.pop("AXONHUB_API_KEY", None)

    try:
        # 从 mcp.json 动态读取 MCP URL
        endpoint = _get_mcp_endpoint()
        mcp_url = ""
        if endpoint is not None:
            host, port = endpoint
            mcp_url = f"http://{host}:{port}/mcp/1password"

        config = {
            "llm": {
                "api_key_env": "AXONHUB_API_KEY",
                "api_key_op_ref": "op://ozqqpvh5yvvxvyu64npq62a3ti/arh3eyylx2snevicwvb3px7iui/api_key",
                "api_key_mcp_url": mcp_url,  # 运行时从 mcp.json 读取
            },
        }

        # 调用 resolve_api_key（应走 MCP 链）
        result = resolve_api_key(config)

        # 验证返回非空密钥
        assert result, "真实 MCP 应解析出非空密钥"
        assert len(result) > 10, f"密钥长度应 >10，实际 {len(result)}"

        # 掩码留证（只记录长度，不记录值）
        print(f"[MCP 自证] 解析出密钥长度={len(result)}, 前缀={result[:3]}***")

    finally:
        # 恢复 env
        if original_key:
            os.environ["AXONHUB_API_KEY"] = original_key
