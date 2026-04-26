"""
Unit tests for AIGenerator in ai_generator.py.
All Anthropic API calls are mocked — no real API usage.

Focus areas
-----------
1. Direct text response path (stop_reason != tool_use)
2. Single-tool-round path: tool executed, messages structured correctly
3. Two-tool-round path: both loop iterations use tools, terminal call strips them
4. Termination conditions: early exit on end_turn, error string on tool failure
5. Crash surface: both direct and tool paths when content is empty
"""
import pytest
from unittest.mock import MagicMock, patch, call
from ai_generator import AIGenerator


# ── mock factories ────────────────────────────────────────────────────────────

def text_block(text: str):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def tool_use_block(name: str, input_dict: dict, id: str = "tool_1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_dict
    b.id = id
    return b


def api_response(blocks, stop_reason="end_turn"):
    r = MagicMock()
    r.content = blocks
    r.stop_reason = stop_reason
    return r


def make_generator():
    """AIGenerator with a fully mocked Anthropic client."""
    with patch("anthropic.Anthropic"):
        gen = AIGenerator(api_key="test-key", model="test-model")
    return gen


def make_tool_manager(tool_result="tool result text"):
    tm = MagicMock()
    tm.execute_tool.return_value = tool_result
    return tm


# ── direct text response path ─────────────────────────────────────────────────

class TestDirectResponsePath:

    def test_text_block_returned_correctly(self):
        gen = make_generator()
        gen.client.messages.create.return_value = api_response(
            [text_block("Direct answer about RAG")]
        )
        result = gen.generate_response("What is RAG?")
        assert result == "Direct answer about RAG"

    def test_first_text_block_used_when_multiple(self):
        gen = make_generator()
        gen.client.messages.create.return_value = api_response(
            [text_block("First"), text_block("Second")]
        )
        result = gen.generate_response("query")
        assert result == "First"

    def test_empty_content_returns_empty_string_not_index_error(self):
        """
        REGRESSION GUARD: When Claude returns stop_reason=end_turn but content=[],
        generate_response must return '' instead of raising IndexError.
        Before the fix the line `return response.content[0].text` crashed,
        which propagated as HTTP 500 / 'Query failed' in the frontend.
        """
        gen = make_generator()
        gen.client.messages.create.return_value = api_response([], stop_reason="end_turn")

        result = gen.generate_response("Are there courses about chatbots?")
        assert result == ""  # graceful fallback, no crash

    def test_no_tools_means_no_tool_choice_in_params(self):
        gen = make_generator()
        gen.client.messages.create.return_value = api_response([text_block("ok")])
        gen.generate_response("query")
        call_kwargs = gen.client.messages.create.call_args.kwargs
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    def test_tools_parameter_included_in_round1_when_provided(self):
        gen = make_generator()
        gen.client.messages.create.return_value = api_response([text_block("ok")])
        tools = [{"name": "search_course_content"}]
        gen.generate_response("query", tools=tools)
        call_kwargs = gen.client.messages.create.call_args.kwargs
        assert call_kwargs.get("tools") == tools
        assert call_kwargs.get("tool_choice") == {"type": "auto"}


# ── tool-use path ─────────────────────────────────────────────────────────────

class TestToolUsePath:

    def test_tool_use_stop_reason_triggers_tool_execution_and_second_api_call(self):
        gen = make_generator()
        tool_block = tool_use_block("search_course_content", {"query": "RAG"})
        r1 = api_response([tool_block], stop_reason="tool_use")
        r2 = api_response([text_block("RAG is retrieval-augmented generation")])
        gen.client.messages.create.side_effect = [r1, r2]

        tm = make_tool_manager("RAG content from course")
        result = gen.generate_response(
            "What is RAG?",
            tools=[{"name": "search_course_content"}],
            tool_manager=tm,
        )

        assert "RAG is retrieval-augmented generation" in result
        assert gen.client.messages.create.call_count == 2

    def test_tool_manager_invoked_with_correct_tool_name_and_args(self):
        gen = make_generator()
        block = tool_use_block(
            "search_course_content",
            {"query": "MCP architecture", "course_name": "MCP", "lesson_number": 2},
            id="xyz",
        )
        r1 = api_response([block], stop_reason="tool_use")
        r2 = api_response([text_block("answer")])
        gen.client.messages.create.side_effect = [r1, r2]

        tm = make_tool_manager()
        gen.generate_response("test", tools=[{}], tool_manager=tm)

        tm.execute_tool.assert_called_once_with(
            "search_course_content",
            query="MCP architecture",
            course_name="MCP",
            lesson_number=2,
        )

    def test_tool_result_id_matches_tool_use_id(self):
        gen = make_generator()
        block = tool_use_block("search_course_content", {"query": "q"}, id="block_abc")
        r1 = api_response([block], stop_reason="tool_use")
        r2 = api_response([text_block("ok")])
        gen.client.messages.create.side_effect = [r1, r2]

        tm = make_tool_manager("result")
        gen.generate_response("test", tools=[{}], tool_manager=tm)

        r2_messages = gen.client.messages.create.call_args_list[1].kwargs["messages"]
        user_content = r2_messages[-1]["content"]
        tool_results = [c for c in user_content if isinstance(c, dict) and c.get("type") == "tool_result"]
        assert tool_results[0]["tool_use_id"] == "block_abc"

    def test_loop_round_includes_tools_and_tool_choice(self):
        gen = make_generator()
        block = tool_use_block("search_course_content", {"query": "q"})
        r1 = api_response([block], stop_reason="tool_use")
        r2 = api_response([text_block("ok")])
        gen.client.messages.create.side_effect = [r1, r2]

        tools = [{"name": "search_course_content"}]
        gen.generate_response("test", tools=tools, tool_manager=make_tool_manager())

        # Both the first and second call (loop iteration) include tools
        for i in range(2):
            kwargs = gen.client.messages.create.call_args_list[i].kwargs
            assert kwargs.get("tools") == tools
            assert kwargs.get("tool_choice") == {"type": "auto"}

    def test_round2_empty_content_returns_empty_string_not_crash(self):
        gen = make_generator()
        block = tool_use_block("search_course_content", {"query": "q"})
        r1 = api_response([block], stop_reason="tool_use")
        r2 = api_response([])  # empty — as seen with claude-sonnet-4-6
        gen.client.messages.create.side_effect = [r1, r2]

        result = gen.generate_response("test", tools=[{}], tool_manager=make_tool_manager())
        assert result == ""  # doesn't crash, returns ""

    def test_round2_message_history_has_correct_turn_order(self):
        """Messages must alternate: user → assistant(tool_use) → user(tool_result)."""
        gen = make_generator()
        block = tool_use_block("search_course_content", {"query": "q"})
        r1 = api_response([block], stop_reason="tool_use")
        r2 = api_response([text_block("ok")])
        gen.client.messages.create.side_effect = [r1, r2]

        gen.generate_response("original question", tools=[{}], tool_manager=make_tool_manager())

        r2_messages = gen.client.messages.create.call_args_list[1].kwargs["messages"]
        assert r2_messages[0]["role"] == "user"
        assert r2_messages[1]["role"] == "assistant"
        assert r2_messages[2]["role"] == "user"


# ── two-tool-round path ───────────────────────────────────────────────────────

class TestTwoRoundToolLoop:

    def _setup_two_round(self, r3_blocks=None):
        """Returns (gen, tm) wired for two tool-use rounds then a text response."""
        gen = make_generator()
        b1 = tool_use_block("get_course_outline", {"course_title": "MCP"}, id="id_r1")
        b2 = tool_use_block("search_course_content", {"query": "lesson 4 topic"}, id="id_r2")
        r1 = api_response([b1], stop_reason="tool_use")
        r2 = api_response([b2], stop_reason="tool_use")
        r3 = api_response(r3_blocks if r3_blocks is not None else [text_block("Final synthesized answer")])
        gen.client.messages.create.side_effect = [r1, r2, r3]
        tm = make_tool_manager("tool output")
        return gen, tm

    def test_two_tool_rounds_makes_three_api_calls(self):
        gen, tm = self._setup_two_round()
        gen.generate_response("complex query", tools=[{}], tool_manager=tm)
        assert gen.client.messages.create.call_count == 3

    def test_both_loop_rounds_include_tools_terminal_call_does_not(self):
        gen, tm = self._setup_two_round()
        tools = [{"name": "search_course_content"}]
        gen.generate_response("complex query", tools=tools, tool_manager=tm)

        calls = gen.client.messages.create.call_args_list
        assert "tools" in calls[0].kwargs and "tool_choice" in calls[0].kwargs
        assert "tools" in calls[1].kwargs and "tool_choice" in calls[1].kwargs
        assert "tools" not in calls[2].kwargs
        assert "tool_choice" not in calls[2].kwargs

    def test_tool_manager_called_once_per_round(self):
        gen, tm = self._setup_two_round()
        gen.generate_response("complex query", tools=[{}], tool_manager=tm)
        assert tm.execute_tool.call_count == 2

    def test_messages_accumulate_to_five_entries_for_terminal_call(self):
        gen, tm = self._setup_two_round()
        gen.generate_response("complex query", tools=[{}], tool_manager=tm)

        terminal_messages = gen.client.messages.create.call_args_list[2].kwargs["messages"]
        assert len(terminal_messages) == 5
        roles = [m["role"] for m in terminal_messages]
        assert roles == ["user", "assistant", "user", "assistant", "user"]

    def test_terminal_call_final_message_includes_followup_text(self):
        gen, tm = self._setup_two_round()
        gen.generate_response("complex query", tools=[{}], tool_manager=tm)

        terminal_messages = gen.client.messages.create.call_args_list[2].kwargs["messages"]
        last_content = terminal_messages[-1]["content"]
        text_entries = [c for c in last_content if isinstance(c, dict) and c.get("type") == "text"]
        assert len(text_entries) == 1
        assert "please answer" in text_entries[0]["text"].lower()

    def test_mid_loop_tool_result_messages_have_no_followup_text(self):
        """Follow-up text only in terminal call — not in loop iterations."""
        gen, tm = self._setup_two_round()
        gen.generate_response("complex query", tools=[{}], tool_manager=tm)

        # The user message sent in the second loop iteration (call index 1)
        loop2_messages = gen.client.messages.create.call_args_list[1].kwargs["messages"]
        last_content = loop2_messages[-1]["content"]
        text_entries = [c for c in last_content if isinstance(c, dict) and c.get("type") == "text"]
        assert len(text_entries) == 0

    def test_returns_text_from_terminal_response(self):
        gen, tm = self._setup_two_round()
        result = gen.generate_response("complex query", tools=[{}], tool_manager=tm)
        assert result == "Final synthesized answer"

    def test_second_round_tool_result_id_matches_second_block_id(self):
        gen, tm = self._setup_two_round()
        gen.generate_response("complex query", tools=[{}], tool_manager=tm)

        # The 4th message (index 3) in the terminal call is assistant(r2 tool_use)
        # The 5th message (index 4) is user(r2 tool_results) — check tool_use_id
        terminal_messages = gen.client.messages.create.call_args_list[2].kwargs["messages"]
        last_tool_results = [
            c for c in terminal_messages[4]["content"]
            if isinstance(c, dict) and c.get("type") == "tool_result"
        ]
        assert last_tool_results[0]["tool_use_id"] == "id_r2"

    def test_terminal_empty_content_returns_empty_string_not_crash(self):
        gen, tm = self._setup_two_round(r3_blocks=[])
        result = gen.generate_response("complex query", tools=[{}], tool_manager=tm)
        assert result == ""


# ── termination conditions ────────────────────────────────────────────────────

class TestTerminationConditions:

    def test_early_termination_round_two_end_turn_returns_round2_text(self):
        gen = make_generator()
        b1 = tool_use_block("search_course_content", {"query": "q"})
        r1 = api_response([b1], stop_reason="tool_use")
        r2 = api_response([text_block("Answer from round 2")])
        gen.client.messages.create.side_effect = [r1, r2]

        result = gen.generate_response("query", tools=[{}], tool_manager=make_tool_manager())

        assert result == "Answer from round 2"
        assert gen.client.messages.create.call_count == 2  # no terminal call


# ── tool execution errors ─────────────────────────────────────────────────────

class TestToolExecutionError:

    def test_tool_execution_exception_returns_user_facing_error_string(self):
        gen = make_generator()
        block = tool_use_block("search_course_content", {"query": "q"})
        r1 = api_response([block], stop_reason="tool_use")
        gen.client.messages.create.return_value = r1

        tm = make_tool_manager()
        tm.execute_tool.side_effect = RuntimeError("DB unavailable")

        result = gen.generate_response("query", tools=[{}], tool_manager=tm)
        assert "encountered an error" in result.lower()

    def test_tool_execution_failure_makes_no_additional_api_calls(self):
        gen = make_generator()
        block = tool_use_block("search_course_content", {"query": "q"})
        r1 = api_response([block], stop_reason="tool_use")
        gen.client.messages.create.return_value = r1

        tm = make_tool_manager()
        tm.execute_tool.side_effect = RuntimeError("DB unavailable")

        gen.generate_response("query", tools=[{}], tool_manager=tm)
        assert gen.client.messages.create.call_count == 1
