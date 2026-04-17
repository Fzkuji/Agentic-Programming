"""
openprogram.programs — 用户程序层（application + functions）。

applications/   完整应用：CLI 可直跑、Web UI 可一键启动
functions/      @agentic_function 集合
                ├── meta/         元函数：用 LLM 创建/修改 agentic_function
                ├── buildin/      框架内置工具函数（agent_loop / deep_work / ...）
                └── third_party/  自动生成 / 外部示例
"""
