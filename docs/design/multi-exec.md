# 两类节点：函数节点 + LLM 调用节点

## 背景

当前上下文树只有一种节点（函数节点）。`exec()` 在函数节点内部记录 LLM 交互（`raw_reply`, `exchanges`），
但 exec 本身不产生树节点。这导致：
1. 多次 exec 的记录需要额外的 `exchanges` 列表（hack）
2. `exec()` 承担了上下文构建的职责（不该是它的事）
3. 树结构没有真实反映执行过程

## 设计方向

**两种节点**：
- **函数节点**：`@agentic_function` 创建，代表一个函数调用
- **LLM 调用节点**：`exec()` 创建，代表一次 LLM 交互

**职责分离**：
- `exec()` 只管 LLM 的输入输出（创建 exec 节点、调 `_call()`、记录结果）
- 上下文结构（preamble 冻结、历史渲染）由函数节点（`Context`）自己管理

## 树结构示例

```
my_func (函数节点, running)
├── _exec (LLM 节点, done)     ← 第1次 exec: "分析这个文件"
├── helper (函数节点, done)     ← 两次 exec 之间调用的子函数
└── _exec (LLM 节点, running)  ← 第2次 exec: "根据分析结果修复"
```

完成后，外部看 my_func（作为兄弟节点）：
```
summary:  my_func(file="x.py") → "修复完成"
detail:   展开显示所有子节点（exec + helper）
```

## 上下文模型

上下文是一个**只增不减的文档**，从函数开始运行起就存在。

### 三个规则

1. **Preamble 冻结**：树上下文（祖先 + 兄弟）+ docstring 在第一次 exec 时计算，之后不再重新计算。
2. **文档只增不减**：每次 exec 追加一个 LLM 节点。子函数调用也作为节点出现。上下文单调增长。
3. **外部视角不变**：多次 exec 的函数完成后，对兄弟节点的呈现与单次 exec 完全一致。

### 第 1 次 exec 的 LLM 输入

```
[祖先链]
    my_func(file="x.py")              ← 父函数（祖先）
        """my_func 的 docstring"""
    [无兄弟]
    _exec()  <-- Current Call          ← 当前 LLM 节点
→ Current Task:
    分析这个文件
```

### 第 2 次 exec 的 LLM 输入（中间调了 helper）

```
[祖先链]
    my_func(file="x.py")              ← 父函数（祖先，preamble 冻结）
        """my_func 的 docstring"""     ← 包含在冻结的 preamble 中
    → 分析这个文件                      ← 第1次 exec 作为兄弟
    ← 文件有 3 个 bug...
    helper(data=...) → {valid: true}   ← 子函数作为兄弟
    _exec()  <-- Current Call          ← 当前 LLM 节点
→ Current Task:
    根据分析结果修复
```

### Docstring 处理

上下文模型中，docstring 属于父函数节点，在 summarize 的祖先链中渲染。
概念上它只出现一次（在 preamble 中）。

实现上：
- **API（无状态）**：每次 exec 都发送完整 preamble（含 docstring），通过 prompt cache 命中前缀
- **Session/Client（有状态）**：preamble 在 session 中已有，只发新内容

## 实现方案

### 1. Context 新增字段和方法

```python
@dataclass
class Context:
    # 新增
    node_type: str = "function"
    # "function" — @agentic_function 创建的函数节点
    # "exec"     — runtime.exec() 创建的 LLM 调用节点

    _frozen_preamble: Optional[str] = field(default=None, repr=False)
    # 冻结的 preamble。首次 exec 时计算并缓存。
    # 不序列化 — 运行时缓存。

    def build_exec_context(self, runtime: "Runtime") -> Optional[str]:
        """为下一次 exec 构建上下文。由函数节点调用。

        首次调用：计算 preamble（通过 summarize）并冻结。
        后续调用：冻结 preamble + 渲染已完成的子节点（exec + 函数）。
        """
        if runtime.has_session:
            if self._frozen_preamble is None:
                self._frozen_preamble = self.prompt or None
            return self._frozen_preamble

        if self._frozen_preamble is None:
            # 首次 exec：计算并冻结
            kwargs = dict(self._summarize_kwargs) if self._summarize_kwargs else {}
            kwargs["prompted_functions"] = runtime._prompted_functions
            self._frozen_preamble = self.summarize(**kwargs)
            if self.name:
                runtime._prompted_functions.add(self.name)
            return self._frozen_preamble

        # 后续 exec：frozen preamble + 已完成的子节点
        parts = [self._frozen_preamble]
        indent = "    " * max(self._depth() + 1 - self._base_depth(), 1)
        for child in self.children:
            if child.status == "running":
                break  # 当前正在运行的 exec 节点，不渲染
            if child.node_type == "exec":
                parts.append(
                    indent + "→ " + (child.params.get("_content", "")[:300])
                    + "\n" + indent + "← " + (child.raw_reply or "")[:500]
                )
            else:
                # 子函数节点，用常规渲染
                parts.append(child._render_traceback(indent, child.render))
        return "\n".join(parts)
```

