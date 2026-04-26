import sys
import os
from unittest.mock import MagicMock
import pytest

# Make backend/ importable regardless of where pytest is invoked from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_rag_system():
    """Fully mocked RAGSystem — no ChromaDB, embedding model, or Anthropic API required."""
    rag = MagicMock()
    rag.session_manager.create_session.return_value = "session_1"
    rag.query.return_value = ("Test answer about the course.", ["Course A - Lesson 1"])
    rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Course A", "Course B"],
    }
    return rag


@pytest.fixture
def sample_course_titles():
    return ["Intro to RAG", "MCP Deep Dive", "Building Chatbots"]


@pytest.fixture
def sample_query_text():
    return "What is retrieval-augmented generation?"
