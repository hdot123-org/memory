"""Shared dynamic loader for scripts/ guard-script tests (INFRA-296).

Historically ``tests/test_boundary_guard.py`` and
``tests/test_check_fix_has_test.py`` each carried its own copy of a
``_load_module()`` helper that imported its target script via
``importlib.util``. The near-identical copies (96% AST similarity)
triggered the CODE_HYGIENE_DUPLICATE_BLOCK finding. The loading logic is
consolidated into this module; test modules keep their local
``_load_module()`` names as thin wrappers delegating to
``load_script_module``, so existing call sites stay unchanged.

Semantics:
- ``load_script_module`` loads a plain script (no package context) under a
  caller-chosen module name and executes it, returning the module object.
- Loading failures surface naturally from ``exec_module``; the guard
  ``assert`` merely narrows ``spec``/``loader`` typing to satisfy type
  checkers (``Optional`` fields on ``ModuleSpec``).
"""

import importlib.util
from pathlib import Path
from types import ModuleType


def load_script_module(script_path: Path, module_name: str) -> ModuleType:
    """Dynamically load a plain script module from script_path under module_name.

    Mirrors the historical per-file ``_load_module()`` helpers: build a
    ``ModuleSpec`` from the script path, execute it, and return the loaded
    module object.
    """
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
