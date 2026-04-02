# Agentic Context

> 每个 Agentic Function 用 `with agentic()` 声明自己。层级由嵌套自动决定，不需要手动传 ctx。

---

## Context

一个函数的执行记录。

```python
@dataclass
class Context:
    name: str               # 函数名
    prompt: str = ""        # docstring
    input: dict = None      # 发给 LLM 的数据
    output: Any = None      # LLM 返回的结果
    error: str = ""         # 错误信息
    children: list = None   # 子函数的 Context
    parent: Context = None  # 父 Context
    level: str = "summary"  # 对外暴露粒度：trace / detail / summary / result
```

---

## 核心机制：`with agentic()`

用 Python 的 context manager + `contextvars` 自动追踪调用层级。**用户不需要手动传 ctx。**

```python
from agentic import agentic

def navigate(target):
    with agentic("navigate") as ctx:
        obs = observe(task=f"find {target}")     # 自动是 navigate 的 child
        result = act(target=target, loc=obs["location"])  # 自动是 navigate 的 child
        ctx.output = {"success": True}
        return ctx.output

def observe(task):
    with agentic("observe", prompt="Look at the screen...") as ctx:
        ctx.input = {"task": task}
        
        img = take_screenshot()
        ocr = run_ocr(img)           # 自动是 observe 的 child
        elements = detect_all(img)    # 自动是 observe 的 child
        
        # LLM 调用时读取兄弟摘要
        siblings = ctx.sibling_summaries()
        reply = llm_call(prompt=ctx.prompt, input=ctx.input, context=siblings)
        
        ctx.output = parse(reply)
        return ctx.output

def act(target, loc):
    with agentic("act", prompt="Click the target...") as ctx:
        ctx.input = {"target": target, "location": loc}
        
        # act 能看到 observe 的摘要
        siblings = ctx.sibling_summaries()
        # → ["observe: {target_visible: true, location: [347, 291]}"]
        
        click(loc)
        ctx.output = {"clicked": True}
        return ctx.output
```

---

## 规则

1. **每个函数用 `with agentic(name)` 声明自己**
2. **层级由 `with` 嵌套自动决定**（不需要手动传 ctx）
3. **在 `with` 内调用的子函数，自动成为 children**
4. **`sibling_summaries()` 返回同层前面兄弟的摘要**
5. **异常自动捕获到 `ctx.error`**

---

## 为什么不需要手动传 ctx

Python 的 `contextvars` 自动追踪当前在哪一层：

```python
with agentic("navigate"):        # 当前层 = navigate
    with agentic("observe"):      # 当前层 = observe，parent = navigate
        with agentic("run_ocr"):  # 当前层 = run_ocr，parent = observe
            ...
    # 退出 observe，当前层回到 navigate
    with agentic("act"):          # 当前层 = act，parent = navigate
        ...
```

**不可能传错。层级由代码结构强制决定。**

---

## 调用栈

执行后 Context 形成树：

```
root
└── navigate
    ├── observe
    │   ├── run_ocr
    │   └── detect_all
    └── act
```

---

## Level（暴露粒度）

子函数的信息传给兄弟时，按 level 裁剪：

| Level | 内容 | 示例 |
|-------|------|------|
| `trace` | 所有细节 | prompt + 原始 OCR 数据 + LLM 原始回复 |
| `detail` | 输入输出 | input: 77 OCR items, output: {found: true} |
| `summary` | 一句话 | "observe: found login button at (347, 291)" |
| `result` | 只有返回值 | {target_visible: true} |

默认 `summary`。

---

## Traceback

报错时：
```
Agentic Traceback:
  navigate(target="login") → error
    observe(task="find login") → success, 1200ms
    act(target="login") → error: "element not interactable"
```

正常时：
```
navigate ✓ 3200ms
├── observe ✓ 1200ms → found 156 elements
├── act ✓ 820ms → clicked login
└── verify ✓ 650ms → verified
```

---

## 持久化

```python
root.save("logs/run.jsonl")    # 机器可读
root.save("logs/run.md")       # 人类可读
```

---

## 核心就三件事

1. **`with agentic()` 自动管理层级**（不可能传错）
2. **Level 控制暴露粒度**（兄弟只看摘要）
3. **LLM 调用时从 Context 读取上下文**（`sibling_summaries()`）
