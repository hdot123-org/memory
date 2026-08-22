#!/usr/bin/env python3.12
"""基础设施检查（第 6 项）：清单加载、SSH、磁盘、systemd 服务。

依赖层级：依赖 _audit_project（常量与工具函数）。
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
from typing import Any

from ._audit_project import (
    INFRA_INVENTORY,
    SSH_CONNECT_TIMEOUT,
    SSH_TIMEOUT,
    TCP_TIMEOUT,
    _make_violation,
)

try:
    import yaml

    _HAS_YAML = True
except ImportError:  # pragma: no cover - 缺 PyYAML 时跳过基础设施检查
    yaml = None
    _HAS_YAML = False

__all__ = [
    # 经 _audit_project 引入并再导出的常量（基础设施清单 / 超时）
    "INFRA_INVENTORY",
    "SSH_TIMEOUT",
    "SSH_CONNECT_TIMEOUT",
    "TCP_TIMEOUT",
    "_load_infra_inventory",
    "_tcp_connect_ok",
    "_run_ssh",
    "check_ssh_reachable",
    "_parse_df_output",
    "_find_matching_mount",
    "check_disk_space",
    "_check_systemd_services",
    "_shell_quote",
    "_HAS_YAML",
    "yaml",
]


def _load_infra_inventory() -> dict[str, Any] | None:
    """加载基础设施清单 YAML。

    Returns:
        dict: 解析后的清单（含 servers / databases 键，可能为空列表）。
        None: 文件不存在、不可解析、或 PyYAML 不可用（调用方据此跳过）。
    """
    if not _HAS_YAML:
        print(
            "[infra] PyYAML 不可用，跳过基础设施检查 （可 `pip install pyyaml` 启用）",
            file=sys.stderr,
        )
        return None
    if not INFRA_INVENTORY.exists():
        print(
            f"[infra] 清单文件不存在：{INFRA_INVENTORY}，跳过基础设施检查",
            file=sys.stderr,
        )
        return None
    try:
        data = yaml.safe_load(INFRA_INVENTORY.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        print(
            f"[infra] 清单解析失败：{e}，跳过基础设施检查",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print("[infra] 清单顶层不是 mapping，跳过基础设施检查", file=sys.stderr)
        return None
    return data


def _tcp_connect_ok(host: str, port: int, timeout: int = TCP_TIMEOUT) -> bool:
    """TCP connect 探测，成功返回 True，超时/拒绝/错误返回 False。"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


