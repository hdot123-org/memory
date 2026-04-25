#!/usr/bin/env python3
"""Workbot runtime profile for memory-hook gateway wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_workbot_runtime_profile(repo_root: Path, workspace_root: Path) -> dict[str, Any]:
    project_map_root = workspace_root / "project-map"
    truth_model = workspace_root / "memory" / "kb" / "global" / "workbot-truth-model.md"
    project_map_files = [
        project_map_root / "INDEX.md",
        project_map_root / "legal-core-map.md",
        project_map_root / "ingestion-registry-map.md",
    ]
    project_map_governance = workspace_root / "memory" / "kb" / "global" / "workbot-project-map-governance.md"
    hook_contract_path = workspace_root / "memory" / "kb" / "global" / "workbot-hook-contract.md"
    global_rule_path = workspace_root / "memory" / "kb" / "global" / "workbot-memory-routing.md"
    memory_system_path = workspace_root / "memory" / "kb" / "global" / "workbot-memory-system.md"
    policy_pack_path = workspace_root / "memory" / "kb" / "global" / "workbot-policy-pack.json"

    required_registry_scopes = [
        "workspace/project-map/**",
        "workspace/memory/kb/global/**",
        "workspace/memory/kb/projects/**",
        "workspace/memory/docs/**",
        "workspace/memory/log/**",
        "workspace/projects/**",
        "workspace/tools/**",
        "tests/**",
    ]

    required_canonical = [
        workspace_root / "INDEX.md",
        workspace_root / "NOW.md",
        *project_map_files,
        workspace_root / "memory" / "kb" / "INDEX.md",
        workspace_root / "memory" / "docs" / "INDEX.md",
        workspace_root / "memory" / "inbox.md",
        truth_model,
        memory_system_path,
        global_rule_path,
        hook_contract_path,
        project_map_governance,
        workspace_root / "memory" / "kb" / "projects" / "INDEX.md",
    ]

    project_canonical = {
        "workbot": workspace_root / "memory" / "kb" / "projects" / "workbot.md",
        "AEdu": workspace_root / "memory" / "kb" / "projects" / "AEdu.md",
        "platform-capabilities": workspace_root / "memory" / "kb" / "projects" / "platform-capabilities.md",
    }

    project_runtime_root = {
        "workbot": workspace_root / "projects",
        "AEdu": workspace_root / "projects" / "AEdu",
        "platform-capabilities": workspace_root / "projects",
    }

    project_doc_refs = {
        "workbot": [
            workspace_root / "memory" / "docs" / "INDEX.md",
            workspace_root / "memory" / "docs" / "记忆系统全景文档.md",
        ],
        "AEdu": [
            workspace_root / "memory" / "docs" / "research" / "projects" / "AEdu" / "INDEX.md",
            workspace_root / "projects" / "AEdu" / "INDEX.md",
        ],
        "platform-capabilities": [
            workspace_root / "memory" / "docs" / "INDEX.md",
        ],
    }

    global_canonical = [
        truth_model,
        memory_system_path,
        global_rule_path,
        hook_contract_path,
        project_map_governance,
    ]

    authority_allowed_paths = {
        project_map_root / "INDEX.md",
        project_map_root / "legal-core-map.md",
    }

    lower_evidence_roots = [
        workspace_root / "projects",
        workspace_root / "artifacts",
        workspace_root / "tools",
        workspace_root / "memory" / "log",
        workspace_root / "memory" / "system",
        repo_root / "tests",
    ]

    default_decision_refs = [
        workspace_root / "memory" / "kb" / "decisions" / "INDEX.md",
    ]

    project_decision_refs = {
        "workbot": [],
        "AEdu": [],
        "platform-capabilities": [],
    }

    aedu_root = repo_root / "AEdu"
    governance_frozen_tuple_files = [
        aedu_root / "00_导航与管理" / "KB+INGEST 模块级开发准入评审单.md",
        aedu_root / "00_导航与管理" / "SIM模块级开发准入评审单.md",
        aedu_root / "12_实施与试点运营" / "09_KB+INGEST 试点范围与责任边界.md",
        aedu_root / "scripts" / "validate_kb_closure.py",
    ]
    event_contract_files = {
        "upstream_standard": aedu_root / "06_数据接入与事件流" / "07_学习事件生成标准.md",
        "upstream_mapping": aedu_root / "06_数据接入与事件流" / "12_输入源映射表.md",
        "formal_contract": aedu_root / "11_系统架构与工程实现" / "22_KB+INGEST-TWIN输入契约.md",
        "upstream_samples": aedu_root / "11_系统架构与工程实现" / "21_KB+INGEST 端到端样例集.md",
        "downstream_samples": aedu_root / "11_系统架构与工程实现" / "24_TWIN端到端样例集.md",
    }
    frozen_tuple_expected = {
        "province=安徽",
        "region_id=CN_AH",
        "rule_package=AH_RULE_V1",
        "kb_version_prefix=KB_CN_AH_",
    }
    frozen_tuple_legacy_markers = {
        "CN_GD_SZ",
        "KB_CN_GD_SZ",
    }
    formal_source_types = {
        "parent_text",
        "teacher_feedback_text",
        "scan_ocr",
        "reviewed_event",
    }
    formal_event_types = {
        "homework_result_event",
        "correction_followup_event",
        "teacher_feedback_event",
        "parent_feedback_event",
        "scan_ocr_result_event",
        "reviewed_learning_event",
    }
    formal_event_statuses = {
        "success",
        "degraded",
        "review_needed",
        "rejected",
    }
    formal_field_keys = {
        "event_summary",
        "raw_input_ref",
    }
    legacy_field_keys = {
        "summary",
        "raw_input_id",
        "accepted",
    }

    default_lesson_refs = [
        workspace_root / "memory" / "kb" / "lessons" / "memory-docs-immutable.md",
    ]

    project_lesson_refs = {
        "workbot": [
            workspace_root / "memory" / "kb" / "lessons" / "pm-bot-crawl4ai-runtime-path.md",
        ],
        "AEdu": [],
        "platform-capabilities": [],
    }

    registration_git_scope = [
        workspace_root / "INDEX.md",
        workspace_root / "NOW.md",
        *project_map_files,
        project_map_governance,
        hook_contract_path,
    ]

    legal_core_markers = [
        "active-legal",
        "project-map/INDEX.md",
        "workbot-truth-model.md",
        "workbot-memory-system.md",
    ]

    return {
        "PROJECT_MAP_ROOT": project_map_root,
        "TRUTH_MODEL": truth_model,
        "PROJECT_MAP_FILES": project_map_files,
        "PROJECT_MAP_GOVERNANCE": project_map_governance,
        "HOOK_CONTRACT_PATH": hook_contract_path,
        "GLOBAL_RULE_PATH": global_rule_path,
        "MEMORY_SYSTEM_PATH": memory_system_path,
        "POLICY_PACK_PATH": policy_pack_path,
        "LEGALITY_SOURCE_POLICY": "active-legal-map-only",
        "REGISTRATION_COMMIT_POLICY": "required-after-absorption-complete",
        "REGISTRATION_COMMIT_PHASE": "declared-not-enforced",
        "REGISTRATION_GIT_SCOPE": registration_git_scope,
        "LEGAL_CORE_MARKERS": legal_core_markers,
        "REQUIRED_REGISTRY_SCOPES": required_registry_scopes,
        "REQUIRED_CANONICAL": required_canonical,
        "PROJECT_CANONICAL": project_canonical,
        "PROJECT_RUNTIME_ROOT": project_runtime_root,
        "PROJECT_DOC_REFS": project_doc_refs,
        "GLOBAL_CANONICAL": global_canonical,
        "AUTHORITY_ALLOWED_PATHS": authority_allowed_paths,
        "LOWER_EVIDENCE_ROOTS": lower_evidence_roots,
        "DEFAULT_DECISION_REFS": default_decision_refs,
        "PROJECT_DECISION_REFS": project_decision_refs,
        "GOVERNANCE_FROZEN_TUPLE_FILES": governance_frozen_tuple_files,
        "EVENT_CONTRACT_FILES": event_contract_files,
        "FROZEN_TUPLE_EXPECTED": frozen_tuple_expected,
        "FROZEN_TUPLE_LEGACY_MARKERS": frozen_tuple_legacy_markers,
        "FORMAL_SOURCE_TYPES": formal_source_types,
        "FORMAL_EVENT_TYPES": formal_event_types,
        "FORMAL_EVENT_STATUSES": formal_event_statuses,
        "FORMAL_FIELD_KEYS": formal_field_keys,
        "LEGACY_FIELD_KEYS": legacy_field_keys,
        "DEFAULT_LESSON_REFS": default_lesson_refs,
        "PROJECT_LESSON_REFS": project_lesson_refs,
        "GOVERNANCE_BLOCKER_SCOPES": {"AEdu"},
        "EVENT_CONTRACT_BLOCKER_SCOPES": {"AEdu"},
        "DEFAULT_PROJECT_SCOPE": "workbot",
        "ROUTE_PROJECT_RUNTIME_SCOPE": "AEdu",
        "SCOPE_MATCH_HINTS": {
            "AEdu": [
                workspace_root / "projects" / "AEdu",
                repo_root / "AEdu",
            ],
            "platform-capabilities": [
                repo_root / "app",
                repo_root / "agents",
                repo_root / "gpt-web-to",
                workspace_root / "projects" / "app",
                workspace_root / "projects" / "agents",
                workspace_root / "projects" / "skills",
            ],
        },
        "CORE_EVIDENCE_REFS": [
            str(memory_system_path),
            str(global_rule_path),
            str(hook_contract_path),
        ],
        "POLICY_ALLOWED_SCOPES": {"workbot", "AEdu", "platform-capabilities"},
        "POLICY_SCOPE_INHERITS": {
            "AEdu": "workbot",
            "platform-capabilities": "workbot",
        },
    }
