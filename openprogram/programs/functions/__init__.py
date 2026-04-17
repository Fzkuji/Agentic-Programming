"""
openprogram.programs.functions — @agentic_function 集合，按来源分三类。
"""

import importlib
from types import ModuleType


def resolve_function_module(name: str) -> ModuleType:
    """按名字在 buildin → third_party → meta 三个子包中查找模块。

    CLI / Web UI 里很多地方需要根据用户给的函数名动态加载模块。
    不暴露内部分类，调用方只给函数名就行。
    """
    for subpkg in ("buildin", "third_party", "meta"):
        try:
            return importlib.import_module(f"openprogram.programs.functions.{subpkg}.{name}")
        except ImportError:
            continue
    raise ImportError(
        f"agentic function {name!r} not found in buildin/, third_party/, or meta/"
    )

