"""monkeypatch 目标重定向共享机制（M3 兼容层三胞胎去重，INFRA-944 等 12 条）。

背景：memory_hook_gateway / migrate_project_memory / daily_kb_audit 三个
门面模块拆分后，各自的 ``_gateway_patch_redirect.py`` / ``_migrate_patch_redirect.py``
/ ``_audit_patch_redirect.py`` 携带逐字节相同的 ``_RedirectModule`` 机制代码
（``_redirect_set`` / ``_redirect_del`` / ``_resolve_target_dicts`` /
``_try_add`` 四函数），被 evolution scanner 以 CODE_HYGIENE_DUPLICATE_BLOCK
重复报告（12 条 finding）。

方案：机制实现收敛到本共享模块，三个重定向文件保留各自的
``_REDIRECT_TARGETS`` / ``_MODULE_ANCHORS`` 目标表（这是每个门面真正
不同的部分），通过 ``make_redirect_module()`` 生成各自绑定的
``_RedirectModule`` 类。行为与原实现完全一致（零行为变化）：

- 门面属性被替换时，同步写门面 + 对应子模块命名空间。
- ``del``（monkeypatch 还原）同理撤销所有写入点。
- 目标命名空间解析同时覆盖 sys.modules 中的模块与「孤儿」模块
  （被测试 purge 出 sys.modules 但仍被旧门面引用），后者通过锚点
  函数的 ``__globals__`` 定位。
"""

from __future__ import annotations

import contextlib
import sys
import types
from typing import Any

# 本共享模块的父包（与三个门面/重定向文件同层，如 "memory_core.tools"）。
# 与原三胞胎各自 ``__name__.rsplit(".", 1)[0]`` 的解析结果一致。
_PARENT_PACKAGE = __name__.rsplit(".", 1)[0]


def _resolve_target_dicts(
    gateway_module: types.ModuleType,
    parent: str,
    mod_name: str,
    module_anchors: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """解析目标模块命名空间的所有存活实例（sys.modules + 孤儿模块）。

    返回可直接写入的命名空间 dict：
    - sys.modules 中登记的模块 ``__dict__``
    - 孤儿模块：已从 sys.modules 移除、但旧门面仍持有其函数引用的
      模块。通过门面属性（或 sys.modules 模块）中锚点函数的
      ``__globals__`` 定位。
    """
    full = f"{parent}.{mod_name}"
    dicts: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _try_add(ns: Any) -> None:
        if isinstance(ns, dict) and ns.get("__name__") == full and id(ns) not in seen:
            dicts.append(ns)
            seen.add(id(ns))

    mod = sys.modules.get(full)
    if mod is not None:
        _try_add(mod.__dict__)

    for anchor_name in module_anchors.get(mod_name, ()):
        # 门面自身属性（可能是孤儿模块的函数）与 sys.modules 模块的属性
        for holder in (gateway_module, mod):
            anchor_fn = getattr(holder, anchor_name, None)
            if anchor_fn is not None:
                _try_add(getattr(anchor_fn, "__globals__", None))
    return dicts


def make_redirect_module(
    redirect_targets: dict[str, tuple[str, ...]],
    module_anchors: dict[str, tuple[str, ...]],
) -> type[types.ModuleType]:
    """构造绑定到指定目标表/锚点表的 ``_RedirectModule`` 类。

    Args:
        redirect_targets: 符号 → 拆分后运行时实际查找该符号的模块名元组。
        module_anchors: 子模块名 → 代表函数名元组（定位孤儿命名空间）。

    Returns:
        新的模块类；将其赋给门面 ``__class__`` 后，对门面属性的
        monkeypatch 写入/删除会同步转发到各子模块命名空间。
    """

    class _RedirectModule(types.ModuleType):
        """把符号写入同步到拆分子模块的模块类。"""

        def __setattr__(self, name: str, value: object) -> None:
            super().__setattr__(name, value)
            self._redirect_set(name, value)

        def __delattr__(self, name: str) -> None:
            super().__delattr__(name)
            self._redirect_del(name)

        def _redirect_set(self, name: str, value: object) -> None:
            targets = redirect_targets.get(name)
            if targets is None:
                return
            for mod_name in targets:
                for ns in _resolve_target_dicts(self, _PARENT_PACKAGE, mod_name, module_anchors):
                    if ns.get(name) is not value:
                        ns[name] = value

        def _redirect_del(self, name: str) -> None:
            targets = redirect_targets.get(name)
            if targets is None:
                return
            for mod_name in targets:
                for ns in _resolve_target_dicts(self, _PARENT_PACKAGE, mod_name, module_anchors):
                    if name in ns:
                        with contextlib.suppress(KeyError):
                            del ns[name]

    return _RedirectModule


def install_redirect(
    gateway_module: types.ModuleType,
    redirect_targets: dict[str, tuple[str, ...]],
    module_anchors: dict[str, tuple[str, ...]],
) -> None:
    """把门面模块的类替换为重定向模块类（幂等）。

    Args:
        gateway_module: 门面模块（sys.modules 中的实例）。
        redirect_targets: 符号 → 消费子模块名元组。
        module_anchors: 子模块名 → 锚点函数名元组。
    """
    redirect_cls = make_redirect_module(redirect_targets, module_anchors)
    if type(gateway_module) is not redirect_cls:
        gateway_module.__class__ = redirect_cls
