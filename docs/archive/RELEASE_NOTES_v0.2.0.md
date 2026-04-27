# memory-core v0.2.0

## New Features

- **CoreConfig dataclass**: 37 parameter structured configuration object replacing flat kwargs
- **build_context_package_simple(host, event, payload)**: 3-parameter simplified API entry point
- **context-package-v1 schema**: New output format with flattened paths/project/task sections, diagnostics separated
- **PathUtils interface**: Encapsulates extract_excerpt and write_targets callbacks
- **PolicyRegistry extension**: 9 new methods for validation, scope lookups, and governance checks
- **ArtifactWriter + DelegateRouter**: Gateway responsibility separation classes
- **pip entry points**: `memory-validate` and `memory-rollback` console scripts
- **Lazy public API**: `from workspace.tools import build_context_package_simple, CoreConfig`

## Test Results

- 179 tests passed, 0 failed
- validate 6/6 checks passed
- rollback drill passed

## Migration from v0.1.0

- `build_context_package()` still returns wb-hook-v2 format (backward compatible)
- `build_context_package_simple()` returns new context-package-v1 format
- All existing tests continue to pass without modification
