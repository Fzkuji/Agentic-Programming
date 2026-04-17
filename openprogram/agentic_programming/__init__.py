"""
openprogram.agentic_programming — 核心引擎，Agentic Programming 的哲学主体。

这里只放三样东西：
    1. @agentic_function  —— 让一个 Python 函数具备"调 LLM"的能力
    2. Runtime            —— LLM 调用的运行时基类
    3. Context            —— 调用发生后自动累积的上下文树
       （及其附带的 ask_user / FollowUp / run_with_follow_up 运行时原语）

零下游依赖。providers / programs / webui 都只能依赖 agentic_programming，不能反向。
"""

from openprogram.agentic_programming.context import (
    Context, FollowUp, run_with_follow_up, ask_user, set_ask_user,
)
from openprogram.agentic_programming.function import (
    agentic_function, traced, auto_trace_module, auto_trace_package,
)
from openprogram.agentic_programming.runtime import Runtime
from openprogram.agentic_programming.session import Session

__all__ = [
    "agentic_function",
    "traced",
    "auto_trace_module",
    "auto_trace_package",
    "Runtime",
    "Context",
    "FollowUp",
    "run_with_follow_up",
    "ask_user",
    "set_ask_user",
    "Session",
]
