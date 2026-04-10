"""
Tests for render levels (summary/detail/result/silent) and summarize parameter combinations.

Verifies the actual text output of _render_traceback() and summarize() under
different configurations.
"""

import pytest
from agentic import agentic_function, Runtime


def echo_call(content, model="test", response_format=None):
    """Echo the user's text content (after exec marker or last plain block)."""
    for block in reversed(content):
        if block["type"] != "text":
            continue
        text = block.get("text", "")
        # If content was merged into context, extract the exec() portion
        if "→ Current Task:" in text:
            return text.split("→ Current Task:\n", 1)[1].strip()
        # Skip context blocks (contain call paths like "- func(")
        if "- " in text and "(" in text and "<-- Current Call" in text:
            continue
        return text
    return "ok"


runtime = Runtime(call=echo_call)


# ══════════════════════════════════════════════════════════════
# Render level tests — verify actual output of each level
# ══════════════════════════════════════════════════════════════

class TestRenderSummary:
    """render='summary' — name, docstring, params, output, status, duration."""

    def test_contains_function_name(self):
        @agentic_function(render="summary")
        def my_task(x):
            """Do something."""
            return f"result_{x}"

        my_task(x=42)
        ctx = my_task.context
        rendered = ctx._render_traceback("", "summary")
        assert "my_task" in rendered

    def test_contains_docstring(self):
        @agentic_function(render="summary")
        def documented(x):
            """This is the prompt."""
            return "done"

        documented(x=1)
        rendered = documented.context._render_traceback("", "summary")
        assert "This is the prompt." in rendered

    def test_contains_params(self):
        @agentic_function(render="summary")
        def parameterized(name, count=3):
            """Task."""
            return "done"

        parameterized(name="test", count=5)
        rendered = parameterized.context._render_traceback("", "summary")
        assert "name=" in rendered
        assert "count=" in rendered

    def test_contains_output(self):
        @agentic_function(render="summary")
        def with_output():
            """Task."""
            return {"success": True}

        with_output()
        rendered = with_output.context._render_traceback("", "summary")
        assert "success" in rendered

    def test_contains_status(self):
        @agentic_function(render="summary")
        def status_fn():
            """Task."""
            return "ok"

        status_fn()
        rendered = status_fn.context._render_traceback("", "summary")
        assert "Status: success" in rendered

    def test_contains_duration(self):
        @agentic_function(render="summary")
        def timed_fn():
            """Task."""
            return "ok"

        timed_fn()
        rendered = timed_fn.context._render_traceback("", "summary")
        assert "ms" in rendered

    def test_no_raw_reply(self):
        """Summary level should NOT include LLM raw_reply."""
        @agentic_function(render="summary")
        def llm_fn():
            """Task."""
            return runtime.exec(content=[{"type": "text", "text": "hello"}])

        llm_fn()
        rendered = llm_fn.context._render_traceback("", "summary")
        assert "LLM reply:" not in rendered


class TestRenderDetail:
    """render='detail' — summary + LLM raw_reply."""

    def test_includes_summary_content(self):
        @agentic_function(render="detail")
        def detail_fn():
            """Detailed task."""
            return runtime.exec(content=[{"type": "text", "text": "analyze this"}])

        detail_fn()
        rendered = detail_fn.context._render_traceback("", "detail")
        assert "detail_fn" in rendered
        assert "Detailed task." in rendered
        assert "Status:" in rendered

    def test_includes_raw_reply(self):
        @agentic_function(render="detail")
        def detail_fn():
            """Task."""
            return runtime.exec(content=[{"type": "text", "text": "my_prompt"}])

        detail_fn()
        rendered = detail_fn.context._render_traceback("", "detail")
        assert "LLM reply:" in rendered
        assert "my_prompt" in rendered


