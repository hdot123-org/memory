"""Vulture whitelist for false positives.

These items are reported as unused by vulture but are actually used:
- Entry points defined in pyproject.toml [project.scripts]
- Interface implementations (methods required by protocols)
- Public API functions/classes imported by consumers
- Dynamically accessed attributes
"""

# Entry points from pyproject.toml [project.scripts]
check_compatibility  # unused function (memory_core/compat.py:271) - entry point: memory-compatibility-check
format_report  # unused function (memory_core/compat.py:340) - used by check_compatibility
OwnershipKind  # unused class (memory_core/ownership.py:33) - public API
DOMAIN  # unused variable (memory_core/ownership.py:36) - public API
RESOURCE  # unused variable (memory_core/ownership.py:37) - public API

# Dynamic module loading via __getattr__
__getattr__  # unused function (memory_core/tools/__init__.py:14) - lazy imports

# Error classes used for exception handling
RuleViolationError  # unused class (memory_core/tools/_rule_errors.py:26) - public API
OwnershipError  # unused class (memory_core/tools/_rule_errors.py:35) - public API
GuardBlockError  # unused class (memory_core/tools/_rule_errors.py:39) - public API
PolicyViolationError  # unused class (memory_core/tools/_rule_errors.py:49) - public API

# Rule evaluator interface implementation
RuleEvaluator  # unused class (memory_core/tools/_rule_types.py:55) - interface
_.evaluate  # unused method (memory_core/tools/_rule_types.py:67) - interface method

# Entry points and public API
plan_main  # unused function (memory_core/tools/audit_project_layout.py:1235) - entry point: memory-plan-residue
capture_candidates  # unused function (memory_core/tools/auto_capture.py:20) - public API

# Business policy checker interface implementations
_.evaluate  # unused method (memory_core/tools/business_policy_checks.py:116) - interface method
LegalContractChecker  # unused class (memory_core/tools/business_policy_checks.py:237) - registered checker
_.evaluate  # unused method (memory_core/tools/business_policy_checks.py:420) - interface method
ScopeResolver  # unused class (memory_core/tools/business_policy_checks.py:677) - registered resolver

# Hook state management
reset_hook_state  # unused function (memory_core/tools/cmux_hook_state.py:52) - public API

# Feature flags public API
register_flag  # unused function (memory_core/tools/feature_flags.py:119) - public API
reset_flags  # unused function (memory_core/tools/feature_flags.py:142) - public API
is_enabled  # unused function (memory_core/tools/feature_flags.py:147) - public API

# Global KB initialization check
is_global_kb_initialized  # unused function (memory_core/tools/global_kb_init.py:261) - public API

# Hook event parsing
from_claude_payload  # unused function (memory_core/tools/hook_event.py:132) - factory method
to_context_package_input  # unused function (memory_core/tools/hook_event.py:163) - serialization method
parse_hook_event  # unused function (memory_core/tools/hook_event.py:183) - public API

# Hook event statistics
_find_context_snapshots  # unused function (memory_core/tools/hook_event_stats.py:35) - internal helper

# Hook generation
generate_hooks_json  # unused function (memory_core/tools/init_project_memory.py:1481) - public API

# Logging utilities
get_sanitized_logger  # unused function (memory_core/tools/log_utils.py:48) - public API

# Default runtime profile builder
build_default_runtime_profile  # unused function (memory_core/tools/memory_hook_adapters/default_runtime_profile.py:27) - loaded dynamically

# Config interface methods
_.uses_interfaces  # unused property (memory_core/tools/memory_hook_config.py:84) - interface property
_.to_gateway_kwargs  # unused method (memory_core/tools/memory_hook_config.py:200) - serialization method
_.from_gateway_kwargs  # unused method (memory_core/tools/memory_hook_config.py:205) - factory method

# Gateway module-level constants (used via globals().update)
MEMORY_SYSTEM_PATH  # unused variable (memory_core/tools/memory_hook_gateway.py:64)
GATEWAY_POLICY_CLASS  # unused variable (memory_core/tools/memory_hook_gateway.py:65)
ARTIFACT_COMPACTION  # unused variable (memory_core/tools/memory_hook_gateway.py:66)
CLAUDE_HOOK_STATE_FILE  # unused variable (memory_core/tools/memory_hook_gateway.py:67)
GLOBAL_KB_ENABLED  # unused variable (memory_core/tools/memory_hook_gateway.py:69)

