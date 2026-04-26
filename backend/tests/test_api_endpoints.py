"""
Tests for the FastAPI HTTP API layer (/api/query, /api/courses).

A self-contained test app is defined here that mirrors app.py's endpoints
without mounting the frontend static files (which don't exist in the test
environment). RAGSystem is fully mocked — no ChromaDB, embedding model, or
Anthropic API is required to run these tests.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from starlette.testclient import TestClient


# ── Pydantic models (mirror app.py) ──────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None

class QueryResponse(BaseModel):
    answer: str
    sources: List[str]
    session_id: str

class CourseStats(BaseModel):
    total_courses: int
    course_titles: List[str]


# ── test app factory ──────────────────────────────────────────────────────────

def build_test_app(rag_system):
    """Minimal FastAPI app with the same routes as app.py, without static files."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = rag_system.session_manager.create_session()
            answer, sources = rag_system.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(mock_rag_system):
    return TestClient(build_test_app(mock_rag_system))


# ── /api/query tests ──────────────────────────────────────────────────────────

class TestQueryEndpoint:

    def test_post_query_returns_200(self, client):
        resp = client.post("/api/query", json={"query": "What is RAG?"})
        assert resp.status_code == 200

    def test_response_has_required_fields(self, client):
        body = client.post("/api/query", json={"query": "What is RAG?"}).json()
        assert "answer" in body
        assert "sources" in body
        assert "session_id" in body

    def test_answer_is_string(self, client):
        body = client.post("/api/query", json={"query": "test"}).json()
        assert isinstance(body["answer"], str)

    def test_sources_is_list(self, client):
        body = client.post("/api/query", json={"query": "test"}).json()
        assert isinstance(body["sources"], list)

    def test_new_session_created_when_not_provided(self, client, mock_rag_system):
        client.post("/api/query", json={"query": "test"})
        mock_rag_system.session_manager.create_session.assert_called_once()

    def test_provided_session_id_is_reused(self, client, mock_rag_system):
        resp = client.post("/api/query", json={"query": "test", "session_id": "my_session"})
        assert resp.json()["session_id"] == "my_session"
        mock_rag_system.session_manager.create_session.assert_not_called()

    def test_rag_query_called_with_user_query_and_session(self, client, mock_rag_system):
        client.post("/api/query", json={"query": "What is MCP?", "session_id": "s1"})
        mock_rag_system.query.assert_called_once_with("What is MCP?", "s1")

    def test_rag_query_called_with_created_session_when_none_provided(self, client, mock_rag_system):
        client.post("/api/query", json={"query": "What is MCP?"})
        mock_rag_system.query.assert_called_once_with("What is MCP?", "session_1")

    def test_sources_propagated_from_rag_result(self, client, mock_rag_system):
        mock_rag_system.query.return_value = ("Answer", ["Course X - Lesson 2"])
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.json()["sources"] == ["Course X - Lesson 2"]

    def test_empty_sources_returned_as_empty_list(self, client, mock_rag_system):
        mock_rag_system.query.return_value = ("Answer with no sources", [])
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.json()["sources"] == []

    def test_multiple_sources_all_present_in_response(self, client, mock_rag_system):
        mock_rag_system.query.return_value = (
            "Answer", ["Course A - Lesson 1", "Course B - Lesson 3"]
        )
        resp = client.post("/api/query", json={"query": "test"})
        assert len(resp.json()["sources"]) == 2

    def test_rag_exception_returns_500(self, client, mock_rag_system):
        mock_rag_system.query.side_effect = RuntimeError("DB unavailable")
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.status_code == 500

    def test_500_response_contains_error_detail(self, client, mock_rag_system):
        mock_rag_system.query.side_effect = RuntimeError("DB unavailable")
        resp = client.post("/api/query", json={"query": "test"})
        assert "DB unavailable" in resp.json()["detail"]

    def test_missing_query_field_returns_422(self, client):
        resp = client.post("/api/query", json={})
        assert resp.status_code == 422

    def test_response_content_type_is_json(self, client):
        resp = client.post("/api/query", json={"query": "test"})
        assert "application/json" in resp.headers["content-type"]

    def test_session_id_in_response_matches_created_session(self, client, mock_rag_system):
        mock_rag_system.session_manager.create_session.return_value = "session_42"
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.json()["session_id"] == "session_42"


# ── /api/courses tests ────────────────────────────────────────────────────────

class TestCoursesEndpoint:

    def test_get_courses_returns_200(self, client):
        resp = client.get("/api/courses")
        assert resp.status_code == 200

    def test_response_has_total_courses_and_titles(self, client):
        body = client.get("/api/courses").json()
        assert "total_courses" in body
        assert "course_titles" in body

    def test_total_courses_is_integer(self, client):
        assert isinstance(client.get("/api/courses").json()["total_courses"], int)

    def test_course_titles_is_list(self, client):
        assert isinstance(client.get("/api/courses").json()["course_titles"], list)

    def test_total_courses_matches_mock(self, client):
        assert client.get("/api/courses").json()["total_courses"] == 2

    def test_course_titles_match_mock(self, client):
        assert client.get("/api/courses").json()["course_titles"] == ["Course A", "Course B"]

    def test_get_course_analytics_called(self, client, mock_rag_system):
        client.get("/api/courses")
        mock_rag_system.get_course_analytics.assert_called_once()

    def test_analytics_exception_returns_500(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.side_effect = RuntimeError("ChromaDB unavailable")
        resp = client.get("/api/courses")
        assert resp.status_code == 500

    def test_500_error_detail_propagated(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.side_effect = RuntimeError("ChromaDB unavailable")
        resp = client.get("/api/courses").json()
        assert "ChromaDB unavailable" in resp["detail"]

    def test_empty_catalog_returns_zero_courses(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0, "course_titles": []
        }
        body = client.get("/api/courses").json()
        assert body["total_courses"] == 0
        assert body["course_titles"] == []

    def test_large_catalog_count_preserved(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 100,
            "course_titles": [f"Course {i}" for i in range(100)],
        }
        body = client.get("/api/courses").json()
        assert body["total_courses"] == 100
        assert len(body["course_titles"]) == 100

    def test_response_content_type_is_json(self, client):
        resp = client.get("/api/courses")
        assert "application/json" in resp.headers["content-type"]