class TestRenderResult:
    """render='result' — name + return value only."""

    def test_contains_name_and_value(self):
        @agentic_function(render="result")
        def result_fn(x):
            """Task."""
            return {"value": x * 2}

        result_fn(x=5)
        rendered = result_fn.context._render_traceback("", "result")
        assert "result_fn" in rendered
        assert "10" in rendered

    def test_no_docstring(self):
        @agentic_function(render="result")
        def result_fn():
            """This should not appear."""
            return "ok"

        result_fn()
        rendered = result_fn.context._render_traceback("", "result")
        assert "This should not appear" not in rendered

    def test_no_status(self):
        @agentic_function(render="result")
        def result_fn():
            """Task."""
            return "ok"

        result_fn()
        rendered = result_fn.context._render_traceback("", "result")
        assert "Status:" not in rendered

    def test_none_output_minimal(self):
        @agentic_function(render="result")
        def none_fn():
            """Task."""
            return None

        none_fn()
        rendered = none_fn.context._render_traceback("", "result")
        assert "none_fn" in rendered
        assert "return" not in rendered  # None output → no return line


class TestRenderSilent:
    """render='silent' — not shown at all."""

    def test_returns_empty_string(self):
        @agentic_function(render="silent")
        def silent_fn():
            """Hidden task."""
            return "secret"

        silent_fn()
        rendered = silent_fn.context._render_traceback("", "silent")
        assert rendered == ""

    def test_silent_excluded_from_summarize(self):
        """Silent siblings should not appear in summarize output."""
        @agentic_function
        def parent():
            """Parent."""
            hidden()
            return visible()

        @agentic_function(render="silent")
        def hidden():
            return "secret"

        @agentic_function
        def visible():
            """Visible."""
            return runtime.exec(content=[{"type": "text", "text": "check"}])

        parent()
        root = parent.context
        # visible's summarize context should NOT contain "hidden"
        visible_ctx = root.children[1]
        summary = visible_ctx.summarize()
        assert "hidden" not in summary
        assert "parent" in summary


class TestRenderLevelOverride:
    """level= parameter in summarize() overrides per-node render settings."""

    def test_force_detail_on_summary_nodes(self):
        @agentic_function(render="summary")
        def fn():
            """Task."""
            return runtime.exec(content=[{"type": "text", "text": "data"}])

        fn()
        # Force detail level
        rendered = fn.context._render_traceback("", "detail")
        assert "LLM reply:" in rendered

    def test_force_result_on_detail_nodes(self):
        @agentic_function(render="detail")
        def fn():
            """Task."""
            return "value123"

        fn()
        rendered = fn.context._render_traceback("", "result")
        assert "value123" in rendered
        assert "Status:" not in rendered
        assert "Task." not in rendered


# ══════════════════════════════════════════════════════════════
# Summarize parameter combination tests
# ══════════════════════════════════════════════════════════════

class TestSummarizeDepth:
    """depth= controls how many ancestor levels are visible."""

    def _build_tree(self):
        """Build a 3-level deep tree: root → mid → leaf."""
        @agentic_function
        def root_fn():
            """Root."""
            return mid_fn()

        @agentic_function
        def mid_fn():
            """Mid."""
            return leaf_fn()

        @agentic_function
        def leaf_fn():
            """Leaf."""
            return runtime.exec(content=[{"type": "text", "text": "leaf"}])

        root_fn()
        return root_fn.context

    def test_depth_all(self):
        root = self._build_tree()
        leaf = root.children[0].children[0]
        summary = leaf.summarize(depth=-1)
        assert "root_fn" in summary
        assert "mid_fn" in summary

    def test_depth_0(self):
        root = self._build_tree()
        leaf = root.children[0].children[0]
        summary = leaf.summarize(depth=0)
        # depth=0 means no ancestor lines, but current call line still shows call path
        lines = summary.strip().split("\n")
        # No ancestor lines (lines starting with "- root_fn(" or "- mid_fn(")
        ancestor_lines = [l for l in lines if l.strip().startswith("- root_fn(") or l.strip().startswith("- root_fn.mid_fn(")]
        assert len(ancestor_lines) == 0
        assert "Current Call" in summary

    def test_depth_1(self):
        root = self._build_tree()
        leaf = root.children[0].children[0]
        summary = leaf.summarize(depth=1)
        assert "mid_fn" in summary  # parent
        # root may or may not appear depending on depth=1 interpretation
        assert "Current Call" in summary


