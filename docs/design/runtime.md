# Runtime 设计文档

## 概述

Runtime 是 LLM 的调用接口。它封装了具体的 provider（Claude Code CLI / Codex CLI / Anthropic API 等），
提供统一的 `exec()` 方法调用 LLM。

**核心设计：一个 runtime 就是一个 session，1:1 关系。**

- 创建 runtime = 创建 session
- 关闭 runtime = 关闭 session
- 想要新 session？创建新 runtime

没有 reset，没有 new_session。

## 生命周期

```
create_runtime() → runtime 对象（= 一个 session）
    ↓
runtime.exec() → 创建 exec 子节点，调 LLM
runtime.exec() → 再创建一个 exec 子节点，调 LLM
    ↓
runtime.close() → 释放资源，之后 exec() 报错
```

每次 `exec()` 调用会在当前函数节点下创建一个 exec 子节点（`node_type="exec"`），
然后通过 `summarize()` 读取上下文树构建 LLM 输入。

### 三个生命周期方法

| 方法 | 作用 |
|------|------|
| `create_runtime()` | 创建 runtime，自动检测 provider |
| `runtime.exec()` | 调用 LLM |
| `runtime.close()` | 释放资源，标记关闭 |

### with 语法

```python
with create_runtime() as rt:
    result = rt.exec(content="hello")
# 自动 close
```

### 关闭后不可用

```python
rt = create_runtime()
rt.close()
rt.exec("hello")  # → RuntimeError: Runtime is closed.
```

## 自动注入

`@agentic_function` 装饰器通过 `_current_runtime`（ContextVar）自动管理 runtime。
函数不需要手动创建或传递 runtime。

### 情况 1：不传 runtime（入口函数）

```python
polish_text(text="hello")
```

- `_inject_runtime` 检测到 `runtime=None`
- `_current_runtime` ContextVar 也是 None
- 自动 `create_runtime()`，设置 ContextVar
- 函数结束后自动 `close()` + 清理 ContextVar

### 情况 2：不传 runtime（子函数）

```python
@agentic_function
def gui_agent(task, runtime=None):
    _gui_step(task=task)  # 没传 runtime

@agentic_function
def _gui_step(task, runtime=None):
    runtime.exec(...)  # 自动拿到 gui_agent 的 runtime
```

- `_inject_runtime` 检测到 `runtime=None`
- `_current_runtime` ContextVar 有值（gui_agent 的 runtime）
- 用 ContextVar 里的，不创建新的
- 不负责 close

### 情况 3：显式传 runtime

```python
rt = create_runtime()
polish_text(text="hello", runtime=rt)
# 子函数自动继承 rt
# 函数结束后不 close（调用方管）
rt.close()
```

- `_inject_runtime` 检测到 `runtime` 不是 None
- 把它放进 ContextVar（供子函数继承）
- 函数结束后不 close（`owns_runtime=False`）

## Provider 的 close() 实现

| Provider | close() 做什么 |
|----------|----------------|
| Claude Code | 杀掉 CLI 进程 + 标记关闭 |
| Codex | 清除 session_id + 标记关闭 |
| Gemini CLI | 清除 session_id + 标记关闭 |
| Anthropic API | 标记关闭（无状态，无需额外清理） |
| OpenAI API | 标记关闭（无状态） |
| Gemini API | 标记关闭（无状态） |

所有 provider 的 `close()` 最终都调用 `super().close()`，设置 `_closed=True`。

## Session vs API Provider

| | Session provider (CLI) | API provider |
|---|---|---|
| 例子 | Claude Code, Codex, Gemini CLI | Anthropic API, OpenAI API |
| 对话记忆 | CLI 进程/session 自己管 | 无，每次 exec() 独立 |
| 上下文注入 | 跳过 summarize()，只发 docstring | 用 summarize() 注入 context tree |
| `has_session` | True（首次 exec 后） | False |
| siblings 设置 | 不生效（session 自己记得） | 生效（注入历史） |

框架通过 `has_session` 自动区分，函数代码不需要关心用的是哪种 provider。

## 自动检测 Provider

`create_runtime()` 调用 `detect_provider()`，按优先级检测：

1. **环境变量** — `AGENTIC_PROVIDER` / `AGENTIC_MODEL`
2. **配置文件** — `~/.agentic/config.json`
3. **调用环境** — 检测是否在 Claude Code / Codex 里运行
4. **已安装的 CLI** — `claude` / `codex` / `gemini` 命令
5. **API Key** — `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`

## 并发安全

`_current_runtime` 是 `ContextVar`，每个线程和协程有独立的值。

```python
# 两个并发调用，各自有自己的 runtime，互不干扰
Thread 1: gui_agent(task="A")  → runtime A
Thread 2: gui_agent(task="B")  → runtime B
```

## 相关文件

- Runtime 基类：`agentic/runtime.py`
- 自动注入逻辑：`agentic/function.py`（`_inject_runtime`、`_current_runtime`）
- Provider 实现：`agentic/providers/` 下各文件
- 自动检测：`agentic/providers/__init__.py`（`detect_provider`、`create_runtime`）
