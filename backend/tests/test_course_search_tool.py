"""
Unit tests for CourseSearchTool.execute() in search_tools.py.
All tests use a mocked VectorStore — no ChromaDB or API calls.
"""
import pytest
from unittest.mock import MagicMock
from search_tools import CourseSearchTool
from vector_store import SearchResults


# ── helpers ──────────────────────────────────────────────────────────────────

def make_store(docs=(), metas=(), distances=(), error=None, lesson_link=None):
    store = MagicMock()
    if error:
        store.search.return_value = SearchResults.empty(error)
    else:
        store.search.return_value = SearchResults(
            documents=list(docs),
            metadata=list(metas),
            distances=list(distances),
        )
    store.get_lesson_link.return_value = lesson_link
    return store


# ── execute() return value ────────────────────────────────────────────────────

class TestExecuteReturnValue:

    def test_returns_formatted_text_on_results(self):
        store = make_store(
            docs=["RAG stands for Retrieval-Augmented Generation."],
            metas=[{"course_title": "Chroma Course", "lesson_number": 1}],
            distances=[0.1],
        )
        tool = CourseSearchTool(store)
        result = tool.execute("What is RAG?")

        assert "RAG stands for Retrieval-Augmented Generation" in result
        assert "Chroma Course" in result
        assert "Lesson 1" in result

    def test_returns_no_content_message_for_empty_results(self):
        store = make_store()
        tool = CourseSearchTool(store)
        result = tool.execute("something obscure")
        assert "No relevant content found" in result

    def test_empty_message_includes_course_name_filter(self):
        store = make_store()
        tool = CourseSearchTool(store)
        result = tool.execute("something", course_name="MCP")
        assert "MCP" in result

    def test_empty_message_includes_lesson_filter(self):
        store = make_store()
        tool = CourseSearchTool(store)
        result = tool.execute("something", lesson_number=3)
        assert "3" in result

    def test_returns_error_string_on_search_error(self):
        store = make_store(error="Search error: DB unavailable")
        tool = CourseSearchTool(store)
        result = tool.execute("query")
        assert "Search error" in result

    def test_none_lesson_number_in_meta_does_not_crash(self):
        """Chunk stored without a lesson number (lesson_number=None) must not raise."""
        store = make_store(
            docs=["some content"],
            metas=[{"course_title": "Course X", "lesson_number": None}],
            distances=[0.2],
        )
        tool = CourseSearchTool(store)
        result = tool.execute("something")
        # Should include course title and not crash
        assert "Course X" in result

    def test_multiple_chunks_separated_by_blank_lines(self):
        store = make_store(
            docs=["chunk A", "chunk B"],
            metas=[
                {"course_title": "C", "lesson_number": 1},
                {"course_title": "C", "lesson_number": 2},
            ],
            distances=[0.1, 0.2],
        )
        tool = CourseSearchTool(store)
        result = tool.execute("query")
        assert "chunk A" in result
        assert "chunk B" in result


# ── execute() delegates to store correctly ────────────────────────────────────

class TestExecutePassesArgsToStore:

    def test_passes_query_only(self):
        store = make_store()
        CourseSearchTool(store).execute("neural networks")
        store.search.assert_called_once_with(
            query="neural networks", course_name=None, lesson_number=None
        )

    def test_passes_course_name(self):
        store = make_store()
        CourseSearchTool(store).execute("content", course_name="Chroma")
        store.search.assert_called_once_with(
            query="content", course_name="Chroma", lesson_number=None
        )

    def test_passes_lesson_number(self):
        store = make_store()
        CourseSearchTool(store).execute("content", lesson_number=4)
        store.search.assert_called_once_with(
            query="content", course_name=None, lesson_number=4
        )

    def test_passes_all_three_filters(self):
        store = make_store()
        CourseSearchTool(store).execute("content", course_name="MCP", lesson_number=2)
        store.search.assert_called_once_with(
            query="content", course_name="MCP", lesson_number=2
        )


# ── source tracking ───────────────────────────────────────────────────────────

class TestSourceTracking:

    def test_last_sources_set_after_results(self):
        store = make_store(
            docs=["text"],
            metas=[{"course_title": "Course A", "lesson_number": 1}],
            distances=[0.1],
        )
        tool = CourseSearchTool(store)
        tool.execute("query")
        assert len(tool.last_sources) == 1
        assert "Course A - Lesson 1" in tool.last_sources[0]

    def test_last_sources_empty_when_no_results(self):
        store = make_store()
        tool = CourseSearchTool(store)
        tool.execute("query")
        assert tool.last_sources == []

    def test_sources_include_pipe_link_when_lesson_link_exists(self):
        store = make_store(
            docs=["text"],
            metas=[{"course_title": "Course A", "lesson_number": 2}],
            distances=[0.1],
            lesson_link="https://example.com/lesson2",
        )
        tool = CourseSearchTool(store)
        tool.execute("query")
        assert "||https://example.com/lesson2" in tool.last_sources[0]

    def test_sources_have_no_pipe_when_no_link(self):
        store = make_store(
            docs=["text"],
            metas=[{"course_title": "Course A", "lesson_number": 2}],
            distances=[0.1],
            lesson_link=None,
        )
        tool = CourseSearchTool(store)
        tool.execute("query")
        assert "||" not in tool.last_sources[0]

    def test_sources_deduplicated_for_same_lesson(self):
        """Two chunks from the same lesson → only one source entry."""
        store = make_store(
            docs=["chunk 1", "chunk 2"],
            metas=[
                {"course_title": "Course A", "lesson_number": 1},
                {"course_title": "Course A", "lesson_number": 1},
            ],
            distances=[0.1, 0.2],
        )
        tool = CourseSearchTool(store)
        tool.execute("query")
        assert len(tool.last_sources) == 1

    def test_sources_not_deduplicated_across_different_lessons(self):
        store = make_store(
            docs=["chunk 1", "chunk 2"],
            metas=[
                {"course_title": "Course A", "lesson_number": 1},
                {"course_title": "Course A", "lesson_number": 2},
            ],
            distances=[0.1, 0.2],
        )
        tool = CourseSearchTool(store)
        tool.execute("query")
        assert len(tool.last_sources) == 2

    def test_get_lesson_link_not_called_when_lesson_number_is_none(self):
        """If lesson_number is None we must not call get_lesson_link."""
        store = make_store(
            docs=["text"],
            metas=[{"course_title": "Course A", "lesson_number": None}],
            distances=[0.1],
        )
        tool = CourseSearchTool(store)
        tool.execute("query")
        store.get_lesson_link.assert_not_called()