def _run_ssh(
    ssh_alias: str,
    remote_cmd: list[str],
    timeout: int = SSH_TIMEOUT,
) -> tuple[int, str, str]:
    """以 BatchMode 执行一条 SSH 命令，返回 (rc, stdout, stderr)。"""
    cmd = [
        "ssh",
        "-o",
        f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-o",
        "BatchMode=yes",
        ssh_alias,
        *remote_cmd,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "", "ssh 命令未找到"
    except subprocess.TimeoutExpired:
        return 124, "", f"SSH 超时（>{timeout}s）"
    return result.returncode, result.stdout, result.stderr


def check_ssh_reachable(ssh_alias: str) -> bool:
    """检查 SSH 是否可达（`ssh <alias> echo ok`）。"""
    rc, out, _ = _run_ssh(ssh_alias, ["echo", "ok"])
    return rc == 0 and out.strip() == "ok"


def _parse_df_output(out: str) -> dict[str, dict[str, Any]]:
    """Parse df -h -P output into filesystems dict."""
    filesystems: dict[str, dict[str, Any]] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("Filesystem"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        size, used, avail = parts[1], parts[2], parts[3]
        use_pct_str = parts[4].rstrip("%")
        mount = " ".join(parts[5:])
        try:
            use_pct = int(use_pct_str)
        except ValueError:
            continue
        filesystems[mount] = {"size": size, "used": used, "avail": avail, "use_pct": use_pct}
    return filesystems


def _find_matching_mount(disk_check: dict[str, Any], filesystems: dict[str, dict[str, Any]]) -> str | None:
    """Find matching mount point for a disk check config."""
    mount_config = disk_check.get("mount")
    pattern = disk_check.get("pattern")
    if mount_config:
        mount_str = str(mount_config)
        return mount_str if mount_str in filesystems else None
    if pattern:
        for fs_mount in filesystems:
            if re.search(pattern, fs_mount):
                return fs_mount
    return None


def check_disk_space(
    ssh_alias: str,
    server_name: str,
    disk_checks: list[dict[str, Any]],
    global_violations: list[dict[str, Any]],
    record_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    """通过 SSH 检查磁盘空间使用率。

    用一条 SSH 命令执行 ``df -P`` 获取所有挂载点信息，
    然后逐个对比配置的阈值。超过 warn_pct 报 warning，
    超过 crit_pct 报 critical。

    磁盘满了会导致 MySQL 写入失败、Docker 构建失败、日志丢失等严重问题。

    Args:
        ssh_alias: SSH 别名。
        server_name: 服务器名（用于违规 file 字段前缀）。
        disk_checks: 磁盘检查配置列表，每项含 mount/pattern、warn_pct、crit_pct。
        global_violations: 全局违规列表（就地追加）。
        record_violations: 当前 server record 的违规列表（就地追加）。

    Returns:
        {mount_point: {size, used, avail, use_pct, status}} 磁盘使用情况。
    """
    result: dict[str, Any] = {}

    if not disk_checks:
        return result

    # 用一条 SSH 命令获取所有挂载点信息
    # df -P: POSIX 输出格式，保证一行一个文件系统
    rc, out, _err = _run_ssh(
        ssh_alias,
        ["df", "-h", "-P"],
    )
    if rc != 0:
        v = _make_violation(
            "disk_full",
            "warning",
            f"{server_name} (df)",
            f"df 命令执行失败 (rc={rc})，无法检查磁盘空间",
        )
        record_violations.append(v)
        global_violations.append(v)
        return result

    # 解析 df -h -P 输出
    filesystems = _parse_df_output(out)

    # 逐个配置项检查
    for dc in disk_checks:
        if not isinstance(dc, dict):
            continue
        warn_pct = int(dc.get("warn_pct", 80))
        crit_pct = int(dc.get("crit_pct", 90))

        # 通过 mount 精确匹配或 pattern 正则匹配
        matched_mount = _find_matching_mount(dc, filesystems)

        if matched_mount is None:
            label = dc.get("mount") or dc.get("pattern") or "?"
            v = _make_violation(
                "disk_full",
                "warning",
                f"{server_name}:{label}",
                f"未找到匹配的挂载点: {label}",
            )
            record_violations.append(v)
            global_violations.append(v)
            continue

        fs_info = filesystems[matched_mount]
        result[matched_mount] = fs_info

        use_pct = fs_info["use_pct"]
        fs_info["status"] = "ok"

        if use_pct >= crit_pct:
            fs_info["status"] = "critical"
            v = _make_violation(
                "disk_full",
                "critical",
                f"{server_name}:{matched_mount}",
                f"磁盘空间严重不足：{matched_mount} 使用 {use_pct}% "
                f"(>={crit_pct}%)，剩余 {fs_info['avail']}，"
                f"总量 {fs_info['size']}（MySQL/Docker 有写入失败风险）",
            )
            record_violations.append(v)
            global_violations.append(v)
        elif use_pct >= warn_pct:
            fs_info["status"] = "warning"
            v = _make_violation(
                "disk_full",
                "warning",
                f"{server_name}:{matched_mount}",
                f"磁盘空间不足：{matched_mount} 使用 {use_pct}% "
                f"(>={warn_pct}%)，剩余 {fs_info['avail']}，"
                f"总量 {fs_info['size']}",
            )
            record_violations.append(v)
            global_violations.append(v)

    return result


def _check_systemd_services(
    ssh_alias: str,
    server_name: str,
    services: list[str],
    global_violations: list[dict[str, Any]],
    record_violations: list[dict[str, Any]],
) -> dict[str, str]:
    """通过 SSH 批量查询 systemd 服务状态。

    用一条 SSH 命令遍历所有服务（`systemctl show ... --property=`），
    解析 LoadState/ActiveState/SubState，对每个期望服务判断：

        - ActiveState=active 且 SubState=running → "running"
        - LoadState=not-found → warning（服务未安装，可能不适用于此机）
        - 其他异常 → critical（service_down）
        - systemctl 命令执行失败 → warning（无法核对，疑似权限问题）

    Args:
        ssh_alias: SSH 别名。
        server_name: 服务器名（用于违规 file 字段前缀）。
        services: 期望检查的 systemd 服务名列表。
        global_violations: 全局违规列表（就地追加）。
        record_violations: 当前 server record 的违规列表（就地追加）。

    Returns:
        {service_name: status_str}，status_str 为 "running" / 状态描述。
        未解析到输出的服务记为 "unknown"。
    """
    statuses: dict[str, str] = {}

    if not services:
        return statuses

    # 批量查询：一条 SSH 命令遍历所有服务，避免多次往返。
    # 注意：必须把整段脚本作为「单个字符串」传给 _run_ssh（即单元素 list），
    # 否则 ssh 客户端会把多个 argv 用空格拼接后送远端 shell，导致
    # 多行脚本被重新分词而破坏（见 ssh(1) 的 command 拼接行为）。
    services_quoted = " ".join(_shell_quote(s) for s in services)
    remote_script = (
        f"for svc in {services_quoted}; do\n"
        '  echo "=== $svc ==="\n'
        '  systemctl show "$svc" '
        "--property=LoadState,ActiveState,SubState --no-pager\n"
        "done\n"
    )
    rc, out, _err = _run_ssh(ssh_alias, [remote_script])

    if rc != 0:
        # systemctl 整体不可用（权限/PATH 问题），逐个标 warning
        detail = f"systemctl 批量查询执行失败 (rc={rc})，无法核对服务状态（疑似权限或 systemd 未安装）"
        v = _make_violation(
            "service_down",
            "warning",
            f"{server_name} (systemctl)",
            detail,
        )
        record_violations.append(v)
        global_violations.append(v)
        for svc in services:
            statuses[svc] = "unknown"
        return statuses

    # 解析输出：=== <svc> === 块，块内是 LoadState/ActiveState/SubState 三行
    current_svc: str | None = None
    current_props: dict[str, str] = {}
    blocks: dict[str, dict[str, str]] = {}

    for line in out.splitlines():
        line = line.strip()
        if line.startswith("=== ") and line.endswith(" ==="):
            # 保存上一个块
            if current_svc is not None:
                blocks[current_svc] = current_props
            current_svc = line[4:-4].strip()
            current_props = {}
        elif "=" in line and current_svc is not None:
            key, _, val = line.partition("=")
            current_props[key.strip()] = val.strip()
    # 收尾最后一个块
    if current_svc is not None:
        blocks[current_svc] = current_props

    # 逐个期望服务判定
    for svc in services:
        props = blocks.get(svc)
        if not props:
            statuses[svc] = "unknown"
            v = _make_violation(
                "service_down",
                "warning",
                f"{server_name}/{svc}",
                f"systemd 服务 {svc} 未在输出中找到（解析失败或未安装）",
            )
            record_violations.append(v)
            global_violations.append(v)
            continue

        load_state = props.get("LoadState", "")
        active_state = props.get("ActiveState", "")
        sub_state = props.get("SubState", "")

        # LoadState=not-found → 服务未安装，warning（可能不适用此机）
        if load_state == "not-found":
            statuses[svc] = "not-found"
            v = _make_violation(
                "service_down",
                "warning",
                f"{server_name}/{svc}",
                f"systemd 服务 {svc} 未安装（LoadState=not-found）",
            )
            record_violations.append(v)
            global_violations.append(v)
            continue

        # 正常运行
        if active_state == "active" and sub_state == "running":
            statuses[svc] = "running"
            continue

        # 其他异常状态 → critical
        statuses[svc] = f"{active_state}/{sub_state}"
        v = _make_violation(
            "service_down",
            "critical",
            f"{server_name}/{svc}",
            f"systemd 服务 {svc} 状态异常：ActiveState={active_state}, SubState={sub_state}",
        )
        record_violations.append(v)
        global_violations.append(v)

    return statuses


def _shell_quote(s: str) -> str:
    """POSIX shell 单引号转义，用于构造安全的远程脚本。"""
    return "'" + s.replace("'", "'\"'\"'") + "'"