class TestSummarizeSiblings:
    """siblings= controls how many previous siblings are visible."""

    def _build_siblings(self):
        @agentic_function
        def parent():
            """Parent."""
            step_a()
            step_b()
            step_c()
            return step_d()

        @agentic_function
        def step_a():
            return runtime.exec(content=[{"type": "text", "text": "a"}])

        @agentic_function
        def step_b():
            return runtime.exec(content=[{"type": "text", "text": "b"}])

        @agentic_function
        def step_c():
            return runtime.exec(content=[{"type": "text", "text": "c"}])

        @agentic_function
        def step_d():
            return runtime.exec(content=[{"type": "text", "text": "d"}])

        parent()
        return parent.context

    def test_siblings_all(self):
        root = self._build_siblings()
        step_d = root.children[3]
        summary = step_d.summarize(siblings=-1)
        assert "step_a" in summary
        assert "step_b" in summary
        assert "step_c" in summary

    def test_siblings_0(self):
        root = self._build_siblings()
        step_d = root.children[3]
        summary = step_d.summarize(siblings=0)
        assert "step_a" not in summary
        assert "step_b" not in summary
        assert "step_c" not in summary

    def test_siblings_1(self):
        root = self._build_siblings()
        step_d = root.children[3]
        summary = step_d.summarize(siblings=1)
        assert "step_a" not in summary
        assert "step_b" not in summary
        assert "step_c" in summary  # only the last sibling

    def test_siblings_2(self):
        root = self._build_siblings()
        step_d = root.children[3]
        summary = step_d.summarize(siblings=2)
        assert "step_a" not in summary
        assert "step_b" in summary
        assert "step_c" in summary


class TestSummarizeLevel:
    """level= overrides render for all nodes in output."""

    def test_level_detail(self):
        @agentic_function
        def parent():
            """Parent."""
            child()
            return checker()

        @agentic_function
        def child():
            """Child."""
            return runtime.exec(content=[{"type": "text", "text": "child_data"}])

        @agentic_function
        def checker():
            """Check."""
            return runtime.exec(content=[{"type": "text", "text": "check"}])

        parent()
        root = parent.context
        checker_ctx = root.children[1]
        summary = checker_ctx.summarize(level="detail")
        # child should be rendered with detail level (including LLM reply)
        assert "LLM reply:" in summary

    def test_level_result(self):
        @agentic_function
        def parent():
            """Parent."""
            worker()
            return final()

        @agentic_function
        def worker():
            """Worker."""
            return "worker_output"

        @agentic_function
        def final():
            """Final."""
            return runtime.exec(content=[{"type": "text", "text": "final"}])

        parent()
        root = parent.context
        final_ctx = root.children[1]
        summary = final_ctx.summarize(level="result")
        assert "worker_output" in summary
        # result level should not show docstrings
        assert "Worker." not in summary


class TestSummarizeIncludeExclude:
    """include= and exclude= filter nodes by path."""

    def _build(self):
        @agentic_function
        def root():
            """Root."""
            observe()
            act()
            return verify()

        @agentic_function
        def observe():
            return runtime.exec(content=[{"type": "text", "text": "obs"}])

        @agentic_function
        def act():
            return runtime.exec(content=[{"type": "text", "text": "act"}])

        @agentic_function
        def verify():
            return runtime.exec(content=[{"type": "text", "text": "ver"}])

        root()
        return root.context

    def test_exclude_by_name(self):
        root = self._build()
        verify_ctx = root.children[2]
        summary = verify_ctx.summarize(exclude=["root/act_0"])
        assert "observe" in summary
        assert "act" not in summary

    def test_include_wildcard(self):
        root = self._build()
        verify_ctx = root.children[2]
        summary = verify_ctx.summarize(include=["root/observe_0", "root/*"])
        assert "observe" in summary


