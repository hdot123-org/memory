#!/usr/bin/env python3
"""Codex session rollout analyzer — reads .jsonl rollout files and generates reports.

Usage:
    # Analyze a specific session
    python codex_session_analyzer.py --rollout ~/.codex/sessions/2026/05/10/rollout-*.jsonl

    # Analyze today's sessions
    python codex_session_analyzer.py --today

    # Analyze a specific thread ID
    python codex_session_analyzer.py --thread-id 019e124c-ad97-7af1-8701-7127155bd833

    # JSON output
    python codex_session_analyzer.py --thread-id 019e124c --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"

# ---------------------------------------------------------------------------
# Rollout parser
# ---------------------------------------------------------------------------

class SessionAnalyzer:
    def __init__(self) -> None:
        self.session_id: str = ""
        self.cwd: str = ""
        self.model_provider: str = ""
        self.cli_version: str = ""
        self.started_at: str = ""

        self.user_messages: list[dict[str, str]] = []
        self.assistant_messages: list[dict[str, str]] = []
        self.tool_calls: list[dict[str, str]] = []
        self.token_events: list[dict[str, Any]] = []

        self.errors: list[str] = []

    def parse_file(self, path: Path) -> None:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = obj.get("type", "")
            ts = obj.get("timestamp", "")
            payload = obj.get("payload", {})

            if t == "session_meta":
                self.session_id = payload.get("id", "")
                self.cwd = payload.get("cwd", "")
                self.model_provider = payload.get("model_provider", "")
                self.cli_version = payload.get("cli_version", "")
                self.started_at = payload.get("timestamp", "")

            elif t == "event_msg":
                evt_type = payload.get("type", "")
                if evt_type == "user_message":
                    msg = payload.get("message", "")
                    if msg.strip():
                        self.user_messages.append({"timestamp": ts, "message": msg})
                elif evt_type == "agent_message":
                    msg = payload.get("message", "")
                    phase = payload.get("phase")
                    if msg.strip() and not phase:
                        self.assistant_messages.append({"timestamp": ts, "message": msg})
                elif evt_type == "agent_reasoning":
                    text = payload.get("text", "")
                    if text.strip():
                        self.assistant_messages.append({"timestamp": ts, "message": text})
                elif evt_type == "token_count":
                    info = payload.get("info", {})
                    if info and "total_token_usage" in info:
                        self.token_events.append({
                            "timestamp": ts,
                            **info["total_token_usage"],
                        })

            elif t == "response_item":
                payload_type = payload.get("type", "")
                if payload_type == "function_call":
                    self.tool_calls.append({
                        "timestamp": ts,
                        "name": payload.get("name", ""),
                        "arguments": payload.get("arguments", ""),
                    })

    @property
    def total_user_messages(self) -> int:
        return len(self.user_messages)

    @property
    def total_assistant_messages(self) -> int:
        return len(self.assistant_messages)

    @property
    def total_tool_calls(self) -> int:
        return len(self.tool_calls)

    @property
    def token_summary(self) -> dict[str, int]:
        if not self.token_events:
            return {}
        return {
            "total_input_tokens": sum(e.get("input_tokens", 0) for e in self.token_events),
            "total_output_tokens": sum(e.get("output_tokens", 0) for e in self.token_events),
            "total_tokens": sum(e.get("total_tokens", 0) for e in self.token_events),
        }

    @property
    def tool_call_frequency(self) -> list[tuple[str, int]]:
        return Counter(tc["name"] for tc in self.tool_calls).most_common()

    def print_report(self, *, show_conversation: bool = True, max_msg_len: int = 200) -> None:
        print("=" * 60)
        print(f"Session Report — {self.session_id[:16]}...")
        print("=" * 60)
        print(f"Model:        {self.model_provider}")
        print(f"Directory:    {self.cwd}")
        print(f"Started:      {self.started_at}")
        print(f"CLI version:  {self.cli_version}")
        print()

        print(f"User messages:      {self.total_user_messages}")
        print(f"Assistant messages: {self.total_assistant_messages}")
        print(f"Tool calls:         {self.total_tool_calls}")
        print()

        ts = self.token_summary
        if ts:
            print("Token usage:")
            print(f"  Input:  {ts.get('total_input_tokens', 0):,}")
            print(f"  Output: {ts.get('total_output_tokens', 0):,}")
            print(f"  Total:  {ts.get('total_tokens', 0):,}")
            print()

        freq = self.tool_call_frequency
        if freq:
            print("Top tools:")
            for name, count in freq[:8]:
                print(f"  {name}: {count}")
            print()

        if show_conversation and self.user_messages:
            print("-" * 60)
            print("Conversation:")
            print("-" * 60)
            for i, um in enumerate(self.user_messages):
                msg = um["message"].strip()
                if msg:
                    print(f"\n[User {i+1}] {um['timestamp'][:19]}")
                    print(f"    {msg[:max_msg_len]}{'...' if len(msg) > max_msg_len else ''}")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_rollout_files(thread_id: str | None = None, target_date: str | None = None) -> list[Path]:
    """Find rollout files matching criteria."""
    if not CODEX_SESSIONS_DIR.exists():
        return []

    results: list[Path] = []
    for jsonl_file in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
        if target_date:
            # Match both "YYYYMMDD" and "YYYY/MM/DD" path formats.
            compact = target_date.replace("-", "")
            if compact not in str(jsonl_file) and target_date not in str(jsonl_file):
                continue
        if thread_id and thread_id not in jsonl_file.name:
            continue
        results.append(jsonl_file)
    return sorted(results)


def find_todays_sessions() -> list[Path]:
    today = date.today().strftime("%Y-%m-%d")
    return find_rollout_files(target_date=today)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex session rollout analyzer.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--rollout", type=str, help="Path to rollout .jsonl file(s), supports glob")
    group.add_argument("--thread-id", type=str, help="Thread ID to search for")
    group.add_argument("--today", action="store_true", help="Analyze today's sessions")
    parser.add_argument("--no-conversation", action="store_true", help="Hide conversation details")
    parser.add_argument("--max-len", type=int, default=200, help="Max message length to display")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv)

    # Find files
    if args.rollout:
        from glob import glob
        files = [Path(p) for p in sorted(glob(args.rollout))]
    elif args.thread_id:
        files = find_rollout_files(thread_id=args.thread_id)
    elif args.today:
        files = find_todays_sessions()
    else:
        files = []

    if not files:
        print("No rollout files found.", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []

    for f in files:
        analyzer = SessionAnalyzer()
        analyzer.parse_file(f)
        if args.json:
            results.append({
                "session_id": analyzer.session_id,
                "cwd": analyzer.cwd,
                "model_provider": analyzer.model_provider,
                "cli_version": analyzer.cli_version,
                "started_at": analyzer.started_at,
                "user_messages": analyzer.total_user_messages,
                "assistant_messages": analyzer.total_assistant_messages,
                "tool_calls": analyzer.total_tool_calls,
                "token_summary": analyzer.token_summary,
                "tool_frequency": dict(analyzer.tool_call_frequency),
            })
        else:
            if len(files) > 1:
                print(f"\n{'='*60}")
                print(f"File: {f.name}")
            analyzer.print_report(show_conversation=not args.no_conversation, max_msg_len=args.max_len)

    if args.json:
        if len(results) == 1:
            print(json.dumps(results[0], indent=2, ensure_ascii=False))
        else:
            print(json.dumps(results, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
