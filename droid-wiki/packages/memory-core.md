# memory_core

The core Python package that provides the memory protocol, CLI tools, hook gateway, and adapter system.

## Directory layout

```
memory_core/
├── __init__.py
├── constants.py           # Version and signature constants
├── ownership.py           # Ownership resolution and scope isolation
├── memory/
│   └── system/
│       └── schema-audit.log
├── tools/
│   ├── adapter_toml_schema.py      # Adapter TOML schema handling
│   ├── daily_summary_generator.py  # Daily summary generation
│   ├── daily_session_summary.py    # (removed) legacy daily summary
│   ├── error_logger.py             # C-layer error logging
│   ├── factory_global_hooks.py     # Factory/Droid host bindings
│   ├── init_project_memory.py      # memory-init CLI command
│   ├── memory_hook_gateway.py      # Main gateway
│   ├── memory_hook_impls.py        # Hook implementations
│   ├── session_end_logger.py       # Session end event logging
│   └── template_sync.py           # Template synchronization
```

## Key abstractions

| Abstraction | File | Purpose |
|-------------|------|---------|
| `memory_hook_gateway` | `tools/memory_hook_gateway.py` | Event routing and adapter resolution |
| `ownership` | `ownership.py` | Project scope isolation |
| `adapter_toml_schema` | `tools/adapter_toml_schema.py` | Adapter configuration schema |
| `init_project_memory` | `tools/init_project_memory.py` | Project memory initialization |
| `factory_global_hooks` | `tools/factory_global_hooks.py` | Factory Droid bindings |

## Entry points

- `memory-init` — bootstrap `memory/` in a consumer project
- `~/.factory/bin/memory-hook` — protected wrapper for Factory hooks

## Installation

```bash
pip install memory_core
```

Package metadata is in `pyproject.toml` at the repository root.