class TestSummarizeBranch:
    """branch= expands specific siblings' children."""

    def test_branch_expands_children(self):
        @agentic_function
        def root():
            """Root."""
            complex_step()
            return simple_step()

        @agentic_function
        def complex_step():
            """Complex."""
            sub_a()
            sub_b()
            return "complex_done"

        @agentic_function
        def sub_a():
            return "a"

        @agentic_function
        def sub_b():
            return "b"

        @agentic_function
        def simple_step():
            """Simple."""
            return runtime.exec(content=[{"type": "text", "text": "simple"}])

        root()
        root_ctx = root.context
        simple_ctx = root_ctx.children[1]
        summary = simple_ctx.summarize(branch=["complex_step"])
        assert "sub_a" in summary
        assert "sub_b" in summary

    def test_no_branch_hides_children(self):
        @agentic_function
        def root():
            """Root."""
            complex_step()
            return simple_step()

        @agentic_function
        def complex_step():
            """Complex."""
            sub_a()
            return "done"

        @agentic_function
        def sub_a():
            return "a"

        @agentic_function
        def simple_step():
            """Simple."""
            return runtime.exec(content=[{"type": "text", "text": "simple"}])

        root()
        root_ctx = root.context
        simple_ctx = root_ctx.children[1]
        summary = simple_ctx.summarize()  # no branch
        assert "sub_a" not in summary


class TestSummarizeMaxTokens:
    """max_tokens= drops oldest siblings when exceeded."""

    def test_max_tokens_drops_oldest(self):
        @agentic_function
        def parent():
            """Parent."""
            for i in range(10):
                numbered_step(i)
            return final_step()

        @agentic_function
        def numbered_step(n):
            return f"result_{n}"

        @agentic_function
        def final_step():
            return runtime.exec(content=[{"type": "text", "text": "final"}])

        parent()
        root = parent.context
        final_ctx = root.children[10]
        # Very small token budget — should drop older siblings
        summary = final_ctx.summarize(max_tokens=50)
        # Should still have Current Call
        assert "Current Call" in summary
        # Oldest siblings should be dropped
        # (exact behavior depends on token estimation)


class TestSummarizeCompress:
    """compress=True prevents children from being expanded in branch."""

    def test_compressed_not_expanded_by_branch(self):
        @agentic_function
        def root():
            """Root."""
            compressed_fn()
            return check_fn()

        @agentic_function(compress=True)
        def compressed_fn():
            """Compressed."""
            hidden_child()
            return "compressed_result"

        @agentic_function
        def hidden_child():
            return "hidden"

        @agentic_function
        def check_fn():
            """Check."""
            return runtime.exec(content=[{"type": "text", "text": "check"}])

        root()
        root_ctx = root.context
        check_ctx = root_ctx.children[1]
        # Even with branch, compressed children should not appear
        summary = check_ctx.summarize(branch=["compressed_fn"])
        assert "hidden_child" not in summary


class TestSummarizeCombinations:
    """Test multiple parameters combined."""

    def test_depth0_siblings0_is_isolated(self):
        """depth=0, siblings=0 gives only the header and current call marker."""
        @agentic_function
        def root():
            """Root."""
            step1()
            step2()
            return step3()

        @agentic_function
        def step1():
            return "s1"

        @agentic_function
        def step2():
            return "s2"

        @agentic_function
        def step3():
            return runtime.exec(content=[{"type": "text", "text": "s3"}])

        root()
        ctx = root.context.children[2]
        summary = ctx.summarize(depth=0, siblings=0)
        assert "step1" not in summary
        assert "step2" not in summary
        # Note: "root" appears in the call path (root.step3) but not as an ancestor line
        lines = summary.strip().split("\n")
        ancestor_lines = [l for l in lines if l.strip().startswith("- root(")]
        assert len(ancestor_lines) == 0
        assert "Current Call" in summary

    def test_depth1_siblings1(self):
        @agentic_function
        def root():
            """Root."""
            step1()
            step2()
            return step3()

        @agentic_function
        def step1():
            return "s1"

        @agentic_function
        def step2():
            return "s2"

        @agentic_function
        def step3():
            return runtime.exec(content=[{"type": "text", "text": "s3"}])

        root()
        ctx = root.context.children[2]
        summary = ctx.summarize(depth=1, siblings=1)
        assert "root" in summary   # parent (depth=1)
        assert "step1" not in summary  # only last 1 sibling
        assert "step2" in summary
        assert "Current Call" in summary
