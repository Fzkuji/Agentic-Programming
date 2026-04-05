# create & fix

> Source: [`agentic/meta_function.py`](../../agentic/meta_function.py)

Meta function。用自然语言描述生成新的 `@agentic_function`，以及修复失败的生成函数。

`create()` 本身也是一个 `@agentic_function`——它用 Runtime 让 LLM 写代码，在沙箱中执行，返回一个可调用的函数。

---

## Function: `create()`

```python
@agentic_function
def create(description: str, runtime: Runtime, name: str = None) -> callable
```

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `description` | `str` | *(必填)* | 函数应该做什么。尽量具体，说明参数和期望输出 |
| `runtime` | `Runtime` | *(必填)* | Runtime 实例。用于生成代码，也注入到生成的函数中 |
| `name` | `str \| None` | `None` | 覆盖生成函数的名称。`None` = 使用 LLM 选择的名称 |

### 返回值

`callable` — 一个标准的 `@agentic_function`，具备完整的 Context 追踪。

### 异常

| 异常 | 原因 |
|------|------|
| `SyntaxError` | 生成的代码有语法错误 |
| `ValueError` | 代码包含 import、使用 async、执行失败、或没有定义 `@agentic_function` |

---

## 安全机制

生成的代码在受限环境中执行：

| 限制 | 说明 |
|------|------|
| 禁止 import | `import` 和 `from ... import` 语句被拦截 |
| 禁止 async | 只允许同步函数 |
| 受限 builtins | 没有 `exec`、`eval`、`open`、`__import__`、文件 I/O |
| 语法校验 | 执行前先编译检查 |

生成的函数只能访问 `agentic_function`（装饰器）和 `runtime`（传入的 Runtime 实例）。

---

## 使用方式

### 基本用法

```python
from agentic import Runtime
from agentic.meta_function import create

runtime = Runtime(call=my_llm, model="sonnet")

# 用描述创建函数
summarize = create(
    "Summarize text into 3 bullet points. Take a 'text' parameter.",
    runtime=runtime,
)

# 像普通函数一样调用
result = summarize(text="Long article about AI...")
print(result)
```

### 指定名称

```python
explain = create(
    "Explain a technical concept using a simple analogy. Take a 'concept' parameter.",
    runtime=runtime,
    name="explain_concept",
)

print(explain.__name__)  # "explain_concept"
result = explain(concept="prompt caching")
```

### 生成的函数使用 LLM

```python
# 如果描述中涉及"分析"、"判断"等需要推理的任务，
# LLM 会生成一个内部调用 runtime.exec() 的函数
rate = create(
    "Rate a business idea 1-10 with reasoning. Take an 'idea' parameter.",
    runtime=runtime,
)

result = rate(idea="AI-generated bedtime stories for kids")
# LLM 生成的函数内部会调用 runtime.exec() 来做评估
```

### 查看 Context

```python
# create() 本身的 Context
print(create.context.tree())

# 生成的函数的 Context
result = explain(concept="KV cache")
print(explain.context.tree())
```

### 生成的函数可以嵌套

```python
@agentic_function
def analyze_topic(topic):
    """Analyze a topic using dynamically created functions."""
    explain = create(f"Explain {topic} simply", runtime=runtime)
    critique = create(f"Critique common misconceptions about {topic}", runtime=runtime)
    
    explanation = explain()
    criticism = critique()
    return f"Explanation: {explanation}\n\nCritique: {criticism}"
```

---

## Function: `fix()`

```python
@agentic_function
def fix(
    fn,
    runtime: Runtime,
    instruction: str = None,
    name: str = None,
    on_question: Callable[[str], str] = None,
    max_rounds: int = 5,
) -> callable
```

当已有函数运行失败、输出格式不稳定、或你想做定向改写时，用 `fix()`。它会自动从 `fn` 中提取源码、函数名，以及最近 Context 树里的错误 / retry 历史，再交给 LLM 重写。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fn` | `callable` | *(必填)* | 要修复的函数对象。通常是 `create()` 生成的函数，也可以是手写的 `@agentic_function` |
| `runtime` | `Runtime` | *(必填)* | 用来分析与重写函数的 Runtime |
| `instruction` | `str \| None` | `None` | 额外修复要求，例如“改成返回 JSON” |
| `name` | `str \| None` | `None` | 覆盖修复后函数的名称 |
| `on_question` | `Callable[[str], str] \| None` | `None` | 当 LLM 返回 `QUESTION: ...` 时的回调。返回值会作为补充信息继续修复 |
| `max_rounds` | `int` | `5` | 最多允许多少轮问答 / 重写 |

### 返回值

`callable` — 修复后的函数。

### 异常

| 异常 | 原因 |
|------|------|
| `SyntaxError` | 修复后的代码仍有语法错误 |
| `ValueError` | 修复后的代码包含不允许的 import、async、或无法执行 |
| `RuntimeError` | 超过 `max_rounds` 仍未得到可编译代码 |

---

### 基本用法

```python
from agentic.meta_function import create, fix

runtime = Runtime(call=my_llm, model="sonnet")

analyze = create("Analyze sentiment of text", runtime=runtime)

try:
    result = analyze(text="This is great!")
except Exception:
    analyze = fix(
        fn=analyze,
        runtime=runtime,
        instruction="Return exactly one word: positive, negative, or neutral.",
    )
    result = analyze(text="This is great!")
```

### `fix()` 会自动拿到什么

`fix(fn=..., runtime=...)` 会自动收集：

- `fn` 的源码（若可读）
- `fn.__doc__` / 名称，用来恢复原始意图
- `fn.context` 里的失败记录，包括 retry attempts 和异常信息
- 你额外传入的 `instruction`

所以新版 API 不再需要手动传 `description`、`code`、`error_log`。

### 交互式修复：`on_question`

```python
def answer(question: str) -> str:
    if "JSON" in question:
        return "Return a JSON object with keys sentiment and confidence."
    return "Prefer the safest interpretation."

fixed = fix(fn=analyze, runtime=runtime, on_question=answer)
```

如果模型不确定修哪里，可以先问，再继续生成最终代码。

### create + fix + retry 模式

```python
def create_with_retry(description, runtime, sample_kwargs, attempts=3):
    fn = create(description, runtime=runtime)

    for _ in range(attempts):
        try:
            fn(**sample_kwargs)
            return fn
        except Exception:
            fn = fix(
                fn=fn,
                runtime=runtime,
                instruction="Make the output schema explicit and validate edge cases.",
            )

    return fn
```

这个模式适合“先生成，再用真实样例验证，不对就继续修”的工作流。
