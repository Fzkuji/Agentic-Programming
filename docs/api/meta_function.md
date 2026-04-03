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
def fix(description: str, code: str, error_log: str, runtime: Runtime, name: str = None) -> callable
```

当 `create()` 生成的函数运行失败时，用 `fix()` 来修复。它把原始代码和错误日志发给 LLM，让 LLM 重写一个修复版本。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `description` | `str` | *(必填)* | 原始任务描述（和 create 时相同） |
| `code` | `str` | *(必填)* | 失败的生成代码 |
| `error_log` | `str` | *(必填)* | 错误日志（包含失败尝试的错误信息） |
| `runtime` | `Runtime` | *(必填)* | Runtime 实例 |
| `name` | `str \| None` | `None` | 覆盖修复后函数的名称 |

### 返回值

`callable` — 修复后的 `@agentic_function`。

### 异常

| 异常 | 原因 |
|------|------|
| `SyntaxError` | 修复后的代码仍有语法错误 |
| `ValueError` | 修复后的代码包含 import、async 等 |

---

### 使用方式

```python
from agentic.meta_function import create, fix

runtime = Runtime(call=my_llm, model="sonnet")

# 创建函数
analyze = create("Analyze sentiment of text", runtime=runtime)

# 尝试运行
try:
    result = analyze(text="This is great!")
except Exception as e:
    # 如果失败，用 fix() 修复
    analyze = fix(
        description="Analyze sentiment of text",
        code="<the generated code>",
        error_log=str(e),
        runtime=runtime,
    )
    result = analyze(text="This is great!")
```

### create + fix 自动重试模式

```python
def create_with_retry(description, runtime, max_attempts=3):
    """Create a function, auto-fix if it fails."""
    fn = create(description, runtime=runtime)
    errors = []
    
    for attempt in range(max_attempts):
        try:
            # Test with a sample input
            fn(text="test")
            return fn
        except Exception as e:
            errors.append(f"Attempt {attempt + 1}: {e}")
            fn = fix(
                description=description,
                code="<source>",
                error_log="\n".join(errors),
                runtime=runtime,
            )
    
    return fn  # Best effort
```
