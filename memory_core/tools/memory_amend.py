#!/usr/bin/env python3.12
"""memory-amend：既有 memory 文件的合法 append-only 追加通道（债 7b）。

与债 7a 的 Create-on-existing-owned 拦截（PR #1122）同窗上线：Create/Write/
Edit 对 memory/kb、memory/log 等受保护文件的改写与新建覆盖仍被守卫拦截，
合法的增量更正统一收敛到本工具。

服务端强制 append-only 语义：
- 只追加，永不改写既有字节：新内容 = 旧内容 + 追加块，并显式断言旧内容
  是新内容的逐字节前缀（天然满足，但显式断言防实现漂移）。
- 任何要求改写既有字节的路径（如 --edit）一律不存在。
- 目标文件必须已存在（新建文件走 Create 合法流）；父目录不存在时报错。
- 原子写入：同目录隐藏 tmp 文件 + os.replace，失败不污染原文件。

``--header`` 时在追加块前自动生成日期化更正段头行（对齐决策记录更正惯例）：
``> ⚠️ 更正段 #N（YYYY-MM-DD，append-only）：<标题>``
N 由文件内既有更正段最大编号推断（无则 #1）。
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

_CORRECTION_MARKER_RE = re.compile(r"更正段\s*#(\d+)")
_HEADER_LINE_TEMPLATE = "> ⚠️ 更正段 #{number}（{date}，append-only）：{title}"


def next_correction_number(old_text: str) -> int:
    """推断下一个更正段编号：取既有最大编号 +1，无则 1。"""
    numbers = [int(m) for m in _CORRECTION_MARKER_RE.findall(old_text)]
    return max(numbers) + 1 if numbers else 1


def build_append_block(
    old_content: bytes,
    append_content: bytes,
    *,
    header_title: str | None,
    today: str | None = None,
) -> tuple[bytes, int]:
    """构造追加块，返回 (追加块字节, 更正段编号；无 header 时编号为 0)。

    纯函数：不触碰文件系统，便于测试 append-only 前缀不变式。
    """
    block_parts: list[bytes] = []

    # 与旧内容保持行边界隔离（仍是纯追加，不改写任何旧字节）
    if old_content and not old_content.endswith(b"\n"):
        block_parts.append(b"\n")

    correction_number = 0
    if header_title is not None:
        date_str = today or datetime.date.today().isoformat()
        correction_number = next_correction_number(old_content.decode("utf-8", errors="ignore"))
        header_line = _HEADER_LINE_TEMPLATE.format(number=correction_number, date=date_str, title=header_title)
        block_parts.append(header_line.encode("utf-8") + b"\n\n")

    block_parts.append(append_content)
    block = b"".join(block_parts)

    # 保证文件以换行收尾（仍是纯追加）
    if block and not block.endswith(b"\n"):
        block += b"\n"
    return block, correction_number


def amend_file(target: Path, append_content: bytes, *, header_title: str | None) -> tuple[int, int]:
    """对既有文件 target 追加 append_content，返回 (追加字节数, 更正段编号)。

    服务端强制 append-only + 原子写。目标不存在 / 父目录不存在即抛错。
    """
    if not target.parent.is_dir():
        raise NotADirectoryError(f"目标父目录不存在：{target.parent}")
    if not target.exists():
        raise FileNotFoundError(f"目标文件不存在（本工具只追加既有文件，新建请走 Create 合法流）：{target}")

    old_content = target.read_bytes()
    block, correction_number = build_append_block(old_content, append_content, header_title=header_title)
    new_content = old_content + block

    # 显式前缀断言：append-only 不变式的硬校验，防实现漂移（改写既有字节）
    if len(new_content) < len(old_content) or new_content[: len(old_content)] != old_content:
        raise AssertionError("append-only 不变式被破坏：旧内容不是新内容的逐字节前缀")

    tmp_path = target.parent / f".{target.name}.memory-amend-tmp"
    try:
        tmp_path.write_bytes(new_content)
        tmp_path.replace(target)
    finally:
        # 成功时 tmp 已被 rename 消费；失败时清理残留，原文件字节未动
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return len(block), correction_number


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：memory-amend <path> [--header "<标题>"]，追加块从 stdin 读。"""
    parser = argparse.ArgumentParser(
        prog="memory-amend",
        description="既有文件的 append-only 合法追加通道（配合 Create-on-existing 拦截守卫）",
    )
    parser.add_argument("path", help="目标文件路径（必须已存在）")
    parser.add_argument(
        "--header",
        metavar="标题",
        default=None,
        help="自动生成日期化更正段头行：更正段 #N（YYYY-MM-DD，append-only）：标题",
    )
    args = parser.parse_args(argv)

    target = Path(args.path).expanduser()
    append_content = sys.stdin.buffer.read()

    if not append_content and args.header is None:
        print("memory-amend：stdin 追加内容为空且未指定 --header，未做任何修改", file=sys.stderr)
        return 1

    try:
        appended, correction_number = amend_file(target, append_content, header_title=args.header)
    except (FileNotFoundError, NotADirectoryError, AssertionError, OSError) as exc:
        print(f"memory-amend：错误 — {exc}", file=sys.stderr)
        return 1

    if correction_number:
        print(
            f"memory-amend：已追加 {target}（+{appended} 字节，更正段 #{correction_number}，append-only）",
            file=sys.stderr,
        )
    else:
        print(f"memory-amend：已追加 {target}（+{appended} 字节，append-only）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
