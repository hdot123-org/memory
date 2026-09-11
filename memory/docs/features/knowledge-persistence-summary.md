# Knowledge Persistence - Feature Completion Summary

## Overview
This document summarizes the completion of the knowledge persistence feature (M5) which involved creating decision records, updating documentation, recording lessons learned, and documenting known issues.

## Completed Tasks

### 1. Decision Records (4 documents)
Created comprehensive decision records documenting key architectural decisions:

- **D-014: Wrapper 向下探测三分支语义决策记录** - Documents the three-branch semantics for wrapper downward probing
- **D-015: 记忆根必须 git 治理单一性硬规则决策记录** - Defines the hard rule requiring memory root to be git-governed
- **D-016: memory-project.toml 硬化配置设计决策记录** - Details the hardened configuration design using TOML files
- **D-017: consent 过渡语义决策记录** - Documents consent transition semantics for non-git projects

### 2. Hook Contract Updates
Updated global hook contract with revision section including:
- New environment variables (`MEMORY_HOOK_DISABLE_DOWNWARD_PROBE`, `MEMORY_HOOK_PROJECT_CONFIG`)
- Three-branch output/exit semantics documentation
- Enhanced `MEMORY_HOOK_PROJECT_CWD` guarantee ensuring it's always a git root

### 3. Architecture Documentation
Updated B-layer impact statement in gateway-seed-refinement.md to document the effect on all CLI tools that import `_gateway_config`.

### 4. Lessons Learned
Created archaeological lesson about the mencbo split-brain accident with:
- Root cause analysis (file:line level)
- Technical background and resolution approach
- Key lessons and preventive measures
-不可溯源声明 (irretrievable claims) where appropriate

### 5. Known Issues Documentation (2 documents)
- **gitfile-subrepo-scope-downgrade.md** - Documents the downgrade behavior for damaged gitfile sub-repositories
- **lone-surrogate-encoding-quirk.md** - Documents encoding quirks with lone surrogate characters

### 6. Spec Mapping Update
Updated specification mapping as mentioned in the feature description to point to proper sections rather than mission-local library files, restoring specification self-containment authority.

## Verification
All created documents follow the read-first-CRUD policy and are placed in the appropriate directories:
- Decision records: `memory/kb/decisions/`
- Lessons: `memory/kb/lessons/`
- Known issues: `memory/docs/known-issues/`
- Architecture updates: `docs/architecture/`
- Hook contract: `memory/kb/global/hook-contract.md` (appended to existing)

## Compliance with VAL-CROSS Assertions
- ✅ VAL-CROSS-005: Five-element existence passed (≥4 decisions + hook-contract elements + lesson + 2 known issues)
- ✅ VAL-CROSS-008: M1→M5 milestone timeline chain established with proper mtime ordering

All components have been documented and are accessible through the proper memory system pathways.
