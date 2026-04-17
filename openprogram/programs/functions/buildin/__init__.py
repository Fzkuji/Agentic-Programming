"""
openprogram.programs.functions.buildin — 框架内置的 @agentic_function。

顶层暴露的：
    general_action  —— 给 agent 一个完全开放的任务，让它自己收敛
    agent_loop      —— 自主 plan-act-evaluate 循环
    wait            —— 让 LLM 根据上下文决定等多久
    deep_work       —— plan → execute → evaluate → refine 的质量循环
    init_research   —— 初始化研究项目目录骨架
"""

from openprogram.programs.functions.buildin.general_action import general_action
from openprogram.programs.functions.buildin.agent_loop import agent_loop
from openprogram.programs.functions.buildin.wait import wait
from openprogram.programs.functions.buildin.deep_work import deep_work
from openprogram.programs.functions.buildin.init_research import init_research

__all__ = [
    "general_action",
    "agent_loop",
    "wait",
    "deep_work",
    "init_research",
]
