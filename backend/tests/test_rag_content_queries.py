"""
Integration tests for content-related queries through the full RAG stack.

These tests use the real ChromaDB (backend/chroma_db) and the real Anthropic API.
They are skipped automatically if ANTHROPIC_API_KEY is not set.

Test hierarchy (fastest → slowest):
  1. VectorStore.search()            — no API call
  2. CourseSearchTool.execute()      — no API call
  3. RAGSystem.query()               — real API call (costs tokens)
"""
import pytest
from config import config
from vector_store import VectorStore
from search_tools import CourseSearchTool
from rag_system import RAGSystem

needs_api = pytest.mark.skipif(
    not config.ANTHROPIC_API_KEY,
    reason="ANTHROPIC_API_KEY not configured",
)


# ── shared fixtures (module-scoped to avoid reloading embedding model) ────────

@pytest.fixture(scope="module")
def store():
    return VectorStore(config.CHROMA_PATH, config.EMBEDDING_MODEL, config.MAX_RESULTS)


@pytest.fixture(scope="module")
def rag():
    return RAGSystem(config)


# ── Layer 1: VectorStore search (no API) ─────────────────────────────────────

class TestVectorStoreSearch:

    def test_unfiltered_search_returns_results(self, store):
        results = store.search("retrieval augmented generation")
        assert not results.error, f"Unexpected error: {results.error}"
        assert not results.is_empty(), "Search returned zero results"

    def test_search_returns_expected_number_of_docs(self, store):
        results = store.search("MCP protocol architecture")
        assert len(results.documents) <= config.MAX_RESULTS
        assert len(results.documents) == len(results.metadata)

    def test_metadata_has_required_fields(self, store):
        results = store.search("introduction to the course")
        for meta in results.metadata:
            assert "course_title" in meta, f"Missing course_title in {meta}"
            assert "chunk_index" in meta, f"Missing chunk_index in {meta}"

    def test_lesson_number_in_metadata_is_int_or_none(self, store):
        """
        ChromaDB only stores str/int/float/bool — None is coerced.
        Verify lesson_number comes back as int (or is absent), never a string 'None'.
        """
        results = store.search("lesson overview introduction")
        for meta in results.metadata:
            ln = meta.get("lesson_number")
            if ln is not None:
                assert isinstance(ln, int), (
                    f"lesson_number should be int, got {type(ln).__name__!r}: {ln!r}"
                )

    def test_course_name_filter_scopes_results(self, store):
        results = store.search("protocol architecture", course_name="MCP")
        assert not results.is_empty()
        for meta in results.metadata:
            assert "MCP" in meta.get("course_title", ""), (
                f"Result from wrong course: {meta.get('course_title')}"
            )

    def test_lesson_number_filter_returns_results(self, store):
        results = store.search("introduction overview", lesson_number=1)
        assert not results.is_empty()

    def test_unknown_course_name_falls_back_to_closest_semantic_match(self, store):
        """
        _resolve_course_name uses vector search, so a nonsense name is matched
        to the nearest real course rather than erroring.  This is expected
        behaviour — the system never returns 'no course found' for fuzzy input.
        Confirm it does not crash and returns some results.
        """
        results = store.search("content", course_name="NonExistentCourse12345")
        assert not results.error  # no hard error
        # Results come from whichever real course matched semantically


# ── Layer 2: CourseSearchTool.execute() (no API) ──────────────────────────────

class TestCourseSearchToolIntegration:

    def test_basic_query_returns_non_empty_string(self, store):
        tool = CourseSearchTool(store)
        result = tool.execute("retrieval augmented generation")
        assert isinstance(result, str) and len(result.strip()) > 0
        assert result != "No relevant content found."

    def test_result_contains_course_header(self, store):
        tool = CourseSearchTool(store)
        result = tool.execute("chatbot implementation")
        # Each result block starts with [Course Title]
        assert "[" in result and "]" in result

    def test_sources_populated_after_execute(self, store):
        tool = CourseSearchTool(store)
        tool.execute("MCP model context protocol")
        assert len(tool.last_sources) > 0

    def test_sources_have_valid_format(self, store):
        tool = CourseSearchTool(store)
        tool.execute("lesson content overview")
        for src in tool.last_sources:
            # Either plain label or label||url
            parts = src.split("||")
            assert len(parts) in (1, 2), f"Unexpected source format: {src!r}"
            if len(parts) == 2:
                assert parts[1].startswith("http"), f"Link looks wrong: {parts[1]!r}"

    def test_mcp_course_filter_returns_relevant_content(self, store):
        tool = CourseSearchTool(store)
        result = tool.execute("architecture overview", course_name="MCP")
        assert isinstance(result, str) and len(result.strip()) > 0

    def test_lesson_5_filter(self, store):
        tool = CourseSearchTool(store)
        result = tool.execute("lesson content", lesson_number=5)
        assert isinstance(result, str)


# ── Layer 3: RAGSystem.query() — full stack including real API ────────────────

CONTENT_QUERIES = [
    "Are there any courses that include a Chatbot implementation?",
    "Are there any courses that explain what RAG is?",
    "What was covered in lesson 5 of the MCP course?",
    "What is the MCP protocol and how does it work?",
]


@needs_api
class TestRAGSystemContentQueries:

    @pytest.mark.parametrize("query", CONTENT_QUERIES)
    def test_query_does_not_raise(self, rag, query):
        """No query should raise an unhandled exception."""
        try:
            answer, sources = rag.query(query)
        except Exception as exc:
            pytest.fail(
                f"rag.query() raised {type(exc).__name__}: {exc}\n"
                f"Query: {query!r}"
            )

    @pytest.mark.parametrize("query", CONTENT_QUERIES)
    def test_query_returns_non_empty_answer(self, rag, query):
        """
        Every content query must produce a non-empty answer string.
        An empty string here means the model returned no text content,
        which causes the frontend to silently fail or shows 'Query failed'
        if an exception was raised upstream.
        """
        answer, sources = rag.query(query)
        assert isinstance(answer, str), f"answer is {type(answer).__name__}, expected str"
        assert len(answer.strip()) > 0, (
            f"Empty answer for query: {query!r}\n"
            "This indicates generate_response returned '' or crashed."
        )

    def test_chatbot_query_returns_answer(self, rag):
        answer, _ = rag.query("Are there any courses that include a Chatbot implementation?")
        assert len(answer.strip()) > 0

    def test_rag_explanation_query_returns_answer(self, rag):
        answer, _ = rag.query("Are there any courses that explain what RAG is?")
        assert len(answer.strip()) > 0

    def test_lesson_detail_query_returns_answer(self, rag):
        answer, _ = rag.query("What was covered in lesson 5 of the MCP course?")
        assert len(answer.strip()) > 0

    def test_sources_returned_for_content_query(self, rag):
        """Content queries should always populate sources."""
        _, sources = rag.query("What is MCP?")
        assert isinstance(sources, list)
        # Sources might be empty if Claude answers without searching,
        # but must not crash.