# Gateway internal functions (used dynamically or public API)
_configured_invalid_memory_root  # unused function (memory_core/tools/memory_hook_gateway.py:140) - test helper
_collect_changed_paths  # unused function (memory_core/tools/memory_hook_gateway.py:254) - public API
get_config  # unused function (memory_core/tools/memory_hook_gateway.py:333) - public API
get_config_dict  # unused function (memory_core/tools/memory_hook_gateway.py:339) - public API
_resolve_policy_conflict_via_registry  # unused function (memory_core/tools/memory_hook_gateway.py:561) - conflict resolver
resolve_route_target  # unused function (memory_core/tools/memory_hook_gateway.py:874) - public API
write_artifacts  # unused function (memory_core/tools/memory_hook_gateway.py:1080) - public API
_require_env  # unused function (memory_core/tools/memory_hook_gateway.py:1119) - validation helper
_canonicalize_cmux_refs  # unused function (memory_core/tools/memory_hook_gateway.py:1126) - normalization helper

# Delegate implementations (registered dynamically)
CodexDelegate  # unused class (memory_core/tools/memory_hook_impls.py:128) - registered delegate
ClaudeDelegate  # unused class (memory_core/tools/memory_hook_impls.py:168) - registered delegate
_.host_unavailable  # unused property (memory_core/tools/memory_hook_impls.py:286) - interface method
_.host_unavailable  # unused property (memory_core/tools/memory_hook_impls.py:323) - interface method
_.get_policy  # unused method (memory_core/tools/memory_hook_impls.py:452) - interface method
_.resolve_kb_file  # unused method (memory_core/tools/memory_hook_impls.py:609) - interface method
_.route  # unused method (memory_core/tools/memory_hook_impls.py:1019) - interface method
PathUtilsImpl  # unused class (memory_core/tools/memory_hook_impls.py:1050) - registered implementation

# Integrity verification helpers
key_info  # unused function (memory_core/tools/memory_hook_integrity_keys.py:64) - public API
_hmac_sha256  # unused function (memory_core/tools/memory_hook_integrity_manifest.py:130) - cryptographic helper
quick_check  # unused function (memory_core/tools/memory_hook_integrity_verify.py:189) - public API

# Interface data structures
project_ref  # unused variable (memory_core/tools/memory_hook_interfaces.py:28) - data structure field
global_refs  # unused variable (memory_core/tools/memory_hook_interfaces.py:32) - data structure field
conflict_status  # unused variable (memory_core/tools/memory_hook_interfaces.py:33) - data structure field
triggered_on_current_event  # unused variable (memory_core/tools/memory_hook_interfaces.py:41) - data structure field
enforcement_result  # unused variable (memory_core/tools/memory_hook_interfaces.py:42) - data structure field
_.host_unavailable  # unused property (memory_core/tools/memory_hook_interfaces.py:80) - interface method
_.get_policy  # unused method (memory_core/tools/memory_hook_interfaces.py:97) - interface method

# Schema version detection
is_v2  # unused function (memory_core/tools/memory_hook_schema.py:205) - public API
is_lossless  # unused function (memory_core/tools/memory_hook_schema.py:362) - public API

# Observability interface methods
_.child_span  # unused method (memory_core/tools/observability.py:80) - interface method
_.record_span  # unused method (memory_core/tools/observability.py:87) - interface method
_.measure  # unused method (memory_core/tools/observability.py:150) - interface method
MetricsRegistry  # unused class (memory_core/tools/observability.py:189) - registry class
_.publish  # unused method (memory_core/tools/observability.py:215) - interface method
ErrorTracker  # unused class (memory_core/tools/observability.py:252) - tracker class
_.recent  # unused method (memory_core/tools/observability.py:283) - interface method

# Project probe fields
git_branch  # unused variable (memory_core/tools/project_probe.py:144) - data structure field
_.git_branch  # unused attribute (memory_core/tools/project_probe.py:189) - data structure field

# Prompt validation
check_prompt_or_raise  # unused function (memory_core/tools/prompt_validator.py:59) - public API

# Orchestrator implementation
ResilientOrchestrator  # unused class (memory_core/tools/resilient_orchestrator.py:12) - registered orchestrator
_.dispatch_task  # unused method (memory_core/tools/resilient_orchestrator.py:27) - interface method

# Telemetry helpers
_.safe_capture  # unused method (memory_core/tools/telemetry_bridge.py:201) - error handling wrapper

# Validation helpers
_parse_frontmatter  # unused function (memory_core/tools/validate_project_memory.py:71) - internal parser
