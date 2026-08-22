#!/usr/bin/env python3.12
"""服务器/数据库检查与单项目编排（第 6 项的服务器侧 + audit_project）。

依赖层级：依赖 _audit_project（工具函数）、_audit_checks（检查 1-5）、
_audit_infra（SSH/TCP/systemd/磁盘）。
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from memory_core.constants import SYSTEM_DIR

try:
    from memory_core.ownership import is_memory_core_source_repo
except ImportError:  # pragma: no cover - 防御性回退
    is_memory_core_source_repo = None  # type: ignore[assignment]

from ._audit_checks import (
    check_global_residue,
    check_large_or_db_files,
    check_manifest_integrity,
    check_unsigned_files,
    check_version_consistency,
)
from ._audit_infra import (
    _check_systemd_services,
    _load_infra_inventory,
    _run_ssh,
    _tcp_connect_ok,
    check_disk_space,
    check_ssh_reachable,
)
from ._audit_project import (
    HTTP_TIMEOUT,
    MANIFEST_PATH_REL,
    TCP_TIMEOUT,
    _make_violation,
)

__all__ = [
    "_append_violation",
    "_check_server_ssh",
    "_check_server_docker",
    "_check_server_ports",
    "_check_server_http_endpoints",
    "check_server",
    "check_database",
    "check_infrastructure",
    "_load_infra_inventory",
    "_safe_check",
    "audit_project",
    "is_memory_core_source_repo",
]


def _append_violation(
    record: dict[str, Any],
    global_violations: list[dict[str, Any]],
    violation: dict[str, Any],
) -> None:
    """DRY helper: append violation to both record and global list."""
    record["violations"].append(violation)
    global_violations.append(violation)


def _check_server_ssh(
    server: dict[str, Any],
    record: dict[str, Any],
    global_violations: list[dict[str, Any]],
) -> bool | None:
    """Check SSH connectivity for server. Returns ssh_ok status."""
    name = str(server.get("name", "unknown"))
    host = str(record["host"])
    checks = server.get("checks") or {}
    ssh_alias = server.get("ssh_alias")
    want_ssh = bool(checks.get("ssh")) and bool(ssh_alias)

    ssh_ok: bool | None = None
    if want_ssh:
        ssh_ok = check_ssh_reachable(str(ssh_alias))
        record["ssh_ok"] = ssh_ok
        if not ssh_ok:
            v = _make_violation(
                "server_unreachable",
                "critical",
                f"{host} ({ssh_alias})",
                f"SSH 不可达：{ssh_alias}",
            )
            _append_violation(record, global_violations, v)
    elif ssh_alias is None and bool(checks.get("ssh")):
        # 声明了 ssh=true 但缺 ssh_alias
        v = _make_violation(
            "server_unreachable",
            "critical",
            name,
            "checks.ssh=true 但缺少 ssh_alias 字段",
        )
        _append_violation(record, global_violations, v)

    return ssh_ok


def _check_server_docker(
    server: dict[str, Any],
    record: dict[str, Any],
    global_violations: list[dict[str, Any]],
    ssh_ok: bool | None,
) -> None:
    """Check Docker container status (depends on SSH)."""
    name = str(server.get("name", "unknown"))
    ssh_alias = server.get("ssh_alias")
    checks = server.get("checks") or {}
    expected_containers = checks.get("docker_containers") or []

    if expected_containers and ssh_ok:
        # 注意：_run_ssh 将 remote_cmd 用空格拼接发给远端 shell，
        # format 串含空格必须用单引号包裹，否则 shell 会拆成两个参数。
        rc, out, _err = _run_ssh(
            str(ssh_alias),
            ["docker", "ps", "--format", "'{{.Names}}: {{.Status}}'"],
        )
        running: dict[str, str] = {}
        if rc == 0:
            for line in out.splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                cname, _, cstatus = line.partition(":")
                running[cname.strip()] = cstatus.strip()
        else:
            v = _make_violation(
                "container_down",
                "warning",
                f"{name} ({ssh_alias})",
                f"docker ps 执行失败 (rc={rc})，无法核对容器状态",
            )
            _append_violation(record, global_violations, v)

        # 对照期望列表
        for expected in expected_containers:
            expected = str(expected)
            status = running.get(expected)
            if status is None:
                record["containers"][expected] = "DOWN"
                v = _make_violation(
                    "container_down",
                    "critical",
                    f"{name}/{expected}",
                    f"期望容器未运行：{expected}",
                )
                _append_violation(record, global_violations, v)
            else:
                record["containers"][expected] = status
                low = status.lower()
                if "restarting" in low or "unhealthy" in low:
                    v = _make_violation(
                        "container_down",
                        "warning",
                        f"{name}/{expected}",
                        f"容器状态异常：{expected} -> {status}",
                    )
                    _append_violation(record, global_violations, v)
    # else: SSH 已失败或未配置 docker_containers，跳过


def _check_server_ports(
    server: dict[str, Any],
    record: dict[str, Any],
    global_violations: list[dict[str, Any]],
) -> None:
    """Check TCP port connectivity."""
    host = str(record["host"])
    checks = server.get("checks") or {}

    for port in checks.get("ports") or []:
        port = int(port)
        ok = _tcp_connect_ok(host, port, timeout=3)
        record["ports"][str(port)] = ok
        if not ok:
            v = _make_violation(
                "port_closed",
                "critical",
                f"{host}:{port}",
                f"端口 {port} 不可达（TCP connect 失败）",
            )
            _append_violation(record, global_violations, v)


def _check_server_http_endpoints(
    server: dict[str, Any],
    record: dict[str, Any],
    global_violations: list[dict[str, Any]],
) -> None:
    """Check HTTP endpoint health via curl."""
    checks = server.get("checks") or {}

    for ep in checks.get("http_endpoints") or []:
        if not isinstance(ep, dict):
            continue
        url = ep.get("url")
        ep_name = str(ep.get("name") or url)
        expected_status = int(ep.get("expected_status", 200))
        if not url:
            continue
        cmd = [
            "curl",
            "-sf",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            str(HTTP_TIMEOUT),
            str(url),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=HTTP_TIMEOUT + 2,
            )
            status_str = (result.stdout or "").strip()
            try:
                status_code = int(status_str) if status_str else 0
            except ValueError:
                status_code = 0
        except FileNotFoundError:
            status_code = -1
        except subprocess.TimeoutExpired:
            status_code = -2

        ep_record: dict[str, Any] = {
            "status": status_code,
            "expected": expected_status,
            "ok": status_code == expected_status,
        }
        record["http_endpoints"][ep_name] = ep_record

        if status_code == -2:
            v = _make_violation(
                "http_error",
                "critical",
                url,
                f"HTTP 端点超时（>{HTTP_TIMEOUT}s）：{ep_name}",
            )
            _append_violation(record, global_violations, v)
        elif status_code in (-1, 0):
            v = _make_violation(
                "http_error",
                "critical",
                url,
                f"HTTP 端点连接失败：{ep_name}",
            )
            _append_violation(record, global_violations, v)
        elif status_code != expected_status:
            v = _make_violation(
                "http_error",
                "warning",
                url,
                f"HTTP 状态码 {status_code} != 期望 {expected_status}：{ep_name}",
            )
            _append_violation(record, global_violations, v)


def check_server(
    server: dict[str, Any],
    global_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    """对单台服务器跑 SSH / Docker / 端口 / HTTP 检查。

    Args:
        server: inventory 里的一条 server 记录。
        global_violations: 累积违规列表（就地追加，便于汇总 total）。

    Returns:
        该服务器的检查结果子树（host / ssh_ok / containers / ports /
        http_endpoints / violations）。
    """
    host = str(server.get("host", ""))
    checks = server.get("checks") or {}

    record: dict[str, Any] = {
        "host": host,
        "ssh_ok": None,
        "containers": {},
        "ports": {},
        "http_endpoints": {},
        "disk_space": {},
        "violations": [],
    }

    ssh_alias = server.get("ssh_alias")

    # 6a. SSH 连通性
    ssh_ok = _check_server_ssh(server, record, global_violations)

    # 6b. Docker 容器（依赖 SSH 可达）
    _check_server_docker(server, record, global_violations, ssh_ok)

    # 6b2. systemd 服务状态（依赖 SSH 可达）
    expected_systemd = checks.get("systemd_services") or []
    if expected_systemd and ssh_ok:
        name = str(server.get("name", "unknown"))
        record["systemd_services"] = _check_systemd_services(
            ssh_alias=str(ssh_alias),
            server_name=name,
            services=[str(s) for s in expected_systemd],
            global_violations=global_violations,
            record_violations=record["violations"],
        )
    # else: SSH 已失败或未配置 systemd_services，跳过

    # 6b3. 磁盘空间检查（依赖 SSH 可达，防止磁盘满导致 MySQL/Docker 故障）
    disk_checks = checks.get("disk_space") or []
    if disk_checks and ssh_ok:
        name = str(server.get("name", "unknown"))
        normalized_checks: list[dict[str, Any]] = [{"path": d} if isinstance(d, str) else d for d in disk_checks]
        record["disk_space"] = check_disk_space(
            ssh_alias=str(ssh_alias),
            server_name=name,
            disk_checks=normalized_checks,
            global_violations=global_violations,
            record_violations=record["violations"],
        )
    # else: SSH 已失败或未配置 disk_space，跳过

    # 6c. 端口连通性（Python socket，超时 3s 贴合规格）
    _check_server_ports(server, record, global_violations)

    # 6d. HTTP 端点健康检查（curl）
    _check_server_http_endpoints(server, record, global_violations)

    return record


def check_database(
    database: dict[str, Any],
    global_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    """对单个数据库做 TCP connect 探测（6e）。"""
    name = str(database.get("name", "unknown"))
    host = str(database.get("host", ""))
    port = int(database.get("port", 0))

    record: dict[str, Any] = {
        "host": host,
        "port": port,
        "connect_ok": None,
        "violations": [],
    }

    # check 字段兼容 tcp_connect / mysql_ping（当前只实现 tcp_connect）
    check_kind = str(database.get("check", "tcp_connect")).lower()
    if check_kind != "tcp_connect":
        # 未支持的检查类型，按 warning 提示但不阻塞
        v = _make_violation(
            "db_unreachable",
            "warning",
            f"{host}:{port}",
            f"不支持的 database.check={check_kind}，仅支持 tcp_connect",
        )
        record["connect_ok"] = False
        record["violations"].append(v)
        global_violations.append(v)
        return record

    ok = _tcp_connect_ok(host, port, timeout=TCP_TIMEOUT)
    record["connect_ok"] = ok
    if not ok:
        v = _make_violation(
            "db_unreachable",
            "critical",
            f"{host}:{port}",
            f"数据库不可达：{name} ({host}:{port}) TCP connect 失败",
        )
        record["violations"].append(v)
        global_violations.append(v)

    return record


def check_infrastructure() -> dict[str, Any]:
    """执行基础设施健康检查（第 6 项），返回报告 infrastructure 子树。

    结构:
        {
          "servers": { "<name>": {...} },
          "databases": { "<name>": {...} },
          "violations": [...]   # 全部基础设施违规（便于汇总）
        }
    """
    result: dict[str, Any] = {
        "servers": {},
        "databases": {},
        "violations": [],
    }

    data = _load_infra_inventory()
    if data is None:
        return result

    # 服务器
    for server in data.get("servers") or []:
        if not isinstance(server, dict):
            continue
        name = str(server.get("name", "unknown"))
        result["servers"][name] = check_server(server, result["violations"])

    # 数据库
    for database in data.get("databases") or []:
        if not isinstance(database, dict):
            continue
        name = str(database.get("name", "unknown"))
        result["databases"][name] = check_database(database, result["violations"])

    return result


# ---------------------------------------------------------------------------
# 单项目编排
# ---------------------------------------------------------------------------


def _safe_check(check_fn: Callable[[], list[Any]], error_violation: Callable[[Exception], Any]) -> list[Any]:
    """Wrapper for check execution with error handling."""
    try:
        return check_fn()
    except Exception as e:
        return [error_violation(e)]


def audit_project(
    project_name: str,
    project_root: Path,
    global_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """对单个项目跑全部 5 项检查，返回报告子树。"""
    record: dict[str, Any] = {
        "path": str(project_root),
        "violations": [],
    }

    # 跳过不存在的项目路径
    if not project_root.exists():
        record["violations"].append(
            _make_violation(
                "hash_mismatch",
                "warning",
                str(project_root),
                "项目路径不存在（可能已删除），跳过",
            )
        )
        record["skipped"] = True
        return record

    # memory-core 自身是只读源仓库，不持有业务 KB，跳过 KB 相关检查和版本一致性检查
    # （源仓库的版本号由自身维护，跑版本检查会产生误报）
    # 此外，源仓库的完整性签名在设计上被禁用（sign_project 拒绝签名源仓库），
    # 因此 manifest.json 不存在是预期行为，跑完整性检查会产生 HASH_MISMATCH 误报。
    is_source_repo = is_memory_core_source_repo is not None and is_memory_core_source_repo(project_root.resolve())

    if not is_source_repo:
        checks = [
            (
                lambda: check_manifest_integrity(project_root),
                lambda e: _make_violation("hash_mismatch", "warning", MANIFEST_PATH_REL, f"检查异常：{e}"),
            ),
            (
                lambda: check_unsigned_files(project_root),
                lambda e: _make_violation("unsigned_file", "warning", "memory/kb/", f"检查异常：{e}"),
            ),
            (
                lambda: check_global_residue(project_root, global_fingerprints),
                lambda e: _make_violation("residue", "warning", "memory/kb/", f"检查异常：{e}"),
            ),
            (
                lambda: check_large_or_db_files(project_root),
                lambda e: _make_violation("large_file", "warning", str(project_root), f"检查异常：{e}"),
            ),
            (
                lambda: check_version_consistency(project_root),
                lambda e: _make_violation("version_mismatch", "warning", f"{SYSTEM_DIR}/", f"检查异常：{e}"),
            ),
        ]

        for check_fn, error_fn in checks:
            violations = _safe_check(check_fn, error_fn)
            record["violations"].extend(violations)

    if is_source_repo:
        record["note"] = "memory-core 源仓库：跳过完整性签名/KB未签名/残留/大文件检查"

    return record
