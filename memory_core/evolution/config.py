"""
管道配置解析：~/.memory-core/evolution/config.json 的加载与默认值生成

架构 §3.2 四段结构：llm / promote / git / analyze
"""

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "llm": {
        "engine": "axonhub",
        "base_url": "https://node1.tail5e888.ts.net/v1",
        "model": "glm-5.3",
        "api_key_env": "AXONHUB_API_KEY",
        "api_key_op_ref": "",
        "max_tokens": 4096,
        "daily_budget_tokens": 2_000_000,
    },
    "promote": {
        "auto_confidence_threshold": 0.8,
    },
    "git": {
        "auto_commit": True,
        "push": True,
    },
    "analyze": {
        "include_docs": True,
        "include_daily_logs": True,
        "max_files_per_project": 50,
    },
}


def get_config_path(evolution_root: Path) -> Path:
    """返回 config.json 路径"""
    return evolution_root / "config.json"


def load_or_create_config(evolution_root: Path) -> dict[str, Any]:
    """
    加载配置，不存在则自动生成默认配置（架构 §3.2）

    Args:
        evolution_root: 运行时目录

    Returns:
        配置字典
    """
    config_path = get_config_path(evolution_root)

    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8") as f:
                config: dict[str, Any] = json.load(f)
            # 补全缺失的默认段（向前兼容）
            for section, defaults in DEFAULT_CONFIG.items():
                if section not in config:
                    config[section] = dict(defaults)
                elif isinstance(defaults, dict):
                    for key, val in defaults.items():
                        if key not in config[section]:
                            config[section][key] = val
            return config
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to load config, using defaults: {e}", file=sys.stderr)

    # 自动生成默认配置
    evolution_root.mkdir(parents=True, exist_ok=True)
    try:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Warning: Failed to write default config: {e}", file=sys.stderr)

    return dict(DEFAULT_CONFIG)
