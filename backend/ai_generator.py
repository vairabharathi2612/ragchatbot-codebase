import anthropic
from typing import List, Optional

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """You are an AI assistant specialized in course materials and educational content with access to two tools for course information.

Tool Selection:
- **get_course_outline** — use for any outline, syllabus, lesson list, or structure query about a course.
  Format the result as Markdown:
    ## <course title>
    [View Course](<course link>)

    | # | Lesson |
    |---|--------|
    | 0 | <title> |
    | 1 | <title> |
    ...  (include every lesson returned, one row per lesson)
- **search_course_content** — use for specific questions about course content, concepts, or details.
- You may use tools across up to **2 sequential rounds** per query.
  Use a second tool call only when the first result is insufficient to fully answer the question.
  If the first result is sufficient, answer immediately.
- If a tool yields no results, state this clearly without offering alternatives.

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Use the appropriate tool first, then answer
- **No meta-commentary**: Provide direct answers only — no reasoning process, search explanations, or question-type analysis. Do not mention "based on the search results".

All responses must be:
1. **Brief, concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    MAX_TOOL_ROUNDS = 2

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }

    def _extract_text(self, response) -> str:
        # Iterate defensively — claude-sonnet-4-6 can return 0 visible blocks,
        # which causes IndexError on content[0] and a 500 upstream
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        messages = [{"role": "user", "content": query}]

        for _ in range(self.MAX_TOOL_ROUNDS):
            params = {**self.base_params, "messages": messages, "system": system_content}
            if tools:
                params["tools"] = tools
                params["tool_choice"] = {"type": "auto"}

            response = self.client.messages.create(**params)

            # Termination (b): Claude returned text directly or no tool_manager available
            if response.stop_reason != "tool_use" or not tool_manager:
                return self._extract_text(response)

            # Execute all tool_use blocks in this response
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        result = tool_manager.execute_tool(block.name, **block.input)
                    except Exception:
                        return "I encountered an error while retrieving information. Please try again."  # Termination (c)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "assistant", "content": response.content})
            # No follow-up text here — allows Claude to call a second tool in the next round
            messages.append({"role": "user", "content": tool_results})

        # Termination (a): both rounds used tools — final synthesis call without tools.
        # Append follow-up text to last user message so claude-sonnet-4-6 produces visible text.
        terminal_messages = messages[:-1] + [{
            "role": "user",
            "content": messages[-1]["content"] + [
                {"type": "text", "text": "Based on the search results above, please answer the question."}
            ]
        }]
        final_params = {**self.base_params, "messages": terminal_messages, "system": system_content}
        return self._extract_text(self.client.messages.create(**final_params))