### 2. runtime.exec() 精简

```python
def exec(self, content, context=None, response_format=None, model=None):
    if self._closed:
        raise RuntimeError("Runtime is closed.")
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]

    parent_ctx = _current_ctx.get(None)
    use_model = model or self.model
    content_text = "\n".join(b["text"] for b in content if b.get("type") == "text")

    # --- 创建 LLM 调用节点 ---
    exec_ctx = None
    if parent_ctx is not None:
        exec_ctx = Context(
            name="_exec",
            node_type="exec",
            params={"_content": content_text},
            parent=parent_ctx,
            start_time=time.time(),
            render="result",
        )
        parent_ctx.children.append(exec_ctx)
        _emit_event("node_created", exec_ctx)

    # --- 上下文：由父函数构建 ---
    if context is None and parent_ctx is not None:
        context = parent_ctx.build_exec_context(self)

    # --- 合并 content 到 context ---
    full_content = _merge_content(context, content, parent_ctx)

    # --- 调 LLM（带重试）---
    attempts = exec_ctx.attempts if exec_ctx is not None else []
    for attempt in range(self.max_retries):
        try:
            reply = self._call(full_content, model=use_model, response_format=response_format)
            attempts.append({"attempt": attempt + 1, "reply": reply, "error": None})
            if exec_ctx is not None:
                exec_ctx.raw_reply = reply
                exec_ctx.output = reply
                exec_ctx.status = "success"
                exec_ctx.end_time = time.time()
                _emit_event("node_completed", exec_ctx)
                parent_ctx.raw_reply = reply  # 向后兼容
            return reply
        except (TypeError, NotImplementedError):
            raise
        except Exception as e:
            attempts.append(...)
            if attempt == self.max_retries - 1:
                if exec_ctx is not None:
                    exec_ctx.error = str(e)
                    exec_ctx.status = "error"
                    exec_ctx.end_time = time.time()
                    _emit_event("node_completed", exec_ctx)
                raise ...
```

**关键设计**：
- `exec()` **不修改 `_current_ctx`**。函数节点始终是当前上下文。
- exec 节点是函数节点的子节点，和子函数调用并列。
- 上下文由父函数的 `build_exec_context()` 构建。
- `exec()` 只管 LLM 调用和 exec 节点的生命周期。

### 3. _merge_content 提取

从 exec() 中提取 content 合并逻辑（缩进、"→ Current Task:" 标记）为模块级函数。
去掉 `ctx.parent` 守卫，让顶层函数也能正确合并。

### 4. 清理 exchanges 字段

`exchanges` 列表不再需要 — 信息已在树的 exec 子节点中。
保留 `raw_reply` 指向最后一个 exec 节点的 reply（向后兼容）。

### 5. _render_traceback 更新

exec 节点的渲染：
```python
if self.node_type == "exec":
    content_preview = self.params.get("_content", "")[:200]
    if level == "result":
        return f"{indent}→ {content_preview}\n{indent}← {(self.raw_reply or '')[:300]}"
    # detail: 更完整
    return f"{indent}→ {content_preview}\n{indent}← {(self.raw_reply or '')[:500]}"
```

### 6. _to_dict / from_dict

添加 `node_type` 字段的序列化。

## API vs Session 实现差异

| | API（无状态） | Session/Client |
|---|---|---|
| Preamble | 每次 exec 完整发送（冻结缓存 + prompt cache） | 首次发送，session 记住 |
| 之前的 exec 结果 | 通过 build_exec_context 渲染子节点 | session 已有 |
| 当前 Task | 合并到 context 末尾 | 只发新内容 |

## 需要修改的文件

1. **`agentic/context.py`** — node_type, _frozen_preamble, build_exec_context(), _render_traceback(), 序列化
2. **`agentic/runtime.py`** — exec() 创建 exec 节点 + 调 build_exec_context, async_exec() 同步, _merge_content 提取
3. **`agentic/visualize/static/js/ui.js`** — exec 节点的视觉区分
4. **`tests/test_runtime.py`** — 多次 exec 测试, frozen preamble 测试
5. **`tests/test_async.py`** — 异步版本

## 验证

```bash
# 全部测试通过
pytest tests/ -v

# 手动验证树结构
python -c "
from agentic import agentic_function, Runtime
rt = Runtime(call=lambda c, **kw: 'ok')

@agentic_function
def demo():
    '''My prompt.'''
    rt.exec('first')
    rt.exec('second')

demo()
print(demo.context.tree())
# 应显示：
# demo
# ├── _exec → ok
# └── _exec → ok
"
```

## 待讨论

- [ ] exec 节点是否需要自己的 docstring？（目前设计为空）
- [ ] build_exec_context 中子节点渲染的截断策略（content 300 chars, reply 500 chars 够吗？）
- [ ] 已有的 `exchanges` 字段是否完全移除，还是保留作为兼容层？
- [ ] 可视化器中 exec 节点的样式（不同颜色/图标？）
- [ ] ask_user() 是否也应该创建一个专门的节点？
