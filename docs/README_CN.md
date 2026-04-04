<p align="center">
  <h1 align="center">🧬 Agentic Programming</h1>
  <p align="center">
    <strong>会思考的 Python 函数。</strong><br>
    一种 Python 与大模型协同执行函数的编程范式。
  </p>
  <p align="center">
    <a href="#快速开始">快速开始</a> •
    <a href="#核心思想">核心思想</a> •
    <a href="#api">API</a> •
    <a href="../README.md">English</a>
  </p>
</p>

> 🚀 **这是一个范式提案。** 我们提出了一种全新的 LLM 编程思路。这里的代码是参考实现——欢迎你基于这些想法，用任何语言、任何场景，构建自己的版本。

---

## 问题

现在的 LLM Agent 是这样工作的：

```
🧠 LLM：“我需要找到登录按钮”
   ↓ 调用截图工具
🧠 LLM：“我看到 (200, 300) 有个按钮，点击它”
   ↓ 调用点击工具
🧠 LLM：“成功了吗？我再看看”
   ↓ 又调用截图工具
🧠 LLM：“好像没反应，试试别的…”
   ↓ 用不同坐标再点一次
   ...(再来 10 轮)
```

**LLM 就是调度器。** 它决定做什么、什么时候做、怎么做。这带来了真正的问题：

- 🎰 **不可控** — 你设计了工作流 A → B → C，但 LLM 可能跳过 B、重复 A、或自己发明步骤 D。不管用 skills、prompt 还是 system message，都无法 *强制* 它按你的路径走。
- 📈 **上下文爆炸** — 每次往返都往对话里加内容。到第 10 步时，LLM 已经在读 50K token 的历史记录，就为了决定下一次点哪里。
- 🎯 **没有保证** — 要 JSON 输出？LLM 可能加上 markdown。要恰好 3 步？它可能做 7 步。LLM *理解* 你的指令，但不 *执行* 它们。

核心问题：**LLM 控制了流程。** 你让一个推理引擎同时当调度器、状态机和格式验证器。这不是它擅长的。

## 思路

**把流程控制权还给 Python。让 LLM 专注推理。**

```
🐍 Python：“步骤 1：截图 + OCR”
   ↓ 确定性代码，瞬间完成
🧠 LLM：“我看到 (200, 300) 有登录按钮”       ← 只做推理
   ↓
🐍 Python：“步骤 2：点击 (200, 300)”
   ↓ 确定性代码，瞬间完成
🧠 LLM：“登录成功，看到仪表盘了”          ← 只做推理
   完成。只调了 2 次 LLM，不是 10 次。
```

Python 负责调度、循环、错误处理和数据流。LLM 只回答问题。

```python
@agentic_function
def observe(task):
    """观察屏幕，描述你看到的内容。"""
    
    img = take_screenshot()       # Python：确定性操作
    ocr = run_ocr(img)            # Python：确定性操作
    
    return runtime.exec(content=[ # LLM：推理
        {"type": "text", "text": f"任务: {task}\nOCR: {ocr}"},
        {"type": "image", "path": img},
    ])
```

**Docstring = Prompt。** 改注释就改行为。其他都是普通 Python。

---

## 快速开始

```bash
pip install -e .
```

```python
from agentic import agentic_function, Runtime

runtime = Runtime(call=my_llm, model="sonnet")

@agentic_function
def greet(name):
    """用创意的方式打招呼。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"用创意的方式跟 {name} 打招呼。"},
    ])

result = greet(name="World")
print(result)                    # "嘿 World！🌍✨"
print(greet.context.tree())      # 执行追踪
```

---

## 核心思想

### 1. 函数调用大模型

每个 `@agentic_function` 都可以调 `runtime.exec()` 来请求 LLM。框架自动把执行上下文（之前发生了什么）注入到 prompt 中。

```python
@agentic_function
def login_flow(username, password):
    """完成登录流程。"""
    observe(task="找到登录表单")
    click(element="登录按钮")
    return verify(expected="仪表盘")
```

### 2. 上下文自动追踪

每次调用创建一个 **Context** 节点，节点组成树：

```
login_flow ✓ 8.8s
├── observe ✓ 3.1s → "在 (200, 300) 处找到登录表单"
├── click ✓ 2.5s → "点击了登录按钮"
└── verify ✓ 3.2s → "确认进入仪表盘"
```

`verify` 调用 LLM 时，自动看到 `observe` 和 `click` 的返回结果。不需要手动管理上下文。

### 3. 函数生成函数

```python
from agentic.meta_function import create

summarize = create("把文本总结成3个要点", runtime=runtime)
result = summarize(text="很长的文章...")
```

LLM 写代码，框架验证并沙箱执行。你得到一个真正的 `@agentic_function`。

### 4. 自动错误恢复

```python
runtime = Runtime(call=my_llm, max_retries=2)  # 失败自动重试

# 或者修复损坏的函数：
from agentic.meta_function import fix
fixed_fn = fix(fn=broken_fn, runtime=runtime, instruction="用 label 代替坐标")
```

---

## API

| 组件 | 功能 |
|------|------|
| [`@agentic_function`](api/agentic_function.md) | 装饰器。记录执行到 Context 树 |
| [`Runtime`](api/runtime.md) | LLM 连接。`exec()` 自动注入上下文 |
| [`Context`](api/context.md) | 执行树。`tree()`、`save()`、`traceback()` |
| [`create()`](api/meta_function.md) | 从描述生成新函数 |
| [`fix()`](api/meta_function.md) | 用 LLM 修复损坏的函数 |

### 内置 Provider

```python
from agentic.providers import AnthropicRuntime   # Claude（支持 prompt caching）
from agentic.providers import OpenAIRuntime       # GPT（支持 response_format）
from agentic.providers import GeminiRuntime       # Gemini
from agentic.providers import ClaudeCodeRuntime   # Claude Code CLI（无需 API key）
```

---

## 对比

|  | Tool-Calling / MCP | Agentic Programming |
|--|---------------------|---------------------|
| **谁调度？** | LLM | Python |
| **函数包含** | 纯代码 | 代码 + LLM 推理 |
| **上下文** | 一整段对话 | 结构化的树 |
| **Prompt** | 写死在 agent 里 | Docstring = prompt |

MCP 是 *传输层*。Agentic Programming 是 *执行模型*。两者正交。

---

## 安装

```bash
pip install -e .                    # 核心（零依赖）
pip install -e ".[anthropic]"       # + Claude
pip install -e ".[openai]"          # + GPT
pip install -e ".[gemini]"          # + Gemini
pip install -e ".[all]"             # 全部
```

## 许可证

MIT
